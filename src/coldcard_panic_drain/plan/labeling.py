"""Interactive labeling for unlabeled UTXOs."""

from __future__ import annotations

import sys
from typing import TextIO

from coldcard_panic_drain.export.warnings import print_frozen_utxo_warning
from coldcard_panic_drain.sparrow.models import LabelSource, SkipReason, UtxoRecord
from coldcard_panic_drain.util import sats_to_btc_str


def apply_frozen_exclusions(utxos: list[UtxoRecord]) -> None:
    for u in utxos:
        if u.frozen:
            u.included = False
            u.skip_reason = SkipReason.FROZEN
            print_frozen_utxo_warning(u)


def prompt_for_labels(
    utxos: list[UtxoRecord],
    *,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> None:
    unlabeled = [u for u in utxos if u.included and not u.frozen and not u.label.strip()]
    total = len(unlabeled)
    for i, u in enumerate(unlabeled, start=1):
        received = u.received_at.strftime("%Y-%m-%d") if u.received_at else "unknown"
        retry = False
        while True:
            if retry:
                stdout.write("  Enter label (or 'skip' to exclude from this batch): ")
            else:
                stdout.write(
                    f"\nUnlabeled UTXO {i} of {total}\n"
                    f"  Ref:      {u.ref}\n"
                    f"  Amount:   {sats_to_btc_str(u.value_sats)} BTC ({u.value_sats:,} sats)\n"
                    f"  Received: {received} (block {u.height:,})\n"
                    f"  Address:  {u.address}  ({u.derivation_path})\n\n"
                    f"  Enter label (or 'skip' to exclude from this batch): "
                )
            stdout.flush()
            line = stdin.readline().strip()
            if line.lower() == "skip":
                u.included = False
                u.skip_reason = SkipReason.USER_SKIPPED
                break
            if line.lower() in ("exit", "q"):
                raise ValueError("Aborted: labeling not completed.")
            if not line:
                retry = True
                continue
            u.label = line
            u.label_source = LabelSource.USER_PROMPTED
            break


def validate_ready_for_generate(utxos: list[UtxoRecord]) -> None:
    for u in utxos:
        if u.frozen:
            continue
        if not u.included:
            continue
        if not u.label.strip():
            raise RuntimeError(
                f"UTXO {u.ref} is unlabeled and not skipped. Re-run `plan` to label or skip it."
            )
