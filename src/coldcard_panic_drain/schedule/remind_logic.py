"""Remind command logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from coldcard_panic_drain.broadcast.paths import signed_path_under_output
from coldcard_panic_drain.broadcast.state import BroadcastState, state_path
from coldcard_panic_drain.schedule.load import load_schedule, schedule_quiet_hours
from coldcard_panic_drain.schedule.quiet_hours import in_quiet_hours, quiet_hours_end_display


@dataclass
class RemindStatus:
    message: str


def compute_remind_status(output_dir: Path, now: Optional[datetime] = None) -> RemindStatus:
    now = now or datetime.now(timezone.utc)
    doc = load_schedule(output_dir / "schedule.yaml")
    qh = schedule_quiet_hours(doc)
    state = BroadcastState.load(state_path(output_dir))
    entries = sorted(doc.get("entries") or [], key=lambda e: e.get("order", 0))

    next_upcoming = None
    for entry in entries:
        order = int(entry["order"])
        if state.is_broadcast(order):
            continue
        not_before = datetime.fromisoformat(entry["broadcast_not_before"])
        if not_before.tzinfo is None:
            not_before = not_before.replace(tzinfo=timezone.utc)
        try:
            signed_path = signed_path_under_output(output_dir, entry.get("signed", ""))
            has_signed = signed_path.is_file()
        except ValueError:
            has_signed = False

        if now < not_before:
            if next_upcoming is None:
                next_upcoming = (entry, not_before, has_signed)
            continue

        if not has_signed:
            return RemindStatus(
                f"Waiting for signature: {entry.get('label')} → {entry.get('signed')}"
            )

        if qh and in_quiet_hours(now, qh):
            end = quiet_hours_end_display(now, qh)
            return RemindStatus(
                f"Due now but quiet hours until {end} ({qh.timezone}). "
                "Auto-broadcast via broadcast-due is unaffected."
            )
        return RemindStatus(
            f"READY TO BROADCAST: {entry.get('label')} → {entry.get('signed')}\n"
            f"  Scheduled from: {entry['broadcast_not_before']}"
        )

    if next_upcoming:
        entry, not_before, has_signed = next_upcoming
        delta = not_before - now
        hours = int(delta.total_seconds() // 3600)
        mins = int((delta.total_seconds() % 3600) // 60)
        sig = "signed PSBT ready" if has_signed else "needs signing first"
        return RemindStatus(
            f"Next: {entry.get('label')} in {hours}h {mins}m ({sig})"
        )
    return RemindStatus("All scheduled entries broadcast or none pending.")
