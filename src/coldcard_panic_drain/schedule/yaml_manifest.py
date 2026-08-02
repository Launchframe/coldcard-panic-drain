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
from coldcard_panic_drain.sparrow.models import DestinationAssignment


def write_schedule(
    path: Path,
    assignments: Iterable[DestinationAssignment],
    *,
    spread_hours: float,
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
        if quiet_hours is not None:
            t = next_allowed_time(t, quiet_hours)
            if last_assigned is not None and t <= last_assigned:
                t = next_allowed_time(last_assigned + step, quiet_hours)
        last_assigned = t
        entries.append(
            {
                "order": i + 1,
                "label": a.utxo.label,
                "unsigned": f"psbts/{a.psbt_filename}",
                "signed": f"psbts_signed/{a.psbt_filename.replace('.psbt', '-signed.psbt')}",
                "broadcast_not_before": t.isoformat(),
                "fee_sat_vb": a.fee_sat_vb,
                "nlocktime": a.nlocktime,
                "utxo_ref": a.utxo.ref,
            }
        )

    doc: dict = {
        "generated_at": now.isoformat(),
        "spread_hours": spread_hours,
        "entries": entries,
    }
    qh_doc = quiet_hours_to_dict(quiet_hours)
    if qh_doc:
        doc["quiet_hours"] = qh_doc
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return entries
