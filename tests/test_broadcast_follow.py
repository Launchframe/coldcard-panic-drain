"""--follow mode: next-wake computation and graceful shutdown tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from coldcard_panic_drain.broadcast.follow import (
    DEFAULT_POLL_INTERVAL,
    INTERRUPTIBLE_SLEEP_SLICE_SECONDS,
    MAX_SLEEP_CHUNK_SECONDS,
    ShutdownFlag,
    _sleep_detail_for_wake,
    _sleep_until,
    _summarize_check_results,
    compute_next_broadcast_wake,
    format_follow_heartbeat,
    run_broadcast_follow,
)
from coldcard_panic_drain.broadcast.runner import BroadcastResult
from coldcard_panic_drain.broadcast.state import BroadcastState, state_path


def _write_schedule(tmp_path: Path, entries: list[dict]) -> None:
    (tmp_path / "schedule.yaml").write_text(
        yaml.safe_dump({"entries": entries}), encoding="utf-8"
    )


def _entry(order: int, not_before: datetime, label: str = "coin") -> dict:
    return {
        "order": order,
        "label": label,
        "signed": f"psbts_signed/{label}-signed.psbt",
        "broadcast_not_before": not_before.isoformat(),
    }


def test_format_follow_heartbeat_uses_utc_iso_timestamps():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    wake = datetime(2026, 1, 1, 13, 30, 0, tzinfo=timezone.utc)
    msg = format_follow_heartbeat(
        now, wake, phase="sleeping", detail="5400s until wake"
    )
    assert msg.startswith("2026-01-01T12:00:00+00:00 follow sleeping")
    assert "wake=2026-01-01T13:30:00+00:00" in msg
    assert msg.endswith("5400s until wake")


def test_run_broadcast_follow_emits_checked_and_sleeping_heartbeats(
    tmp_path: Path, monkeypatch
):
    heartbeats: list[str] = []
    flag = ShutdownFlag()

    def fake_sleep(_seconds: float) -> None:
        flag.requested = True

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        lambda output_dir, rpc, **kwargs: [],
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        shutdown_flag=flag,
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
        on_heartbeat=heartbeats.append,
    )

    assert any(" follow checked " in h for h in heartbeats)
    assert any(" follow sleeping " in h for h in heartbeats)
    assert any("no due entries" in h for h in heartbeats)


def test_run_broadcast_follow_checked_heartbeat_summarizes_first_result(
    tmp_path: Path, monkeypatch
):
    heartbeats: list[str] = []
    flag = ShutdownFlag()
    result = BroadcastResult(3, "coin", "broadcast")

    def fake_sleep(_seconds: float) -> None:
        flag.requested = True

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        lambda output_dir, rpc, **kwargs: [result],
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        shutdown_flag=flag,
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
        on_heartbeat=heartbeats.append,
    )

    assert any("broadcast order 3" in h for h in heartbeats)


def test_sleep_chunks_emit_heartbeat_when_on_heartbeat_provided(
    tmp_path: Path, monkeypatch
):
    clock = {"now": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    not_before = clock["now"] + timedelta(seconds=150)
    _write_schedule(tmp_path, [_entry(1, not_before)])

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        lambda output_dir, rpc, **kwargs: [],
    )

    flag = ShutdownFlag()
    heartbeats: list[str] = []

    def fake_sleep(seconds: float) -> None:
        clock["now"] += timedelta(seconds=seconds)
        if len([h for h in heartbeats if " follow heartbeat " in h]) >= 2:
            flag.requested = True

    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        shutdown_flag=flag,
        now_fn=lambda: clock["now"],
        sleep_fn=fake_sleep,
        on_heartbeat=heartbeats.append,
    )

    heartbeat_lines = [h for h in heartbeats if " follow heartbeat " in h]
    assert len(heartbeat_lines) >= 2
    assert all("still waiting" in h for h in heartbeat_lines)


def test_compute_next_wake_falls_back_to_poll_interval_without_schedule(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert compute_next_broadcast_wake(tmp_path, now) == now + DEFAULT_POLL_INTERVAL


def test_compute_next_wake_uses_not_before_when_in_future(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    not_before = now + timedelta(hours=3)
    _write_schedule(tmp_path, [_entry(1, not_before)])
    assert compute_next_broadcast_wake(tmp_path, now) == not_before


def test_compute_next_wake_prefers_later_persisted_ready_at(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    not_before = now + timedelta(hours=1)
    ready_at = now + timedelta(hours=2)
    _write_schedule(tmp_path, [_entry(1, not_before)])
    state = BroadcastState()
    state.set_ready_at(1, ready_at)
    state.save_atomic(state_path(tmp_path))

    assert compute_next_broadcast_wake(tmp_path, now) == ready_at


def test_compute_next_wake_ignores_ready_at_earlier_than_not_before(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    not_before = now + timedelta(hours=2)
    ready_at = now + timedelta(hours=1)  # stale/earlier draw; not_before wins
    _write_schedule(tmp_path, [_entry(1, not_before)])
    state = BroadcastState()
    state.set_ready_at(1, ready_at)
    state.save_atomic(state_path(tmp_path))

    assert compute_next_broadcast_wake(tmp_path, now) == not_before


def test_compute_next_wake_falls_back_when_due_but_blocked(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Already due (e.g. blocked on missing signature, quiet hours, or a jitter
    # draw not yet made) — must not return a past/now timestamp.
    _write_schedule(tmp_path, [_entry(1, now - timedelta(minutes=5))])
    assert compute_next_broadcast_wake(tmp_path, now) == now + DEFAULT_POLL_INTERVAL


def test_compute_next_wake_ignores_already_broadcast_entries(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    not_before = now + timedelta(hours=1)
    _write_schedule(tmp_path, [_entry(1, not_before)])
    state = BroadcastState()
    state.mark_broadcast(1, "aa" * 32)
    state.save_atomic(state_path(tmp_path))

    assert compute_next_broadcast_wake(tmp_path, now) == now + DEFAULT_POLL_INTERVAL


def test_compute_next_wake_picks_earliest_of_multiple_pending_entries(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    soon = now + timedelta(minutes=30)
    later = now + timedelta(hours=5)
    _write_schedule(tmp_path, [_entry(1, later, "b"), _entry(2, soon, "a")])
    assert compute_next_broadcast_wake(tmp_path, now) == soon


def _write_schedule_with_quiet_hours(
    tmp_path: Path, entries: list[dict], *, start: str, end: str, tz: str = "UTC"
) -> None:
    (tmp_path / "schedule.yaml").write_text(
        yaml.safe_dump(
            {
                "entries": entries,
                "quiet_hours": {"start": start, "end": end, "timezone": tz},
            }
        ),
        encoding="utf-8",
    )


def test_summarize_check_results_quiet_hours_skips():
    results = [
        BroadcastResult(1, "coin-a", "skipped", detail="quiet hours"),
        BroadcastResult(2, "coin-b", "skipped", detail="quiet hours"),
    ]
    assert _summarize_check_results(results) == "quiet hours — 2 due entries held"


def test_sleep_detail_for_wake_acknowledges_quiet_hours(tmp_path: Path):
    now = datetime(2026, 1, 1, 23, 0, 0, tzinfo=timezone.utc)
    _write_schedule_with_quiet_hours(
        tmp_path,
        [_entry(1, now - timedelta(minutes=5))],
        start="22:00",
        end="08:00",
    )
    wake = datetime(2026, 1, 2, 8, 0, 0, tzinfo=timezone.utc)
    detail = _sleep_detail_for_wake(
        tmp_path,
        now,
        wake,
        respect_quiet_hours=True,
    )
    assert "quiet hours until 08:00 (UTC)" in detail
    assert "sleeping" in detail
    assert "32400s" in detail


def test_sleep_detail_for_wake_generic_when_not_quiet_hours(tmp_path: Path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    wake = now + timedelta(minutes=5)
    detail = _sleep_detail_for_wake(
        tmp_path,
        now,
        wake,
        respect_quiet_hours=True,
    )
    assert detail == "300s until wake"


def test_run_broadcast_follow_sleeping_heartbeat_acknowledges_quiet_hours(
    tmp_path: Path, monkeypatch
):
    heartbeats: list[str] = []
    flag = ShutdownFlag()
    now = datetime(2026, 1, 1, 23, 0, 0, tzinfo=timezone.utc)
    _write_schedule_with_quiet_hours(
        tmp_path,
        [_entry(1, now - timedelta(minutes=5))],
        start="22:00",
        end="08:00",
    )

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        lambda output_dir, rpc, **kwargs: [
            BroadcastResult(1, "coin", "skipped", detail="quiet hours")
        ],
    )

    def fake_sleep(_seconds: float) -> None:
        flag.requested = True

    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        respect_quiet_hours=True,
        shutdown_flag=flag,
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
        on_heartbeat=heartbeats.append,
    )

    assert any("quiet hours — 1 due entry held" in h for h in heartbeats)
    assert any(
        "quiet hours until 08:00 (UTC)" in h and " follow sleeping " in h
        for h in heartbeats
    )


def test_compute_next_wake_bumps_to_quiet_hours_end_when_due_but_blocked(tmp_path: Path):
    # 23:00 UTC is inside a 22:00->08:00 quiet window; the entry is already
    # due (broadcast_not_before in the past), so without quiet-hours
    # awareness this would fall back to `now + poll_interval` (60s) and keep
    # polling every minute for hours instead of sleeping through the window.
    now = datetime(2026, 1, 1, 23, 0, 0, tzinfo=timezone.utc)
    _write_schedule_with_quiet_hours(
        tmp_path,
        [_entry(1, now - timedelta(minutes=5))],
        start="22:00",
        end="08:00",
    )
    wake = compute_next_broadcast_wake(tmp_path, now, respect_quiet_hours=True)
    assert wake == datetime(2026, 1, 2, 8, 0, 0, tzinfo=timezone.utc)


def test_compute_next_wake_ignores_quiet_hours_unless_respect_quiet_hours_set(
    tmp_path: Path,
):
    now = datetime(2026, 1, 1, 23, 0, 0, tzinfo=timezone.utc)
    _write_schedule_with_quiet_hours(
        tmp_path,
        [_entry(1, now - timedelta(minutes=5))],
        start="22:00",
        end="08:00",
    )
    # respect_quiet_hours defaults to False: unchanged short poll fallback.
    assert compute_next_broadcast_wake(tmp_path, now) == now + DEFAULT_POLL_INTERVAL


def test_compute_next_wake_quiet_hours_does_not_delay_entry_not_yet_due(tmp_path: Path):
    # A future entry landing outside the quiet window is unaffected even
    # with respect_quiet_hours=True.
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    not_before = now + timedelta(hours=1)
    _write_schedule_with_quiet_hours(
        tmp_path, [_entry(1, not_before)], start="22:00", end="08:00"
    )
    assert (
        compute_next_broadcast_wake(tmp_path, now, respect_quiet_hours=True)
        == not_before
    )


def test_run_broadcast_follow_stops_on_shutdown_flag(tmp_path: Path, monkeypatch):
    calls = {"run": 0, "sleep": 0}

    def fake_run_broadcast_due(output_dir, rpc, **kwargs):
        calls["run"] += 1
        return []

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due", fake_run_broadcast_due
    )
    flag = ShutdownFlag()

    def fake_sleep(seconds: float) -> None:
        calls["sleep"] += 1
        flag.requested = True

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        shutdown_flag=flag,
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
    )
    assert calls["run"] == 1
    assert calls["sleep"] == 1


def test_run_broadcast_follow_skips_run_broadcast_due_if_already_shutdown(
    tmp_path: Path, monkeypatch
):
    called = {"run": False}

    def fake_run_broadcast_due(*args, **kwargs):
        called["run"] = True
        return []

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due", fake_run_broadcast_due
    )
    flag = ShutdownFlag()
    flag.requested = True

    run_broadcast_follow(tmp_path, MagicMock(), shutdown_flag=flag)

    assert called["run"] is False


def test_run_broadcast_follow_sleeps_in_chunks_of_at_most_60s(tmp_path: Path, monkeypatch):
    clock = {"now": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    not_before = clock["now"] + timedelta(seconds=150)
    _write_schedule(tmp_path, [_entry(1, not_before)])

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        lambda output_dir, rpc, **kwargs: [],
    )

    flag = ShutdownFlag()
    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock["now"] += timedelta(seconds=seconds)
        if len(sleep_calls) >= 5:
            flag.requested = True

    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        shutdown_flag=flag,
        now_fn=lambda: clock["now"],
        sleep_fn=fake_sleep,
    )

    assert sleep_calls, "expected at least one sleep chunk before shutdown"
    assert all(s <= MAX_SLEEP_CHUNK_SECONDS for s in sleep_calls)
    # The 150s wake cannot be reached in a single <=60s chunk.
    assert len(sleep_calls) >= 2


def test_run_broadcast_follow_forwards_results_to_on_results(tmp_path: Path, monkeypatch):
    seen: list[list] = []
    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        lambda output_dir, rpc, **kwargs: ["fake-result"],
    )
    flag = ShutdownFlag()

    def fake_sleep(_seconds: float) -> None:
        flag.requested = True

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        shutdown_flag=flag,
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
        on_results=seen.append,
    )
    assert seen == [["fake-result"]]


def test_sleep_until_exits_within_one_slice_after_shutdown_flag():
    wake = datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    flag = ShutdownFlag()
    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) == 2:
            flag.request()

    _sleep_until(
        wake,
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
        flag=flag,
    )

    assert len(sleep_calls) == 2
    assert all(s <= INTERRUPTIBLE_SLEEP_SLICE_SECONDS for s in sleep_calls)
    assert flag.requested


def test_shutdown_flag_on_request_called_once():
    calls = {"n": 0}
    flag = ShutdownFlag(on_request=lambda: calls.__setitem__("n", calls["n"] + 1))
    flag.request()
    flag.request()
    assert calls["n"] == 1


def test_run_broadcast_follow_forwards_max_count_to_run_broadcast_due(
    tmp_path: Path, monkeypatch
):
    captured_kwargs: dict = {}

    def fake_run_broadcast_due(output_dir, rpc, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        fake_run_broadcast_due,
    )
    flag = ShutdownFlag()

    def fake_sleep(_seconds: float) -> None:
        flag.requested = True

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        max_count=5,
        shutdown_flag=flag,
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
    )

    assert captured_kwargs["max_count"] == 5


def test_run_broadcast_follow_forwards_respect_quiet_hours_to_compute_wake(
    tmp_path: Path, monkeypatch
):
    captured_kwargs: dict = {}
    real_compute = compute_next_broadcast_wake

    def spy_compute(output_dir, now=None, **kwargs):
        captured_kwargs.update(kwargs)
        return real_compute(output_dir, now, **kwargs)

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        lambda output_dir, rpc, **kwargs: [],
    )
    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.compute_next_broadcast_wake",
        spy_compute,
    )
    flag = ShutdownFlag()

    def fake_sleep(_seconds: float) -> None:
        flag.requested = True

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        respect_quiet_hours=True,
        shutdown_flag=flag,
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
    )

    assert captured_kwargs["respect_quiet_hours"] is True


def test_run_broadcast_follow_calls_on_shutdown_request(tmp_path: Path, monkeypatch):
    calls: list[int] = []
    captured: dict[str, ShutdownFlag] = {}

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        lambda output_dir, rpc, **kwargs: [],
    )

    def capture_handlers(flag: ShutdownFlag) -> None:
        captured["flag"] = flag

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.install_signal_handlers",
        capture_handlers,
    )

    def fake_sleep(_seconds: float) -> None:
        captured["flag"].request()

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
        on_shutdown_request=lambda: calls.append(1),
    )

    assert calls == [1]
