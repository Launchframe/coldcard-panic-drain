"""Plan mapping table display and plan review helpers."""

import io

import pytest

from coldcard_panic_drain.cli import _print_mapping_table
from coldcard_panic_drain.plan.mapper import build_assignments
from coldcard_panic_drain.plan.plan_review import PlanReviewState, run_mapping_review
from coldcard_panic_drain.psbt.fees import estimate_psbt_fee_sats
from coldcard_panic_drain.sparrow.models import UtxoRecord
from coldcard_panic_drain.util import format_amount, normalize_display_unit

from conftest import make_test_wallet, make_test_wallet_b


def _sample_assignments(fee_base=25, fee_jitter=0.0):
    source = make_test_wallet()
    dest = make_test_wallet_b()
    utxo = UtxoRecord(
        txid="ab" * 32,
        vout=0,
        value_sats=5_000_000,
        height=890_000,
        received_at=None,
        address="bc1qtest",
        derivation_path="m/84'/0'/0'/0/0",
        label="Coin A",
        included=True,
    )
    assignments = build_assignments(
        [utxo],
        dest,
        fee_base=fee_base,
        fee_jitter=fee_jitter,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    return [utxo], dest, assignments


def test_format_amount_btc_and_sats():
    assert format_amount(100_000_000, "btc") == "1.00000000"
    assert format_amount(12345, "sats") == "12,345"
    assert format_amount(12345, "sat") == "12,345"


def test_normalize_display_unit():
    assert normalize_display_unit("btc") == "btc"
    assert normalize_display_unit("SATS") == "sats"
    assert normalize_display_unit("sat") == "sats"
    with pytest.raises(ValueError, match="display must be"):
        normalize_display_unit("usd")


def test_estimate_psbt_fee_sats_matches_builder_assumption():
    assert estimate_psbt_fee_sats(25) == 3500


def test_print_mapping_table_shows_jittered_fees(capsys):
    import random

    from coldcard_panic_drain.util import derive_address_for_chain_index

    source = make_test_wallet()
    dest = make_test_wallet_b()
    utxos = []
    for i in range(4):
        utxos.append(
            UtxoRecord(
                txid=f"{i:064x}",
                vout=0,
                value_sats=1_000_000 * (i + 1),
                height=800_000,
                received_at=None,
                address=derive_address_for_chain_index(source.keystore, 0, i),
                derivation_path=f"m/84'/0'/0'/0/{i}",
                label=f"coin{i}",
                included=True,
            )
        )
    assignments = build_assignments(
        utxos,
        dest,
        fee_base=25,
        fee_jitter=0.15,
        chain_tip=900_000,
        min_blocks_apart=2,
        rng=random.Random(7),
    )
    fees = {a.fee_sats for a in assignments}
    assert len(fees) > 1

    _print_mapping_table(assignments, unit="sats")
    out = capsys.readouterr().out
    for fee in fees:
        assert f"{fee:,}" in out


def test_run_mapping_review_retries_on_typo():
    utxos, dest, assignments = _sample_assignments()
    state = PlanReviewState(
        assignments=assignments,
        fee_base=25,
        fee_jitter=0.0,
        amount_unit="sats",
        utxos=utxos,
        dest_wallet=dest,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    stdin = io.StringIO("o\nPROCEED\n")
    stdout = io.StringIO()
    table_prints = []

    def capture_table(assignments, *, unit):
        table_prints.append(len(assignments))

    run_mapping_review(
        state,
        print_mapping_table=capture_table,
        stdin=stdin,
        stdout=stdout,
        prompt=lambda *_a, **_k: "",
        echo=lambda *_a, **_k: None,
    )
    assert "Not recognized" in stdout.getvalue()
    assert len(table_prints) == 1


def test_run_mapping_review_aborts_on_eof_instead_of_looping_forever():
    utxos, dest, assignments = _sample_assignments()
    state = PlanReviewState(
        assignments=assignments,
        fee_base=25,
        fee_jitter=0.0,
        amount_unit="sats",
        utxos=utxos,
        dest_wallet=dest,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    stdin = io.StringIO("")  # closed/exhausted stdin: readline() returns "" forever
    stdout = io.StringIO()
    with pytest.raises(ValueError, match="mapping not confirmed"):
        run_mapping_review(
            state,
            print_mapping_table=lambda *_a, **_k: None,
            stdin=stdin,
            stdout=stdout,
            prompt=lambda *_a, **_k: "",
            echo=lambda *_a, **_k: None,
        )


def test_run_mapping_review_accepts_proceed():
    utxos, dest, assignments = _sample_assignments()
    state = PlanReviewState(
        assignments=assignments,
        fee_base=25,
        fee_jitter=0.0,
        amount_unit="sats",
        utxos=utxos,
        dest_wallet=dest,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    stdin = io.StringIO("PROCEED\n")
    stdout = io.StringIO()
    result = run_mapping_review(
        state,
        print_mapping_table=lambda *_a, **_k: None,
        stdin=stdin,
        stdout=stdout,
        prompt=lambda *_a, **_k: "",
        echo=lambda *_a, **_k: None,
    )
    assert result.fee_base == 25
    assert "OPTIONS" in stdout.getvalue()


def test_run_mapping_review_options_edits_fee_base():
    utxos, dest, assignments = _sample_assignments(fee_base=25)
    state = PlanReviewState(
        assignments=assignments,
        fee_base=25,
        fee_jitter=0.0,
        amount_unit="sats",
        utxos=utxos,
        dest_wallet=dest,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    stdin = io.StringIO("OPTIONS\nPROCEED\n")
    prompts = iter(["b", "50", "c"])

    def fake_prompt(*_args, **_kwargs):
        return next(prompts)

    result = run_mapping_review(
        state,
        print_mapping_table=lambda *_a, **_k: None,
        stdin=stdin,
        stdout=io.StringIO(),
        prompt=fake_prompt,
        echo=lambda *_a, **_k: None,
    )
    assert result.fee_base == 50
    assert result.assignments[0].fee_sat_vb == 50
    assert estimate_psbt_fee_sats(result.assignments[0].fee_sat_vb) == 7000


def test_run_mapping_review_options_changes_display_unit():
    utxos, dest, assignments = _sample_assignments()
    state = PlanReviewState(
        assignments=assignments,
        fee_base=25,
        fee_jitter=0.0,
        amount_unit="btc",
        utxos=utxos,
        dest_wallet=dest,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    stdin = io.StringIO("OPTIONS\nPROCEED\n")
    prompts = iter(["d", "sats", "c"])

    def fake_prompt(*_args, **_kwargs):
        return next(prompts)

    result = run_mapping_review(
        state,
        print_mapping_table=lambda *_a, **_k: None,
        stdin=stdin,
        stdout=io.StringIO(),
        prompt=fake_prompt,
        echo=lambda *_a, **_k: None,
    )
    assert result.amount_unit == "sats"
