"""Broadcast schedule YAML."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import yaml

from coldcard_panic_drain.schedule.quiet_hours import QuietHours, quiet_hours_to_dict
from coldcard_panic_drain.schedule.timing import MIN_ENTRY_GAP, assign_broadcast_times
from coldcard_panic_drain.broadcast.paths import signed_psbt_relpath
from coldcard_panic_drain.sparrow.models import DestinationAssignment

__all__ = ["MIN_ENTRY_GAP", "write_schedule"]


def write_schedule(
    path: Path,
    assignments: Iterable[DestinationAssignment],
    *,
    spread_hours: float,
    schedule_jitter: float = 0.35,
    quiet_hours: Optional[QuietHours] = None,
    rng: random.Random | None = None,
) -> list[dict]:
    """Write schedule.yaml; return entry dicts (for ICS export)."""
    rng = rng or random.Random()
    items = list(assignments)
    if not items:
        path.write_text("entries: []\n", encoding="utf-8")
        return []

    tiers: dict[int, list[DestinationAssignment]] = {}
    for a in items:
        tiers.setdefault(a.utxo.value_sats, []).append(a)
    ordered: list[DestinationAssignment] = []
    for _val, group in sorted(tiers.items(), key=lambda x: x[0], reverse=True):
        g = list(group)
        rng.shuffle(g)
        ordered.extend(g)

    now = datetime.now(timezone.utc)
    times = assign_broadcast_times(
        len(ordered),
        spread_hours=spread_hours,
        schedule_jitter=schedule_jitter,
        quiet_hours=quiet_hours,
        start=now,
        rng=rng,
    )
    entries: list[dict] = []

    for i, (a, t) in enumerate(zip(ordered, times)):
        entries.append(
            {
                "order": i + 1,
                "label": a.utxo.label,
                "unsigned": f"psbts/{a.psbt_filename}",
                "signed": signed_psbt_relpath(a.psbt_filename),
                "broadcast_not_before": t.isoformat(),
                "fee_sat_vb": a.fee_sat_vb,
                "nlocktime": a.nlocktime,
                "utxo_ref": a.utxo.ref,
            }
        )

    doc: dict = {
        "generated_at": now.isoformat(),
        "spread_hours": spread_hours,
        "schedule_jitter": schedule_jitter,
        "entries": entries,
    }
    qh_doc = quiet_hours_to_dict(quiet_hours)
    if qh_doc:
        doc["quiet_hours"] = qh_doc
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return entries
