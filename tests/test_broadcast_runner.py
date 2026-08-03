"""Broadcast runner helpers and safety tests."""

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

import pytest

from coldcard_panic_drain.broadcast.core_rpc import CoreRpcError
from coldcard_panic_drain.broadcast.runner import _signed_tx_hex, run_broadcast_due
from coldcard_panic_drain.broadcast.state import BroadcastState, state_path


def test_signed_tx_hex_normalizes_bytes_txid(tmp_path: Path):
    mock_tx = MagicMock()
    mock_tx.txid.return_value = b"\xab" * 32
    mock_tx.serialize.return_value.hex.return_value = "deadbeef"
    path = tmp_path / "signed.psbt"
    path.write_bytes(b"psbt")
    with patch("coldcard_panic_drain.broadcast.runner.PSBT.parse"):
        with patch("coldcard_panic_drain.broadcast.runner.finalize_psbt", return_value=mock_tx):
            txid, raw_hex = _signed_tx_hex(path)
    assert isinstance(txid, str)
    assert len(txid) == 64
    assert txid == (b"\xab" * 32).hex()
    assert raw_hex == "deadbeef"


def _write_schedule(tmp_path: Path, signed_rel: str) -> None:
    doc = {
        "entries": [
            {
                "order": 1,
                "label": "coin",
                "signed": signed_rel,
                "broadcast_not_before": datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(),
            }
        ]
    }
    (tmp_path / "schedule.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _seed_signed_dir(tmp_path: Path) -> None:
    signed_dir = tmp_path / "psbts_signed"
    signed_dir.mkdir()
    (signed_dir / "placeholder-signed.psbt").write_bytes(b"psbt")


def _seed_signed_file(tmp_path: Path, name: str = "coin-signed.psbt") -> None:
    """Seed psbts_signed/<name> so the schedule entry's signed PSBT resolves and exists."""
    signed_dir = tmp_path / "psbts_signed"
    signed_dir.mkdir(exist_ok=True)
    (signed_dir / name).write_bytes(b"psbt")


def test_run_broadcast_due_requires_psbts_signed_dir(tmp_path: Path):
    _write_schedule(tmp_path, "psbts_signed/coin-signed.psbt")
    with pytest.raises(ValueError, match="Missing psbts_signed/"):
        run_broadcast_due(tmp_path, MagicMock(), max_count=1)


def test_run_broadcast_due_requires_nonempty_psbts_signed_dir(tmp_path: Path):
    _write_schedule(tmp_path, "psbts_signed/coin-signed.psbt")
    (tmp_path / "psbts_signed").mkdir()
    with pytest.raises(ValueError, match="contains no .psbt files"):
        run_broadcast_due(tmp_path, MagicMock(), max_count=1)


def test_run_broadcast_due_dry_run_skips_signed_dir_check(tmp_path: Path):
    _write_schedule(tmp_path, "psbts_signed/coin-signed.psbt")
    results = run_broadcast_due(tmp_path, MagicMock(), max_count=1, dry_run=True)
    assert len(results) == 1
    assert results[0].action == "skipped"
    assert "missing" in results[0].detail


def test_rejects_signed_path_outside_output_dir(tmp_path: Path):
    _write_schedule(tmp_path, "../../../etc/passwd")
    _seed_signed_dir(tmp_path)
    rpc = MagicMock()
    results = run_broadcast_due(tmp_path, rpc, max_count=1)
    assert len(results) == 1
    assert results[0].action == "skipped"
    assert "escapes" in results[0].detail
    rpc.send_raw_transaction.assert_not_called()


def test_rejects_absolute_signed_path(tmp_path: Path):
    _write_schedule(tmp_path, "/tmp/evil-signed.psbt")
    _seed_signed_dir(tmp_path)
    rpc = MagicMock()
    results = run_broadcast_due(tmp_path, rpc, max_count=1)
    assert results[0].action == "skipped"
    assert "relative" in results[0].detail


def _mock_broadcast_rpc() -> MagicMock:
    rpc = MagicMock()
    rpc.get_raw_transaction.return_value = None
    rpc.test_mempool_accept.return_value = [{"allowed": True}]
    rpc.send_raw_transaction.return_value = "aa" * 32
    return rpc


def _patch_signed_tx_hex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.runner._signed_tx_hex",
        lambda path: ("aa" * 32, "deadbeef"),
    )


def test_broadcast_jitter_draws_and_persists_ready_at(tmp_path: Path, monkeypatch):
    _write_schedule(tmp_path, "psbts_signed/coin-signed.psbt")
    _seed_signed_file(tmp_path)
    _patch_signed_tx_hex(monkeypatch)
    rpc = _mock_broadcast_rpc()

    run_broadcast_due(
        tmp_path, rpc, max_count=1, broadcast_jitter_minutes=90, rng=random.Random(1)
    )
    ready_at = BroadcastState.load(state_path(tmp_path)).get_ready_at(1)
    assert ready_at is not None
    not_before = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert not_before <= ready_at <= not_before + timedelta(minutes=90)


def test_broadcast_jitter_minutes_zero_disables_gate_and_ready_at(tmp_path: Path, monkeypatch):
    _write_schedule(tmp_path, "psbts_signed/coin-signed.psbt")
    _seed_signed_file(tmp_path)
    _patch_signed_tx_hex(monkeypatch)
    rpc = _mock_broadcast_rpc()

    results = run_broadcast_due(tmp_path, rpc, max_count=1, broadcast_jitter_minutes=0)
    assert results[0].action == "broadcast"
    rpc.send_raw_transaction.assert_called_once()
    assert BroadcastState.load(state_path(tmp_path)).get_ready_at(1) is None


def test_broadcast_jitter_gate_skips_until_ready_at(tmp_path: Path):
    _write_schedule(tmp_path, "psbts_signed/coin-signed.psbt")
    _seed_signed_file(tmp_path)
    future_ready = datetime.now(timezone.utc) + timedelta(hours=1)
    state = BroadcastState()
    state.set_ready_at(1, future_ready)
    state.save_atomic(state_path(tmp_path))

    rpc = MagicMock()
    results = run_broadcast_due(tmp_path, rpc, max_count=1, broadcast_jitter_minutes=90)
    assert len(results) == 1
    assert results[0].action == "skipped"
    assert results[0].detail == "broadcast jitter window"
    rpc.send_raw_transaction.assert_not_called()

    # Gate check must not consume or alter the persisted draw.
    reloaded = BroadcastState.load(state_path(tmp_path))
    assert reloaded.get_ready_at(1) == future_ready


def test_broadcast_jitter_gate_allows_broadcast_once_ready_at_passed(
    tmp_path: Path, monkeypatch
):
    _write_schedule(tmp_path, "psbts_signed/coin-signed.psbt")
    _seed_signed_file(tmp_path)
    past_ready = datetime.now(timezone.utc) - timedelta(minutes=1)
    state = BroadcastState()
    state.set_ready_at(1, past_ready)
    state.save_atomic(state_path(tmp_path))
    _patch_signed_tx_hex(monkeypatch)
    rpc = _mock_broadcast_rpc()

    results = run_broadcast_due(tmp_path, rpc, max_count=1, broadcast_jitter_minutes=90)
    assert results[0].action == "broadcast"
    rpc.send_raw_transaction.assert_called_once()


def test_broadcast_jitter_ready_at_not_rerolled_on_retry_after_failure(
    tmp_path: Path, monkeypatch
):
    _write_schedule(tmp_path, "psbts_signed/coin-signed.psbt")
    _seed_signed_file(tmp_path)
    _patch_signed_tx_hex(monkeypatch)
    rpc = MagicMock()
    rpc.get_raw_transaction.return_value = None
    rpc.test_mempool_accept.side_effect = CoreRpcError("mempool full")

    run_broadcast_due(
        tmp_path, rpc, max_count=1, broadcast_jitter_minutes=90, rng=random.Random(1)
    )
    first_ready = BroadcastState.load(state_path(tmp_path)).get_ready_at(1)
    assert first_ready is not None

    # Retry with a different rng — the persisted draw must not be re-rolled.
    run_broadcast_due(
        tmp_path, rpc, max_count=1, broadcast_jitter_minutes=90, rng=random.Random(999)
    )
    second_ready = BroadcastState.load(state_path(tmp_path)).get_ready_at(1)
    assert second_ready == first_ready


def _quiet_hours_schedule_doc() -> dict:
    return {
        # Overnight window with start == end covers the full day (see
        # in_quiet_hours' overnight branch), avoiding test flakiness from
        # wall-clock timing.
        "quiet_hours": {"start": "00:00", "end": "00:00", "timezone": "UTC"},
        "entries": [
            {
                "order": 1,
                "label": "coin",
                "signed": "psbts_signed/coin-signed.psbt",
                "broadcast_not_before": datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(),
            }
        ],
    }


def test_respect_quiet_hours_skips_in_quiet_window(tmp_path: Path):
    (tmp_path / "schedule.yaml").write_text(
        yaml.safe_dump(_quiet_hours_schedule_doc()), encoding="utf-8"
    )
    _seed_signed_file(tmp_path)
    rpc = MagicMock()

    results = run_broadcast_due(
        tmp_path, rpc, max_count=1, broadcast_jitter_minutes=0, respect_quiet_hours=True
    )
    assert results[0].action == "skipped"
    assert results[0].detail == "quiet hours"
    rpc.send_raw_transaction.assert_not_called()


def test_respect_quiet_hours_off_by_default_ignores_quiet_hours(tmp_path: Path, monkeypatch):
    (tmp_path / "schedule.yaml").write_text(
        yaml.safe_dump(_quiet_hours_schedule_doc()), encoding="utf-8"
    )
    _seed_signed_file(tmp_path)
    _patch_signed_tx_hex(monkeypatch)
    rpc = _mock_broadcast_rpc()

    results = run_broadcast_due(tmp_path, rpc, max_count=1, broadcast_jitter_minutes=0)
    assert results[0].action == "broadcast"
