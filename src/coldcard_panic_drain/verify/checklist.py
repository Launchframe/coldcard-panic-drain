"""PSBT signing checklist — verify destinations when signing on Wallet A."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from coldcard_panic_drain.psbt.fees import assignment_fee_sats
from coldcard_panic_drain.sparrow.models import DestinationAssignment, WalletSnapshot
from coldcard_panic_drain.util import sats_to_btc_str


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
        "Before signing: copy each .psbt from psbts/ to the ROOT of the microSD card.",
        "Ready to Sign does not scan subdirectories on the card.",
        "After signing: copy each *-signed.psbt into psbts_signed/ on this output volume.",
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
        fee_sats = assignment_fee_sats(a)
        output_sats = a.utxo.value_sats - fee_sats
        lines.append(f"PSBT: {a.psbt_filename}")
        lines.append(f'Label: "{a.utxo.label}"')
        lines.append(f"Input:  {sats_to_btc_str(a.utxo.value_sats)} BTC")
        lines.append(f"Fee:    {sats_to_btc_str(fee_sats)} BTC")
        lines.append(f"Output: {sats_to_btc_str(output_sats)} BTC")
        lines.append(f"Wallet B receive index {a.receive_index}: {a.address}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
