"""Long-running --follow mode: replaces an hourly cron with a sleeping watcher.

The watcher never busy-loops: it sleeps in chunks of at most
`MAX_SLEEP_CHUNK_SECONDS` until the next entry's `broadcast_not_before` (plus
any runtime jitter draw already persisted in broadcast-state.yaml) or a
bounded fallback poll interval, whichever is sooner. Each chunk is further
split into ``INTERRUPTIBLE_SLEEP_SLICE_SECONDS`` slices so SIGINT/SIGTERM are
re-checked frequently; the loop exits within ~1s of interrupt instead of
blocking for the remainder of a long sleep.
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
from coldcard_panic_drain.schedule.load import load_schedule, schedule_quiet_hours
from coldcard_panic_drain.schedule.quiet_hours import in_quiet_hours, next_allowed_time

MAX_SLEEP_CHUNK_SECONDS = 60
INTERRUPTIBLE_SLEEP_SLICE_SECONDS = 1.0  # max latency from SIGINT to exit loop
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

    def __init__(self, on_request: Callable[[], None] | None = None) -> None:
        self.requested = False
        self._on_request = on_request

    def request(self, *_args: object) -> None:
        if self.requested:
            return
        self.requested = True
        if self._on_request is not None:
            self._on_request()


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
    respect_quiet_hours: bool = False,
) -> datetime:
    """Earliest time `run_broadcast_due` is worth calling again.

    Looks at every not-yet-broadcast schedule entry and takes the later of its
    `broadcast_not_before` and any persisted runtime-jitter `ready_at`. If the
    soonest such time is already in the past (e.g. blocked on a missing signed
    PSBT, or a jitter draw not yet made), falls back to `now + poll_interval`
    instead of returning a past/now timestamp — that fallback is what keeps
    --follow from spinning in a tight loop.

    When `respect_quiet_hours` is set and an entry is already due but `now`
    falls inside schedule.yaml's quiet window, the fallback is the quiet
    window's end instead of `now + poll_interval` — otherwise --follow would
    poll every `poll_interval` for the entire quiet window (e.g. every 60s for
    up to 8+ hours) instead of sleeping straight through it.
    """
    now = now or datetime.now(timezone.utc)
    sched_path = output_dir / "schedule.yaml"
    if not sched_path.is_file():
        return now + poll_interval

    doc = load_schedule(sched_path)
    state = BroadcastState.load(state_path(output_dir))
    quiet_hours = schedule_quiet_hours(doc) if respect_quiet_hours else None

    earliest: Optional[datetime] = None
    due_now = False
    for entry in doc.get("entries") or []:
        order = int(entry["order"])
        if state.is_broadcast(order):
            continue
        wake = _parse_not_before(entry["broadcast_not_before"])
        ready_at = state.get_ready_at(order)
        if ready_at is not None and ready_at > wake:
            wake = ready_at
        if wake <= now:
            due_now = True
            continue
        if earliest is None or wake < earliest:
            earliest = wake

    if quiet_hours is not None and due_now and in_quiet_hours(now, quiet_hours):
        quiet_end = next_allowed_time(now, quiet_hours)
        if earliest is None or quiet_end < earliest:
            return quiet_end

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
        chunk = min(remaining, MAX_SLEEP_CHUNK_SECONDS)
        slept = 0.0
        while slept < chunk and not flag.requested:
            slice_seconds = min(
                INTERRUPTIBLE_SLEEP_SLICE_SECONDS, chunk - slept
            )
            sleep_fn(slice_seconds)
            slept += slice_seconds


def run_broadcast_follow(
    output_dir: Path,
    rpc: CoreRpcClient,
    *,
    max_count: int = 1,
    dry_run: bool = False,
    skip_failed: bool = False,
    broadcast_jitter_minutes: int = DEFAULT_BROADCAST_JITTER_MINUTES,
    respect_quiet_hours: bool = False,
    rng: Optional[random.Random] = None,
    on_results: Optional[Callable[[list[BroadcastResult]], None]] = None,
    on_heartbeat: Optional[Callable[[str], None]] = None,
    on_shutdown_request: Callable[[], None] | None = None,
    shutdown_flag: Optional[ShutdownFlag] = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """Replace an hourly cron with a single sleeping process.

    Each iteration calls `run_broadcast_due(max_count=max_count)` — identical
    logic to a cron invocation — then sleeps (in <=60s chunks, each split into
    ~1s interruptible slices) until the next entry is actually worth
    checking. `max_count` defaults to 1 (one broadcast per wake) since the
    loop runs indefinitely anyway; pass a higher value to drain multiple due
    entries per iteration instead of waiting out the sleep between each one.
    Install a `shutdown_flag` for tests; production callers get
    SIGINT/SIGTERM wired up automatically.
    """
    flag = shutdown_flag or ShutdownFlag(on_request=on_shutdown_request)
    if shutdown_flag is None:
        install_signal_handlers(flag)

    while not flag.requested:
        results = run_broadcast_due(
            output_dir,
            rpc,
            max_count=max_count,
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

        wake = compute_next_broadcast_wake(
            output_dir, now, respect_quiet_hours=respect_quiet_hours
        )
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
