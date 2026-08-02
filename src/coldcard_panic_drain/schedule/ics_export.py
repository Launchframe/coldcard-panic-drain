"""RFC 5545 calendar export for broadcast reminders."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _format_dt(dt: datetime, tz_name: str | None) -> tuple[str, str]:
    """Return (line_prefix, value) for DTSTART/DTEND."""
    if tz_name:
        local = dt.astimezone(ZoneInfo(tz_name))
        return f"DTSTART;TZID={tz_name}", local.strftime("%Y%m%dT%H%M%S")
    utc = dt.astimezone(timezone.utc)
    return "DTSTART", utc.strftime("%Y%m%dT%H%M%SZ")


def write_ics_calendar(
    path: Path,
    entries: Iterable[dict],
    *,
    batch_name: str,
    alarm_minutes: int = 15,
    event_minutes: int = 30,
    timezone: str | None = None,
) -> None:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Launchframe//coldcard-panic-drain//EN",
        "CALSCALE:GREGORIAN",
    ]
    for entry in entries:
        order = entry["order"]
        label = entry.get("label", "broadcast")
        signed = entry.get("signed", "")
        not_before = datetime.fromisoformat(entry["broadcast_not_before"])
        if not_before.tzinfo is None:
            not_before = not_before.replace(tzinfo=timezone.utc)
        end = not_before + timedelta(minutes=event_minutes)
        uid = f"{batch_name}-{order}@coldcard-panic-drain"
        desc = (
            f"Signed PSBT: {signed}\\n"
            "Manual: open in Sparrow and broadcast.\\n"
            "Auto: coldcard-panic-drain broadcast-due (local Core only)."
        )
        start_key, start_val = _format_dt(not_before, timezone)
        end_key = start_key.replace("START", "END")
        _, end_val = _format_dt(end, timezone)
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"{start_key}:{start_val}",
                f"{end_key}:{end_val}",
                f"SUMMARY:{_ics_escape(f'Broadcast: {label}')}",
                f"DESCRIPTION:{desc}",
            ]
        )
        if alarm_minutes > 0:
            lines.extend(
                [
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_ics_escape(f'Broadcast soon: {label}')}",
                    f"TRIGGER:-PT{alarm_minutes}M",
                    "END:VALARM",
                ]
            )
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def count_vevents(ics_text: str) -> int:
    return len(re.findall(r"^BEGIN:VEVENT", ics_text, re.MULTILINE))
