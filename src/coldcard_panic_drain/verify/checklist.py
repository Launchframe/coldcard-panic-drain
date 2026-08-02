"""Coldcard verification checklist."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from coldcard_panic_drain.sparrow.models import DestinationAssignment, WalletSnapshot


def write_verification_checklist(
    path: Path,
    assignments: Iterable[DestinationAssignment],
    dest_wallet: WalletSnapshot,
    *,
    ownership_checked_index: int | None = None,
) -> None:
    account = dest_wallet.keystore.derivation_path.rstrip("/")
    lines = [
        "Coldcard address verification checklist (Wallet B)",
        f"Account: {account}",
        "",
    ]
    if ownership_checked_index is not None and ownership_checked_index >= 0:
        lines.extend(
            [
                f"Ownership verified at plan for receive index {ownership_checked_index} "
                "(Sparrow Wallet B file matches signing device).",
                "",
            ]
        )
    lines.extend(
        [
            "On Coldcard: Advanced → View Identity → Address → verify each index:",
            "",
        ]
    )
    for a in assignments:
        lines.append(f'Index {a.receive_index} | Label: "{a.utxo.label}"')
        lines.append(f"Address: {a.address}")
        lines.append(f"Path:    {account}/0/{a.receive_index}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
