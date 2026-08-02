"""Mapping review gate at plan — no device verification until PSBT signing."""

from __future__ import annotations

import sys
from typing import TextIO

MAPPING_ACK = "PROCEED"


def confirm_mapping_review(
    assignment_count: int,
    *,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> None:
    """Prompt operator to accept or abort the UTXO → destination mapping.

    Destination addresses are not verified on a hardware device here. Signing-time
    checks on Wallet A's Coldcard and Sparrow Wallet B are the operator's responsibility.
    """
    stdout.write(
        "\n"
        "=== Mapping review ===\n"
        "Review the table above. This tool cannot verify destination addresses at "
        "signing time — a wrong address would cause irreversible loss.\n\n"
        "After `generate`, sign each PSBT on Wallet A's Coldcard. Before signing "
        "each transaction, verify the destination address on the device and confirm "
        "it appears as a receive address in Sparrow Wallet B.\n"
        f"({assignment_count} PSBTs will be generated.)\n\n"
        f"Type {MAPPING_ACK} to save this mapping, or Ctrl+C to abort: "
    )
    stdout.flush()
    line = stdin.readline().strip()
    if line != MAPPING_ACK:
        raise ValueError(
            "Aborted: mapping not confirmed. "
            f"Type exactly {MAPPING_ACK} after reviewing the mapping table."
        )
