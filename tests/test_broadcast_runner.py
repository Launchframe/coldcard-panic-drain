"""Broadcast runner helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from coldcard_panic_drain.broadcast.runner import _signed_tx_hex


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
    assert isinstance(txid, str)
    assert raw_hex == "deadbeef"
