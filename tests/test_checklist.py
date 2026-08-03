"""Checklist includes ownership verification note."""

from pathlib import Path

from coldcard_panic_drain.plan.mapper import build_assignments, derive_receive_address
from coldcard_panic_drain.sparrow.models import UtxoRecord
from coldcard_panic_drain.verify.checklist import write_verification_checklist

from conftest import make_test_wallet, make_test_wallet_b


def test_checklist_includes_signing_instructions(tmp_path: Path):
    source = make_test_wallet(path="/tmp/a.mv.db")
    dest = make_test_wallet_b(path="/tmp/b.mv.db")
    utxo = UtxoRecord(
        txid="ab" * 32,
        vout=0,
        value_sats=1_000_000,
        height=890_000,
        received_at=None,
        address=derive_receive_address(source, 0),
        derivation_path="m/84'/0'/0'/0/0",
        label="test",
        included=True,
    )
    assignments = build_assignments(
        [utxo],
        dest,
        fee_base=25,
        fee_jitter=0,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    path = tmp_path / "checklist.txt"
    write_verification_checklist(path, assignments, dest, ownership_checked_index=0)
    text = path.read_text(encoding="utf-8")
    assert "Wallet A" in text
    assert "mapping.csv" in text
    assert "Wallet B ownership was verified at plan" in text
    assert assignments[0].psbt_filename in text
    fee_sats = assignments[0].fee_sats
    output_sats = utxo.value_sats - fee_sats
    assert f"Input:  {utxo.value_sats / 100_000_000:.8f} BTC" in text
    assert f"Fee:    {fee_sats / 100_000_000:.8f} BTC" in text
    assert f"Output: {output_sats / 100_000_000:.8f} BTC" in text
