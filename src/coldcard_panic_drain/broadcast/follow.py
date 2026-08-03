"""Long-running --follow mode: replaces an hourly cron with a sleeping watcher.

The watcher never busy-loops: it sleeps in chunks of at most
`MAX_SLEEP_CHUNK_SECONDS` until the next entry's `broadcast_not_before` (plus
any runtime jitter draw already persisted in broadcast-state.yaml) or a
bounded fallback poll interval, whichever is sooner. SIGINT/SIGTERM set a
shutdown flag that is checked between sleep chunks, so the loop exits within
one chunk instead of blocking for the remainder of a long sleep.
"""

from __future__ import annotations

import random
import signal
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from coldcard_panic_drain.broadcast.core_rpc import CoreRpcClient
from coldcard_panic_drain.broadcast.runner import (
    DEFAULT_BROADCAST_JITTER_MINUTES,
    BroadcastResult,
    _parse_not_before,
    run_broadcast_due,
)
from coldcard_panic_drain.broadcast.state import BroadcastState, state_path
from coldcard_panic_drain.schedule.load import load_schedule

MAX_SLEEP_CHUNK_SECONDS = 60
DEFAULT_POLL_INTERVAL = timedelta(seconds=60)


def _iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="seconds")


def format_follow_heartbeat(
    now: datetime,
    wake: datetime,
    *,
    phase: str,
    detail: str = "",
) -> str:
    """Single-line UTC heartbeat for --follow stderr (now/wake as ISO8601)."""
    parts = [f"{_iso_utc(now)} follow {phase} wake={_iso_utc(wake)}"]
    if detail:
        parts.append(detail)
    return " ".join(parts)


def _summarize_check_results(results: list[BroadcastResult]) -> str:
    if not results:
        return "no due entries"
    first = results[0]
    return f"{first.action} order {first.order}"


class ShutdownFlag:
    """Mutable flag toggled by a signal handler (or a test) to stop the loop."""

    def __init__(self) -> None:
        self.requested = False

    def request(self, *_args: object) -> None:
        self.requested = True


def install_signal_handlers(flag: ShutdownFlag) -> None:
    """Route SIGINT/SIGTERM to `flag` so the loop exits gracefully.

    Registering signal handlers only works on the main thread; silently skip
    if unavailable (e.g. running inside a test worker thread) rather than
    crashing --follow startup.
    """
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, flag.request)
        except (ValueError, OSError):
            pass


def compute_next_broadcast_wake(
    output_dir: Path,
    now: Optional[datetime] = None,
    *,
    poll_interval: timedelta = DEFAULT_POLL_INTERVAL,
) -> datetime:
    """Earliest time `run_broadcast_due` is worth calling again.

    Looks at every not-yet-broadcast schedule entry and takes the later of its
    `broadcast_not_before` and any persisted runtime-jitter `ready_at`. If the
    soonest such time is already in the past (e.g. blocked on quiet hours, a
    missing signed PSBT, or a jitter draw not yet made), falls back to
    `now + poll_interval` instead of returning a past/now timestamp — that
    fallback is what keeps --follow from spinning in a tight loop.
    """
    now = now or datetime.now(timezone.utc)
    sched_path = output_dir / "schedule.yaml"
    if not sched_path.is_file():
        return now + poll_interval

    doc = load_schedule(sched_path)
    state = BroadcastState.load(state_path(output_dir))

    earliest: Optional[datetime] = None
    for entry in doc.get("entries") or []:
        order = int(entry["order"])
        if state.is_broadcast(order):
            continue
        wake = _parse_not_before(entry["broadcast_not_before"])
        ready_at = state.get_ready_at(order)
        if ready_at is not None and ready_at > wake:
            wake = ready_at
        if wake <= now:
            continue
        if earliest is None or wake < earliest:
            earliest = wake

    if earliest is None:
        return now + poll_interval
    return earliest


def _sleep_until(
    wake: datetime,
    *,
    now_fn: Callable[[], datetime],
    sleep_fn: Callable[[float], None],
    flag: ShutdownFlag,
    on_heartbeat: Optional[Callable[[str], None]] = None,
) -> None:
    while not flag.requested:
        now = now_fn()
        remaining = (wake - now).total_seconds()
        if remaining <= 0:
            return
        if on_heartbeat is not None:
            on_heartbeat(
                format_follow_heartbeat(
                    now, wake, phase="heartbeat", detail="still waiting"
                )
            )
        sleep_fn(min(remaining, MAX_SLEEP_CHUNK_SECONDS))


def run_broadcast_follow(
    output_dir: Path,
    rpc: CoreRpcClient,
    *,
    dry_run: bool = False,
    skip_failed: bool = False,
    broadcast_jitter_minutes: int = DEFAULT_BROADCAST_JITTER_MINUTES,
    respect_quiet_hours: bool = False,
    rng: Optional[random.Random] = None,
    on_results: Optional[Callable[[list[BroadcastResult]], None]] = None,
    on_heartbeat: Optional[Callable[[str], None]] = None,
    shutdown_flag: Optional[ShutdownFlag] = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """Replace an hourly cron with a single sleeping process.

    Each iteration calls `run_broadcast_due(max_count=1)` — identical
    single-shot logic to a cron invocation — then sleeps (in <=60s chunks)
    until the next entry is actually worth checking. Install a
    `shutdown_flag` for tests; production callers get SIGINT/SIGTERM wired
    up automatically.
    """
    flag = shutdown_flag or ShutdownFlag()
    if shutdown_flag is None:
        install_signal_handlers(flag)

    while not flag.requested:
        results = run_broadcast_due(
            output_dir,
            rpc,
            max_count=1,
            dry_run=dry_run,
            skip_failed=skip_failed,
            broadcast_jitter_minutes=broadcast_jitter_minutes,
            respect_quiet_hours=respect_quiet_hours,
            rng=rng,
        )
        if on_results is not None:
            on_results(results)

        now = now_fn()
        if on_heartbeat is not None:
            on_heartbeat(
                format_follow_heartbeat(
                    now,
                    now,
                    phase="checked",
                    detail=_summarize_check_results(results),
                )
            )

        if flag.requested:
            break

        wake = compute_next_broadcast_wake(output_dir, now)
        if on_heartbeat is not None:
            seconds_until = max(0, int((wake - now).total_seconds()))
            on_heartbeat(
                format_follow_heartbeat(
                    now,
                    wake,
                    phase="sleeping",
                    detail=f"{seconds_until}s until wake",
                )
            )
        _sleep_until(
            wake,
            now_fn=now_fn,
            sleep_fn=sleep_fn,
            flag=flag,
            on_heartbeat=on_heartbeat,
        )
