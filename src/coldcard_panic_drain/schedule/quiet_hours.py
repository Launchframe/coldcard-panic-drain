"""Quiet-hours scheduling for manual broadcast reminders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class QuietHours:
    start: str  # HH:MM
    end: str  # HH:MM
    timezone: str

    def validate(self) -> None:
        _parse_hhmm(self.start)
        _parse_hhmm(self.end)
        try:
            ZoneInfo(self.timezone)
        except KeyError as e:
            raise ValueError(f"Invalid timezone {self.timezone!r}") from e


def _parse_hhmm(s: str) -> time:
    parts = s.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time {s!r}; expected HH:MM")
    h, m = int(parts[0]), int(parts[1])
    return time(h, m)


def in_quiet_hours(dt: datetime, qh: QuietHours) -> bool:
    """True if dt (aware UTC) falls inside quiet window in qh.timezone."""
    tz = ZoneInfo(qh.timezone)
    local = dt.astimezone(tz)
    t = local.timetz().replace(tzinfo=None)
    start = _parse_hhmm(qh.start)
    end = _parse_hhmm(qh.end)
    if start < end:
        return start <= t < end
    # overnight e.g. 22:00 -> 08:00
    return t >= start or t < end


def next_allowed_time(dt: datetime, qh: QuietHours) -> datetime:
    """Bump dt forward to qh.end if currently inside quiet hours (local tz)."""
    if not in_quiet_hours(dt, qh):
        return dt
    tz = ZoneInfo(qh.timezone)
    local = dt.astimezone(tz)
    end = _parse_hhmm(qh.end)
    candidate = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def quiet_hours_end_display(dt: datetime, qh: QuietHours) -> str:
    """Human-readable end of current quiet period."""
    tz = ZoneInfo(qh.timezone)
    local = dt.astimezone(tz)
    end = _parse_hhmm(qh.end)
    candidate = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.strftime("%H:%M")


def parse_quiet_hours(
    dnd_start: Optional[str],
    dnd_end: Optional[str],
    tz_name: Optional[str],
) -> Optional[QuietHours]:
    if not dnd_start and not dnd_end and not tz_name:
        return None
    if not dnd_start or not dnd_end or not tz_name:
        raise ValueError("--dnd-start, --dnd-end, and --timezone must all be set together.")
    qh = QuietHours(start=dnd_start, end=dnd_end, timezone=tz_name)
    qh.validate()
    return qh


def quiet_hours_to_dict(qh: Optional[QuietHours]) -> Optional[dict[str, str]]:
    if qh is None:
        return None
    return {"start": qh.start, "end": qh.end, "timezone": qh.timezone}


def quiet_hours_from_dict(data: Optional[dict]) -> Optional[QuietHours]:
    if not data:
        return None
    return QuietHours(start=data["start"], end=data["end"], timezone=data["timezone"])
