"""Mandatory Wallet B ownership verification."""

import io

import pytest

from coldcard_panic_drain.plan.session import DrainSession
from coldcard_panic_drain.verify.ownership import OWNERSHIP_ACK, confirm_dest_wallet_ownership

from conftest import make_test_wallet_b


def test_confirm_dest_wallet_ownership_accepts_exact_ack():
    dest = make_test_wallet_b(used_receive_indices=[0, 1])
    stdin = io.StringIO(OWNERSHIP_ACK + "\n")
    stdout = io.StringIO()
    index = confirm_dest_wallet_ownership(dest, stdin=stdin, stdout=stdout)
    assert index == 2
    assert "Next receive index: 2" in stdout.getvalue()


def test_confirm_dest_wallet_ownership_rejects_wrong_ack():
    dest = make_test_wallet_b()
    stdin = io.StringIO("CONFIRM\n")
    stdout = io.StringIO()
    with pytest.raises(ValueError, match="ownership not confirmed"):
        confirm_dest_wallet_ownership(dest, stdin=stdin, stdout=stdout)


def test_confirm_dest_wallet_ownership_shows_wallet_identity():
    dest = make_test_wallet_b(name="staging-wallet")
    stdin = io.StringIO(OWNERSHIP_ACK + "\n")
    stdout = io.StringIO()
    confirm_dest_wallet_ownership(dest, stdin=stdin, stdout=stdout)
    out = stdout.getvalue()
    assert "staging-wallet" in out
    assert dest.keystore.fingerprint in out
    assert "Wallet B ownership check" in out


def test_require_plan_gates_rejects_missing_ownership():
    session = DrainSession(
        source_path="/tmp/a.mv.db",
        dest_path="/tmp/b.mv.db",
        chain_tip_height=900_000,
        fee_base=25,
        fee_jitter=0.0,
        min_blocks_apart=2,
        spread_hours=48.0,
        addresses_confirmed=True,
        dest_ownership_confirmed=False,
    )
    with pytest.raises(ValueError, match="ownership was not confirmed"):
        session.require_plan_gates()


def test_require_plan_gates_rejects_missing_address_confirm():
    session = DrainSession(
        source_path="/tmp/a.mv.db",
        dest_path="/tmp/b.mv.db",
        chain_tip_height=900_000,
        fee_base=25,
        fee_jitter=0.0,
        min_blocks_apart=2,
        spread_hours=48.0,
        addresses_confirmed=False,
        dest_ownership_confirmed=True,
    )
    with pytest.raises(ValueError, match="addresses were not confirmed"):
        session.require_plan_gates()


def test_require_plan_gates_passes_when_both_confirmed():
    session = DrainSession(
        source_path="/tmp/a.mv.db",
        dest_path="/tmp/b.mv.db",
        chain_tip_height=900_000,
        fee_base=25,
        fee_jitter=0.0,
        min_blocks_apart=2,
        spread_hours=48.0,
        addresses_confirmed=True,
        dest_ownership_confirmed=True,
    )
    session.require_plan_gates()
