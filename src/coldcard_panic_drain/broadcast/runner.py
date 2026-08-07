"""Broadcast due signed PSBTs via local Bitcoin Core."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from embit.finalizer import finalize_psbt
from embit.psbt import PSBT

from coldcard_panic_drain.broadcast.core_rpc import CoreRpcClient, CoreRpcError
from coldcard_panic_drain.broadcast.paths import ensure_signed_psbt_dir_ready, signed_path_under_output
from coldcard_panic_drain.broadcast.state import BroadcastState, state_path
from coldcard_panic_drain.schedule.load import load_schedule, schedule_quiet_hours
from coldcard_panic_drain.schedule.quiet_hours import in_quiet_hours

# Default width (minutes) of the runtime broadcast jitter window: once an entry's
# broadcast_not_before has passed and its signed PSBT is present, the actual send
# is delayed by a further uniform(0, jitter) draw so a --follow/cron watcher does
# not fire the instant each entry becomes due (see docs/FEE-SPIKE-RECOVERY.md and
# README.md §9 for why fixed-cadence auto-broadcast is fingerprintable).
DEFAULT_BROADCAST_JITTER_MINUTES = 90

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


def _parse_broadcast_at(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _scheduled_gap_after_previous(
    entries: list[dict], order: int
) -> Optional[timedelta]:
    """Planned spacing between `order` and the previous schedule entry."""
    by_order = {int(e["order"]): e for e in entries}
    if order <= 1 or order not in by_order or (order - 1) not in by_order:
        return None
    cur = _parse_not_before(by_order[order]["broadcast_not_before"])
    prev = _parse_not_before(by_order[order - 1]["broadcast_not_before"])
    return cur - prev


def _last_prior_broadcast_at(state: BroadcastState, order: int) -> Optional[datetime]:
    """Most recent `broadcast_at` among already-broadcast entries before `order`."""
    latest: Optional[datetime] = None
    for prior_order in range(1, order):
        entry = state.get(prior_order)
        if entry.get("status") != "broadcast":
            continue
        raw = entry.get("broadcast_at")
        if not raw:
            continue
        dt = _parse_broadcast_at(raw)
        if latest is None or dt > latest:
            latest = dt
    return latest


def _catch_up_ready_floor(
    order: int,
    entries: list[dict],
    state: BroadcastState,
) -> Optional[datetime]:
    """Earliest allowed send when catching up on a backlog.

    When several entries are overdue, honor the relative spacing from
    schedule.yaml instead of firing them back-to-back. Uses the most recent
    prior broadcast time plus the scheduled gap to the current entry.
    """
    gap = _scheduled_gap_after_previous(entries, order)
    prior_broadcast = _last_prior_broadcast_at(state, order)
    if gap is None or prior_broadcast is None:
        return None
    return prior_broadcast + gap


def _resolve_ready_at(
    order: int,
    not_before: datetime,
    entries: list[dict],
    state: BroadcastState,
    rng: random.Random,
    broadcast_jitter_minutes: int,
) -> datetime:
    """Runtime send time: schedule jitter plus backlog catch-up floor."""
    existing = state.get_ready_at(order)
    if broadcast_jitter_minutes > 0:
        if existing is None:
            offset = timedelta(minutes=rng.uniform(0, broadcast_jitter_minutes))
            ready = not_before + offset
        else:
            ready = existing
    else:
        ready = existing or not_before

    floor = _catch_up_ready_floor(order, entries, state)
    if floor is not None and floor > ready:
        ready = floor
    return ready


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
    broadcast_jitter_minutes: int = DEFAULT_BROADCAST_JITTER_MINUTES,
    respect_quiet_hours: bool = False,
    rng: Optional[random.Random] = None,
) -> list[BroadcastResult]:
    sched_path = output_dir / "schedule.yaml"
    doc = load_schedule(sched_path)
    schedule_entries = doc.get("entries") or []
    now = datetime.now(timezone.utc)
    state = BroadcastState.load(state_path(output_dir))
    rng = rng or random.Random()
    quiet_hours = schedule_quiet_hours(doc) if respect_quiet_hours else None
    results: list[BroadcastResult] = []
    sent = 0
    signed_dir_checked = dry_run

    for entry in sorted(schedule_entries, key=lambda e: e.get("order", 0)):
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

        if not signed_dir_checked:
            ensure_signed_psbt_dir_ready(output_dir)
            signed_dir_checked = True

        signed_rel = entry.get("signed", "")
        try:
            signed_path = signed_path_under_output(output_dir, signed_rel)
        except ValueError as e:
            results.append(
                BroadcastResult(order, label, "skipped", detail=str(e))
            )
            continue
        if not signed_path.is_file():
            results.append(
                BroadcastResult(order, label, "skipped", detail="signed PSBT missing")
            )
            continue

        ready_at = _resolve_ready_at(
            order,
            not_before,
            schedule_entries,
            state,
            rng,
            broadcast_jitter_minutes,
        )
        persisted_ready = state.get_ready_at(order)
        if persisted_ready != ready_at and (
            broadcast_jitter_minutes > 0 or ready_at > not_before
        ):
            state.set_ready_at(order, ready_at)
            state.save_atomic(state_path(output_dir))
        if now < ready_at:
            results.append(
                BroadcastResult(order, label, "skipped", detail="broadcast jitter window")
            )
            continue

        if quiet_hours is not None and in_quiet_hours(now, quiet_hours):
            results.append(BroadcastResult(order, label, "skipped", detail="quiet hours"))
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
