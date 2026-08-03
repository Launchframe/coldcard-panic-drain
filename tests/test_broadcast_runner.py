"""Broadcast runner helpers and safety tests."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

import pytest

from coldcard_panic_drain.broadcast.runner import _signed_tx_hex, run_broadcast_due


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
