"""Shared broadcast-time assignment logic (jitter, min-gap, quiet hours).

Extracted so `write_schedule` (initial `generate`) and `reschedule_schedule`
(retiming unbroadcast entries later) apply identical spacing rules without a
circular import between `yaml_manifest.py` and `reschedule.py`.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from coldcard_panic_drain.schedule.quiet_hours import QuietHours, next_allowed_time

# Floor between consecutive broadcast_not_before entries after jitter/quiet-hours
# adjustment, so a large negative jitter draw can never collapse two entries onto
# (or past) the same timestamp.
MIN_ENTRY_GAP = timedelta(minutes=15)


def assign_broadcast_times(
    count: int,
    *,
    spread_hours: float,
    schedule_jitter: float = 0.35,
    quiet_hours: Optional[QuietHours] = None,
    start: Optional[datetime] = None,
    rng: Optional[random.Random] = None,
) -> list[datetime]:
    """Return `count` monotonic broadcast timestamps spread across `spread_hours` from `start`.

    Each timestamp gets a uniform(-schedule_jitter, +schedule_jitter) offset of the
    per-entry step, is floored to `MIN_ENTRY_GAP` after its predecessor, and (if
    `quiet_hours` is set) is bumped past the quiet window with the floor re-applied.
    """
    rng = rng or random.Random()
    start = start or datetime.now(timezone.utc)
    if count <= 0:
        return []

    step = timedelta(hours=spread_hours / max(count, 1))
    times: list[datetime] = []
    last_assigned: Optional[datetime] = None

    for i in range(count):
        t = start + step * i
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
        times.append(t)

    return times
