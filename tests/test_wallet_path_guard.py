"""Tests for real-wallet path guard."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from coldcard_panic_drain.sparrow.h2_reader import _query_rows
from coldcard_panic_drain.wallet_path_guard import (
    REAL_WALLET_ENV,
    RealWalletBlockedError,
    assert_wallet_path_allowed,
    disable_wallet_path_guard,
    enable_cli_wallet_access,
    enable_wallet_path_guard,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_WALLET = _REPO_ROOT / "tests" / "fixtures" / "synthetic.mv.db"


@pytest.fixture(autouse=True)
def _reset_guard():
    enable_wallet_path_guard()
    os.environ.pop(REAL_WALLET_ENV, None)
    yield
    enable_wallet_path_guard()
    os.environ.pop(REAL_WALLET_ENV, None)


def test_blocks_non_fixture_wallet_path(tmp_path: Path):
    wallet = tmp_path / "user-wallet.mv.db"
    wallet.write_bytes(b"H:2,block:2,format:2,version:1,")
    with pytest.raises(RealWalletBlockedError, match="tests/fixtures"):
        assert_wallet_path_allowed(wallet)


def test_allows_fixture_wallet_path():
    assert_wallet_path_allowed(_FIXTURE_WALLET)


def test_allows_real_wallet_when_env_set(tmp_path: Path):
    wallet = tmp_path / "user-wallet.mv.db"
    wallet.write_bytes(b"\x00")
    os.environ[REAL_WALLET_ENV] = "1"
    assert_wallet_path_allowed(wallet)


def test_cli_opt_in_sets_env():
    os.environ.pop(REAL_WALLET_ENV, None)
    enable_cli_wallet_access()
    assert os.environ[REAL_WALLET_ENV] == "1"


def test_query_rows_blocked_outside_fixtures(tmp_path: Path):
    wallet = tmp_path / "outside.mv.db"
    wallet.write_bytes(b"H:2,block:2,format:2,version:1,")
    with pytest.raises(RealWalletBlockedError):
        _query_rows(wallet, "SELECT 1;")


def test_disable_guard_skips_path_check(tmp_path: Path):
    wallet = tmp_path / "outside.mv.db"
    wallet.write_bytes(b"\x00")
    disable_wallet_path_guard()
    assert_wallet_path_allowed(wallet)
