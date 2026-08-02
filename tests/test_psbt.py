"""PSBT builder tests."""

from coldcard_panic_drain.plan.mapper import build_assignments, derive_receive_address
from coldcard_panic_drain.psbt.builder import build_psbt, psbt_sha256
from coldcard_panic_drain.sparrow.models import UtxoRecord
from embit.psbt import PSBT

from conftest import make_test_wallet


def _fixtures():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet(path="/tmp/b.mv.db", name="b")
    utxo = UtxoRecord(
        txid="ab" * 32,
        vout=1,
        value_sats=5_000_000,
        height=890_000,
        received_at=None,
        address=derive_receive_address(source, 0),
        derivation_path="m/84'/0'/0'/0/0",
        label="Drain me",
        included=True,
    )
    source.utxos = [utxo]
    assignments = build_assignments(
        [utxo],
        dest,
        fee_base=25,
        fee_jitter=0,
        chain_tip=900_000,
        min_blocks_apart=2,
        rng=__import__("random").Random(1),
    )
    return source, assignments[0]


def test_build_psbt_structure():
    source, assignment = _fixtures()
    raw = build_psbt(assignment, source)
    assert len(psbt_sha256(raw)) == 64
    psbt = PSBT.parse(raw)
    assert len(psbt.inputs) == 1
    assert len(psbt.outputs) == 1
    assert psbt.tx.locktime == assignment.nlocktime
    assert psbt.inputs[0].witness_utxo is not None
    assert psbt.inputs[0].witness_utxo.value == assignment.utxo.value_sats
