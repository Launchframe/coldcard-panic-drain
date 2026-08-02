"""BIP-329 JSONL label export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from coldcard_panic_drain.sparrow.models import DestinationAssignment, UtxoRecord, WalletSnapshot


def _line(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def write_wallet_b_labels(
    path: Path,
    assignments: Iterable[DestinationAssignment],
    dest_wallet: WalletSnapshot,
) -> None:
    ks = dest_wallet.keystore
    lines = []
    for a in assignments:
        lines.append(
            _line(
                {
                    "type": "addr",
                    "ref": a.address,
                    "label": a.utxo.label,
                    "origin": ks.origin,
                    "keypath": f"/0/{a.receive_index}",
                }
            )
        )
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_wallet_a_labels(
    path: Path,
    assignments: Iterable[DestinationAssignment],
    source_wallet: WalletSnapshot,
) -> None:
    ks = source_wallet.keystore
    lines = []
    for a in assignments:
        # keypath from utxo derivation: m/84'/0'/0'/0/N -> /0/N
        parts = a.utxo.derivation_path.split("/")
        keypath = f"/{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else ""
        lines.append(
            _line(
                {
                    "type": "output",
                    "ref": a.utxo.ref,
                    "label": a.utxo.label,
                    "origin": ks.origin,
                    "keypath": keypath,
                    "value": a.utxo.value_sats,
                }
            )
        )
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
