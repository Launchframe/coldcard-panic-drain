"""Mapping review gate at plan."""

import io
import json
from pathlib import Path

import pytest

from coldcard_panic_drain.plan.session import DrainSession
from coldcard_panic_drain.verify.mapping import MAPPING_ACK, confirm_mapping_review


def test_confirm_mapping_review_accepts_proceed():
    stdin = io.StringIO(MAPPING_ACK + "\n")
    stdout = io.StringIO()
    confirm_mapping_review(3, stdin=stdin, stdout=stdout)
    assert "3 PSBTs" in stdout.getvalue()
    assert "Wallet A" in stdout.getvalue()


def test_confirm_mapping_review_rejects_wrong_ack():
    stdin = io.StringIO("CONFIRM\n")
    stdout = io.StringIO()
    with pytest.raises(ValueError, match="mapping not confirmed"):
        confirm_mapping_review(1, stdin=stdin, stdout=stdout)


def test_require_plan_gates_rejects_missing_mapping():
    session = DrainSession(
        source_path="/tmp/a.mv.db",
        dest_path="/tmp/b.mv.db",
        chain_tip_height=900_000,
        fee_base=25,
        fee_jitter=0.0,
        min_blocks_apart=2,
        spread_hours=48.0,
        mapping_confirmed=False,
        dest_ownership_confirmed=True,
    )
    with pytest.raises(ValueError, match="mapping was not confirmed"):
        session.require_plan_gates()


def test_session_load_accepts_legacy_addresses_confirmed(tmp_path: Path):
    data = {
        "source_path": "/tmp/a.mv.db",
        "dest_path": "/tmp/b.mv.db",
        "chain_tip_height": 900_000,
        "fee_base": 25,
        "fee_jitter": 0.0,
        "min_blocks_apart": 2,
        "spread_hours": 48.0,
        "addresses_confirmed": True,
        "dest_ownership_confirmed": True,
    }
    path = tmp_path / "labels-session.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    session = DrainSession.load(path)
    assert session.mapping_confirmed is True
    session.require_plan_gates()
