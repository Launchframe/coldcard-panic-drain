"""Regression tests for Sparrow H2 reader fixes after PR #2."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import coldcard_panic_drain.sparrow.h2_reader as h2_reader
from coldcard_panic_drain.sparrow.h2_reader import (
    SCRIPT_TYPE_P2WPKH,
    _fetch_column_chunks,
    _hex_txid,
    _query_rows,
    load_wallet,
)
from conftest import TEST_FP, TEST_XPUB


def _write_format2_stub(path: Path) -> Path:
    path.write_bytes(b"H:2,block:2,format:2,version:1," + b"\x00" * 64)
    return path


@pytest.fixture
def format2_wallet_path(tmp_path: Path) -> Path:
    h2_reader._schema_cache.clear()
    return _write_format2_stub(tmp_path / "stub.mv.db")


def _chunked_xpub_responses(xpub: str):
    chunk_size = h2_reader._VARCHAR_CHUNK_SIZE

    def respond(_wallet_path: Path, sql: str) -> list[list[str]]:
        if "TABLE_SCHEMA" in sql and "TABLE_NAME = 'wallet'" in sql:
            return [["wallet_master"]]
        if '"scriptType"' in sql and '"wallet_master"."wallet"' in sql:
            return [["1", "synthetic", "900000", str(SCRIPT_TYPE_P2WPKH)]]
        if '"masterFingerprint"' in sql and '"keystore"' in sql:
            return [[TEST_FP, "m/84'/0'/0'"]]
        if sql.startswith("SELECT LENGTH") and "extendedPublicKey" in sql:
            return [[str(len(xpub))]]
        if "SUBSTRING" in sql and "extendedPublicKey" in sql:
            start = int(sql.split(", ")[1].split(",")[0])
            return [[xpub[start - 1 : start - 1 + chunk_size]]]
        if "DISTINCT" in sql and "derivationPath" in sql and "blockTransactionHashIndex" in sql:
            return [["m/84'/0'/0'/0/0"], ["m/84'/0'/0'/0/1"]]
        if (
            '"walletNode"' in sql
            and "derivationPath" in sql
            and "DISTINCT" not in sql
            and "RAWTOHEX" not in sql
            and "blockTransactionHashIndex" not in sql
        ):
            return [["m/84'/0'/0'/0/0"], ["m/84'/0'/0'/0/1"]]
        if "RAWTOHEX" in sql:
            assert '"wallet_master"."blockTransaction"' in sql
            assert '"wallet_master"."blockTransactionHashIndex"' in sql
            assert '"spentBy"' in sql and "IS NULL" in sql
            assert "NOT EXISTS" in sql
            return [
                [
                    "ab" * 32,
                    "0",
                    "100000",
                    "800000",
                    "NULL",
                    "",
                    "1",
                    "m/84'/0'/0'/0/0",
                ]
            ]
        raise AssertionError(f"unexpected SQL: {sql[:120]}")

    return respond


def test_load_wallet_queries_wallet_master_schema(monkeypatch, format2_wallet_path: Path):
    """Sparrow 2.x tables live in wallet_master, not PUBLIC."""
    seen: list[str] = []

    def capture(wallet_path: Path, sql: str) -> list[list[str]]:
        seen.append(sql)
        return _chunked_xpub_responses(TEST_XPUB)(wallet_path, sql)

    monkeypatch.setattr(h2_reader, "_query_rows", capture)
    wallet = load_wallet(format2_wallet_path)
    assert wallet.name == "synthetic"
    assert any('"wallet_master"."wallet"' in sql for sql in seen)
    assert any('"wallet_master"."keystore"' in sql for sql in seen)


def test_load_wallet_accepts_sparrow_p2wpkh_script_type(monkeypatch, format2_wallet_path: Path):
    """Drongo ScriptType.P2WPKH is ordinal 6, not 1 (P2PKH) or BIP-84."""
    monkeypatch.setattr(h2_reader, "_query_rows", _chunked_xpub_responses(TEST_XPUB))
    wallet = load_wallet(format2_wallet_path)
    assert wallet.chain_tip_height == 900_000


def test_load_wallet_collects_used_receive_from_tx_history(monkeypatch, format2_wallet_path: Path):
    """Spent receives must still block reuse — not only walletNode gap entries."""
    monkeypatch.setattr(h2_reader, "_query_rows", _chunked_xpub_responses(TEST_XPUB))
    wallet = load_wallet(format2_wallet_path)
    assert wallet.used_receive_indices == [0, 1]


def test_load_wallet_rejects_non_p2wpkh_script_type(monkeypatch, format2_wallet_path: Path):
    def respond(wallet_path: Path, sql: str) -> list[list[str]]:
        handler = _chunked_xpub_responses(TEST_XPUB)
        if '"scriptType"' in sql:
            return [["1", "legacy", "900000", "1"]]
        return handler(wallet_path, sql)

    monkeypatch.setattr(h2_reader, "_query_rows", respond)
    with pytest.raises(RuntimeError, match="not BIP84 P2WPKH"):
        load_wallet(format2_wallet_path)


def test_load_wallet_rejects_non_numeric_wallet_id(monkeypatch, format2_wallet_path: Path):
    def respond(wallet_path: Path, sql: str) -> list[list[str]]:
        handler = _chunked_xpub_responses(TEST_XPUB)
        if '"scriptType"' in sql and '"wallet_master"."wallet"' in sql:
            return [["1; DROP TABLE wallet; --", "synthetic", "900000", str(SCRIPT_TYPE_P2WPKH)]]
        return handler(wallet_path, sql)

    monkeypatch.setattr(h2_reader, "_query_rows", respond)
    with pytest.raises(RuntimeError, match="Invalid wallet id"):
        load_wallet(format2_wallet_path)


def test_wallet_schema_rejects_unsafe_name(monkeypatch, format2_wallet_path: Path):
    def respond(_wallet_path: Path, sql: str) -> list[list[str]]:
        if "TABLE_SCHEMA" in sql:
            return [['wallet"; DROP TABLE wallet; --']]
        raise AssertionError(sql)

    monkeypatch.setattr(h2_reader, "_query_rows", respond)
    with pytest.raises(RuntimeError, match="Unsafe schema name"):
        load_wallet(format2_wallet_path)


def test_load_wallet_utxo_query_uses_rawtohex(monkeypatch, format2_wallet_path: Path):
    """Binary txid BLOBs break H2 Shell row parsing unless hex-encoded in SQL."""
    monkeypatch.setattr(h2_reader, "_query_rows", _chunked_xpub_responses(TEST_XPUB))
    wallet = load_wallet(format2_wallet_path)
    assert len(wallet.utxos) == 1
    assert wallet.utxos[0].value_sats == 100_000
    assert wallet.utxos[0].txid == _hex_txid("ab" * 32)


def test_load_wallet_reads_chunked_xpub(monkeypatch, format2_wallet_path: Path):
    """H2 Shell truncates VARCHAR columns at ~100 chars; xpubs are ~111."""
    long_xpub = TEST_XPUB if len(TEST_XPUB) > 100 else TEST_XPUB + ("x" * (111 - len(TEST_XPUB)))
    monkeypatch.setattr(h2_reader, "_query_rows", _chunked_xpub_responses(long_xpub))
    wallet = load_wallet(format2_wallet_path)
    assert wallet.keystore.xpub == long_xpub


def test_load_wallet_utxo_query_filters_spent_markers(monkeypatch, format2_wallet_path: Path):
    """Exclude Sparrow spent-marker rows (spentBy IS NULL but referenced by another row)."""
    seen_utxo_sql: list[str] = []

    def capture(wallet_path: Path, sql: str) -> list[list[str]]:
        if "RAWTOHEX" in sql:
            seen_utxo_sql.append(sql)
        return _chunked_xpub_responses(TEST_XPUB)(wallet_path, sql)

    monkeypatch.setattr(h2_reader, "_query_rows", capture)
    load_wallet(format2_wallet_path)
    assert len(seen_utxo_sql) == 1
    assert '"spentBy"' in seen_utxo_sql[0] and "IS NULL" in seen_utxo_sql[0]
    assert "NOT EXISTS" in seen_utxo_sql[0]


def test_load_wallet_raises_on_malformed_utxo_row(monkeypatch, format2_wallet_path: Path):
    def respond(wallet_path: Path, sql: str) -> list[list[str]]:
        handler = _chunked_xpub_responses(TEST_XPUB)
        if "RAWTOHEX" in sql:
            return [["only-one-column"]]
        return handler(wallet_path, sql)

    monkeypatch.setattr(h2_reader, "_query_rows", respond)
    with pytest.raises(RuntimeError, match="Malformed UTXO row"):
        load_wallet(format2_wallet_path)


def test_query_rows_raises_on_shell_error_stdout(monkeypatch, format2_wallet_path: Path):
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='Error: org.h2.jdbc.JdbcSQLSyntaxErrorException: Table "WALLET" not found\n',
            stderr="",
        )

    monkeypatch.setattr(h2_reader.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="H2 query failed"):
        _query_rows(format2_wallet_path, 'SELECT 1 FROM "wallet_master"."wallet";')


def test_query_rows_format_mismatch_error(monkeypatch, format2_wallet_path: Path):
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="The read format 2 is smaller than the supported format 3 [2.2.224/5]",
        )

    monkeypatch.setattr(h2_reader.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="H2 version mismatch"):
        _query_rows(format2_wallet_path, "SELECT 1;")


def test_fetch_column_chunks_uses_direct_from_clause(monkeypatch, format2_wallet_path: Path):
    """Subqueries in LENGTH() caused multi-line Shell output; use FROM table directly."""
    calls: list[str] = []

    def fake_query(_wallet_path: Path, sql: str) -> list[list[str]]:
        calls.append(sql)
        if sql.startswith("SELECT LENGTH"):
            assert "FROM \"wallet_master\".\"keystore\"" in sql
            assert "SELECT (" not in sql
            return [["5"]]
        if "SUBSTRING" in sql:
            return [["12345"]]
        raise AssertionError(sql)

    monkeypatch.setattr(h2_reader, "_query_rows", fake_query)
    assert (
        _fetch_column_chunks(
            format2_wallet_path,
            column="extendedPublicKey",
            from_clause='FROM "wallet_master"."keystore" LIMIT 1',
        )
        == "12345"
    )
