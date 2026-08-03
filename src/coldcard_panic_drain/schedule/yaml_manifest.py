"""Broadcast schedule YAML."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import yaml

from coldcard_panic_drain.schedule.quiet_hours import (
    QuietHours,
    next_allowed_time,
    quiet_hours_to_dict,
)
from coldcard_panic_drain.broadcast.paths import signed_psbt_relpath
from coldcard_panic_drain.sparrow.models import DestinationAssignment

# Floor between consecutive broadcast_not_before entries after jitter/quiet-hours
# adjustment, so a large negative jitter draw can never collapse two entries onto
# (or past) the same timestamp.
MIN_ENTRY_GAP = timedelta(minutes=15)


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
    step = timedelta(hours=spread_hours / max(len(ordered), 1))
    entries: list[dict] = []
    last_assigned: Optional[datetime] = None

    for i, a in enumerate(ordered):
        t = now + step * i
        if schedule_jitter:
            offset_seconds = rng.uniform(-schedule_jitter, schedule_jitter) * step.total_seconds()
            t = t + timedelta(seconds=offset_seconds)
        if last_assigned is not None and t < last_assigned + MIN_ENTRY_GAP:
            t = last_assigned + MIN_ENTRY_GAP
        if quiet_hours is not None:
            t = next_allowed_time(t, quiet_hours)
            if last_assigned is not None and t < last_assigned + MIN_ENTRY_GAP:
                t = next_allowed_time(last_assigned + MIN_ENTRY_GAP, quiet_hours)
        last_assigned = t
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
