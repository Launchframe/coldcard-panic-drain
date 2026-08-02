"""Broadcast due signed PSBTs via local Bitcoin Core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from embit.finalizer import finalize_psbt
from embit.psbt import PSBT

from coldcard_panic_drain.broadcast.core_rpc import CoreRpcClient, CoreRpcError
from coldcard_panic_drain.broadcast.state import BroadcastState, state_path
from coldcard_panic_drain.schedule.load import load_schedule

FEE_URGENCY_BANNER = (
    "WARNING: You are racing an attacker with access to the compromised seed. "
    "Fees are fixed at PSBT creation time — use a competitive --fee-base when planning "
    "if you rely on auto-broadcast. See docs/FEE-SPIKE-RECOVERY.md if fees spike mid-drain."
)


@dataclass
class BroadcastResult:
    order: int
    label: str
    action: str  # broadcast | skipped | dry_run | failed | already
    txid: Optional[str] = None
    detail: str = ""


def _parse_not_before(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _signed_tx_hex(signed_psbt_path: Path) -> tuple[str, str]:
    psbt = PSBT.parse(signed_psbt_path.read_bytes())
    tx = finalize_psbt(psbt)
    if tx is None:
        raise ValueError(f"Could not finalize signed PSBT: {signed_psbt_path.name}")
    txid = tx.txid()
    txid_hex = txid.hex() if isinstance(txid, bytes) else str(txid)
    return txid_hex, tx.serialize().hex()


def run_broadcast_due(
    output_dir: Path,
    rpc: CoreRpcClient,
    *,
    max_count: int = 1,
    dry_run: bool = False,
    skip_failed: bool = False,
) -> list[BroadcastResult]:
    sched_path = output_dir / "schedule.yaml"
    doc = load_schedule(sched_path)
    now = datetime.now(timezone.utc)
    state = BroadcastState.load(state_path(output_dir))
    results: list[BroadcastResult] = []
    sent = 0

    for entry in sorted(doc.get("entries") or [], key=lambda e: e.get("order", 0)):
        if sent >= max_count:
            break
        order = int(entry["order"])
        label = entry.get("label", "")
        if state.is_broadcast(order):
            results.append(BroadcastResult(order, label, "already", detail="already broadcast"))
            continue
        prev = state.get(order)
        if skip_failed and prev.get("status") == "failed":
            results.append(BroadcastResult(order, label, "skipped", detail="prior failure"))
            continue

        not_before = _parse_not_before(entry["broadcast_not_before"])
        if now < not_before:
            continue

        signed_rel = entry.get("signed", "")
        signed_path = output_dir / signed_rel
        if not signed_path.is_file():
            results.append(
                BroadcastResult(order, label, "skipped", detail="signed PSBT missing")
            )
            continue

        try:
            txid, raw_hex = _signed_tx_hex(signed_path)
        except ValueError as e:
            state.mark_failed(order, str(e))
            state.save_atomic(state_path(output_dir))
            results.append(BroadcastResult(order, label, "failed", detail=str(e)))
            sent += 1
            continue

        existing = rpc.get_raw_transaction(txid)
        if existing is not None:
            state.mark_broadcast(order, txid)
            state.save_atomic(state_path(output_dir))
            results.append(BroadcastResult(order, label, "already", txid=txid, detail="on chain/mempool"))
            sent += 1
            continue

        if dry_run:
            results.append(BroadcastResult(order, label, "dry_run", txid=txid))
            sent += 1
            continue

        try:
            accept = rpc.test_mempool_accept(raw_hex)
            if accept and not accept[0].get("allowed", True):
                reason = accept[0].get("reject-reason", "mempool rejected")
                raise CoreRpcError(reason)
            returned = rpc.send_raw_transaction(raw_hex)
            state.mark_broadcast(order, returned)
            state.save_atomic(state_path(output_dir))
            results.append(BroadcastResult(order, label, "broadcast", txid=returned))
        except CoreRpcError as e:
            state.mark_failed(order, str(e))
            state.save_atomic(state_path(output_dir))
            results.append(BroadcastResult(order, label, "failed", detail=str(e)))
        sent += 1

    return results
