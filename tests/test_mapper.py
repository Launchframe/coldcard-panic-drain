"""Mapper and util tests."""

from coldcard_panic_drain.plan.mapper import build_assignments, derive_receive_address
from coldcard_panic_drain.sparrow.models import UtxoRecord
from coldcard_panic_drain.sparrow.receive import next_free_receive_index, used_receive_sets
from coldcard_panic_drain.util import derive_address_for_chain_index, sanitize_label

from conftest import make_test_wallet


def test_sanitize_label():
    assert sanitize_label("Salary March!") == "salary-march"
    assert sanitize_label("   ") == "utxo"


def test_derive_receive_address():
    w = make_test_wallet()
    addr0 = derive_receive_address(w, 0)
    assert addr0.startswith("bc1")


def test_next_receive_index_skips_used_and_fills_gaps():
    from conftest import make_test_wallet_b

    assert make_test_wallet_b(used_receive_indices=[0, 1]).next_receive_index == 2
    assert make_test_wallet_b(used_receive_indices=[0, 2]).next_receive_index == 1


def test_build_assignments_skips_used_receive_indices():
    from conftest import make_test_wallet_b

    dest = make_test_wallet_b(used_receive_indices=[0])
    source = make_test_wallet()
    utxo = UtxoRecord(
        txid="a" * 64,
        vout=0,
        value_sats=1_000_000,
        height=800_000,
        received_at=None,
        address=derive_receive_address(source, 0),
        derivation_path="m/84'/0'/0'/0/0",
        label="coin",
        included=True,
    )
    assignments = build_assignments(
        [utxo],
        dest,
        fee_base=20,
        fee_jitter=0,
        chain_tip=900_000,
        min_blocks_apart=3,
        rng=__import__("random").Random(0),
    )
    assert assignments[0].receive_index == 1
    assert assignments[0].address == derive_receive_address(dest, 1)


def test_build_assignments_skips_used_receive_address_even_if_index_missing():
    from conftest import make_test_wallet_b

    dest = make_test_wallet_b(used_receive_indices=[0])
    used_addr_1 = derive_receive_address(dest, 1)
    dest = make_test_wallet_b(
        used_receive_indices=[0],
        used_receive_addresses=[used_addr_1],
    )
    source = make_test_wallet()
    utxo = UtxoRecord(
        txid="b" * 64,
        vout=0,
        value_sats=500_000,
        height=800_000,
        received_at=None,
        address=derive_receive_address(source, 0),
        derivation_path="m/84'/0'/0'/0/0",
        label="coin",
        included=True,
    )
    assignments = build_assignments(
        [utxo],
        dest,
        fee_base=20,
        fee_jitter=0,
        chain_tip=900_000,
        min_blocks_apart=3,
        rng=__import__("random").Random(0),
    )
    assert assignments[0].receive_index == 2
    assert assignments[0].address == derive_receive_address(dest, 2)


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
