"""PSBT signing checklist — verify destinations when signing on Wallet A."""

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
    lines = [
        "PSBT signing checklist (Wallet A — verify before each signature)",
        "",
        "For EACH PSBT in psbts/:",
        "  1. Load the file on Wallet A Coldcard (Ready to Sign).",
        "  2. Verify the destination address matches mapping.csv and the entry below.",
        "  3. In Sparrow Wallet B, confirm the address appears as a receive address.",
        "  4. Verify amount and fee before approving.",
        "",
        "Do NOT sign if the destination does not match Wallet B.",
        "",
    ]
    if ownership_checked_index is not None and ownership_checked_index >= 0:
        lines.extend(
            [
                f"Wallet B ownership was verified at plan (receive index "
                f"{ownership_checked_index}; Sparrow file matches signing device).",
                "",
            ]
        )
    lines.append("Reference mapping:")
    lines.append("")
    for a in assignments:
        lines.append(f"PSBT: {a.psbt_filename}")
        lines.append(f'Label: "{a.utxo.label}"')
        lines.append(f"Wallet B receive index {a.receive_index}: {a.address}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
