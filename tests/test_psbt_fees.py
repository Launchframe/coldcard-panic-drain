"""PSBT fee jitter helpers."""

import random

from coldcard_panic_drain.plan.mapper import build_assignments
from coldcard_panic_drain.psbt.fees import jittered_assignment_fees
from coldcard_panic_drain.sparrow.models import UtxoRecord
from coldcard_panic_drain.util import derive_address_for_chain_index

from conftest import make_test_wallet, make_test_wallet_b


def test_jittered_assignment_fees_extreme_jitter_never_below_one_sat_vb():
    rng = random.Random(1)
    for _ in range(100):
        fee_sats, fee_sat_vb = jittered_assignment_fees(1, 1.5, rng)
        assert fee_sats >= 140
        assert fee_sat_vb >= 1


def test_jittered_assignment_fees_low_base_varies_absolute_fee():
    rng = random.Random(0)
    fees = {jittered_assignment_fees(1, 0.12, rng)[0] for _ in range(20)}
    assert len(fees) > 1
    assert fees.issubset(range(140, 158))


def test_jittered_assignment_fees_floor_bound_base_spreads_uniformly():
    rng = random.Random(3)
    fees = [jittered_assignment_fees(1, 0.3, rng)[0] for _ in range(15)]
    assert min(fees) >= 140
    assert max(fees) <= 182
    assert len(set(fees)) >= 10


def test_build_assignments_low_fee_base_shows_jitter_in_fee_sats():
    source = make_test_wallet()
    dest = make_test_wallet_b()
    utxos = [
        UtxoRecord(
            txid=f"{i:064x}",
            vout=0,
            value_sats=5_000_000,
            height=800_000,
            received_at=None,
            address=derive_address_for_chain_index(source.keystore, 0, i),
            derivation_path=f"m/84'/0'/0'/0/{i}",
            label=f"coin{i}",
            included=True,
        )
        for i in range(6)
    ]
    assignments = build_assignments(
        utxos,
        dest,
        fee_base=1,
        fee_jitter=0.12,
        chain_tip=900_000,
        min_blocks_apart=2,
        rng=random.Random(5),
    )
    fees = {a.fee_sats for a in assignments}
    assert len(fees) > 1
    assert min(fees) >= 140
    assert max(fees) <= 157
