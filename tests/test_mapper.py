"""Mapper and util tests."""

from coldcard_panic_drain.plan.mapper import build_assignments, derive_receive_address
from coldcard_panic_drain.sparrow.models import UtxoRecord
from coldcard_panic_drain.util import sanitize_label

from conftest import make_test_wallet


def test_sanitize_label():
    assert sanitize_label("Salary March!") == "salary-march"
    assert sanitize_label("   ") == "utxo"


def test_derive_receive_address():
    w = make_test_wallet()
    addr0 = derive_receive_address(w, 0)
    assert addr0.startswith("bc1")


def test_build_assignments_fee_jitter():
    w = make_test_wallet()
    utxo = UtxoRecord(
        txid="a" * 64,
        vout=0,
        value_sats=1_000_000,
        height=800_000,
        received_at=None,
        address=derive_receive_address(w, 0),
        derivation_path="m/84'/0'/0'/0/0",
        label="Test Coin",
        included=True,
    )
    assignments = build_assignments(
        [utxo],
        w,
        fee_base=20,
        fee_jitter=0.1,
        chain_tip=900_000,
        min_blocks_apart=3,
        rng=__import__("random").Random(0),
    )
    assert len(assignments) == 1
    a = assignments[0]
    assert a.fee_sat_vb >= 18
    assert a.nlocktime == 900_003
    assert a.psbt_filename.endswith(".psbt")
