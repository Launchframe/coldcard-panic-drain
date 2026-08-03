"""Reschedule unbroadcast entries in schedule.yaml without re-planning or re-signing.

Used after `generate` + signing when the user wants to change broadcast timing
(e.g. spread it out further, or shift it later) for whatever hasn't gone out
yet. Entries already marked `status=broadcast` in broadcast-state.yaml keep
their original `broadcast_not_before` untouched; PSBTs, labels, and fees are
never touched here.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from coldcard_panic_drain.broadcast.state import BroadcastState, state_path
from coldcard_panic_drain.schedule.load import load_schedule, schedule_quiet_hours
from coldcard_panic_drain.schedule.quiet_hours import QuietHours
from coldcard_panic_drain.schedule.timing import assign_broadcast_times

DEFAULT_SCHEDULE_JITTER = 0.35


@dataclass
class RescheduleResult:
    """Summary of a reschedule run. Labels only — no addresses/amounts, safe to log/echo."""

    rescheduled_count: int
    skipped_broadcast_count: int
    pending_orders: list[int]
    old_times: dict[int, datetime]
    new_times: dict[int, datetime]
    labels: dict[int, str] = field(default_factory=dict)


def compute_rescheduled_times(
    pending_count: int,
    *,
    spread_hours: float,
    schedule_jitter: float = DEFAULT_SCHEDULE_JITTER,
    quiet_hours: Optional[QuietHours] = None,
    start: Optional[datetime] = None,
    rng: Optional[random.Random] = None,
) -> list[datetime]:
    """Return `pending_count` new broadcast timestamps spread across `spread_hours` from `start`."""
    return assign_broadcast_times(
        pending_count,
        spread_hours=spread_hours,
        schedule_jitter=schedule_jitter,
        quiet_hours=quiet_hours,
        start=start,
        rng=rng,
    )


def _atomic_write_yaml(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    os.replace(tmp, path)


def reschedule_schedule(
    output_dir: Path,
    *,
    spread_hours: float,
    schedule_jitter: Optional[float] = None,
    shuffle_pending: bool = False,
    dry_run: bool = False,
    rng: Optional[random.Random] = None,
) -> RescheduleResult:
    """Recompute broadcast_not_before for every not-yet-broadcast schedule.yaml entry.

    Broadcast entries (per broadcast-state.yaml) are left untouched. Pending
    entries (including previously-`failed` ones, which the user may retry) get
    fresh times spread across `spread_hours` starting now. Any persisted
    runtime-jitter `ready_at` for a rescheduled order is cleared so
    `broadcast-due` re-draws it against the new `broadcast_not_before`.

    `schedule_jitter=None` reads the value already in schedule.yaml, falling
    back to `DEFAULT_SCHEDULE_JITTER` if absent.
    """
    rng = rng or random.Random()
    sched_path = output_dir / "schedule.yaml"
    doc = load_schedule(sched_path)
    entries = list(doc.get("entries") or [])
    quiet_hours = schedule_quiet_hours(doc)
    if schedule_jitter is None:
        schedule_jitter = doc.get("schedule_jitter", DEFAULT_SCHEDULE_JITTER)

    state = BroadcastState.load(state_path(output_dir))

    old_times: dict[int, datetime] = {}
    labels: dict[int, str] = {}
    pending_entries: list[dict] = []
    skipped_broadcast_count = 0

    for entry in entries:
        order = int(entry["order"])
        labels[order] = entry.get("label", "")
        old_times[order] = datetime.fromisoformat(entry["broadcast_not_before"])
        if state.is_broadcast(order):
            skipped_broadcast_count += 1
            continue
        pending_entries.append(entry)

    if shuffle_pending:
        rng.shuffle(pending_entries)

    now = datetime.now(timezone.utc)
    new_times_list = assign_broadcast_times(
        len(pending_entries),
        spread_hours=spread_hours,
        schedule_jitter=schedule_jitter,
        quiet_hours=quiet_hours,
        start=now,
        rng=rng,
    )

    pending_orders: list[int] = []
    new_times: dict[int, datetime] = {}
    for entry, t in zip(pending_entries, new_times_list):
        order = int(entry["order"])
        pending_orders.append(order)
        new_times[order] = t

    result = RescheduleResult(
        rescheduled_count=len(pending_orders),
        skipped_broadcast_count=skipped_broadcast_count,
        pending_orders=pending_orders,
        old_times={o: old_times[o] for o in pending_orders},
        new_times=new_times,
        labels=labels,
    )
    if dry_run:
        return result

    for entry in entries:
        order = int(entry["order"])
        if order in new_times:
            entry["broadcast_not_before"] = new_times[order].isoformat()

    doc["entries"] = entries
    doc["rescheduled_at"] = now.isoformat()
    doc["spread_hours"] = spread_hours
    doc["schedule_jitter"] = schedule_jitter
    _atomic_write_yaml(sched_path, doc)

    state_changed = False
    for order in pending_orders:
        if state.get_ready_at(order) is not None:
            state.clear_ready_at(order)
            state_changed = True
    if state_changed:
        state.save_atomic(state_path(output_dir))

    return result
