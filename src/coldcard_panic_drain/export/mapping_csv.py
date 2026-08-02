"""CSV mapping export."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from coldcard_panic_drain.sparrow.models import DestinationAssignment, LabelSource, UtxoRecord


def write_mapping_csv(
    path: Path,
    assignments: Iterable[DestinationAssignment],
    all_utxos: Iterable[UtxoRecord],
) -> None:
    assignment_by_ref = {a.utxo.ref: a for a in assignments}
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "utxo_ref",
                "label",
                "label_source",
                "status",
                "skip_reason",
                "dest_address",
                "dest_index",
                "fee_sat_vb",
                "psbt_file",
            ]
        )
        for u in all_utxos:
            if u.included and not u.frozen and u.ref in assignment_by_ref:
                a = assignment_by_ref[u.ref]
                src = u.label_source.value if u.label_source else LabelSource.EXISTING.value
                w.writerow(
                    [
                        u.ref,
                        u.label,
                        src,
                        "included",
                        "",
                        a.address,
                        a.receive_index,
                        a.fee_sat_vb,
                        a.psbt_filename,
                    ]
                )
            else:
                reason = ""
                if u.frozen or u.skip_reason:
                    reason = (u.skip_reason.value if u.skip_reason else "frozen")
                w.writerow(
                    [
                        u.ref,
                        u.label,
                        u.label_source.value if u.label_source else "",
                        "skipped",
                        reason,
                        "",
                        "",
                        "",
                        "",
                    ]
                )
