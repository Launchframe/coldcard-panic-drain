"""H2 JAR selection for Sparrow .mv.db files."""

from pathlib import Path

import pytest

from coldcard_panic_drain.sparrow.h2_reader import (
    H2_JARS,
    SCRIPT_TYPE_P2WPKH,
    _detect_mvstore_format,
    _h2_jar_for_wallet,
    _parse_shell_output,
    _validate_sql_ident,
)


def test_sparrow_p2wpkh_script_type_ordinal():
    assert SCRIPT_TYPE_P2WPKH == 6


def test_detect_format_2(tmp_path: Path):
    f = tmp_path / "test.mv.db"
    f.write_bytes(b"H:2,block:2,format:2,version:1," + b"\x00" * 100)
    assert _detect_mvstore_format(f) == 2
    assert _h2_jar_for_wallet(f).name == "h2-2.1.214.jar"


def test_detect_format_3(tmp_path: Path):
    f = tmp_path / "test.mv.db"
    f.write_bytes(b"H:2,block:3,format:3,version:1," + b"\x00" * 100)
    assert _detect_mvstore_format(f) == 3
    assert _h2_jar_for_wallet(f).name == "h2-2.2.224.jar"


def test_detect_format_20_not_confused_with_format_2(tmp_path: Path):
    """Substring 'format:2' must not match inside 'format:20,'."""
    f = tmp_path / "future.mv.db"
    f.write_bytes(b"H:2,block:20,format:20,version:1," + b"\x00" * 100)
    with pytest.raises(RuntimeError, match="Unrecognized Sparrow/H2 file format"):
        _detect_mvstore_format(f)


def test_validate_sql_ident_accepts_wallet_master():
    assert _validate_sql_ident("wallet_master", label="schema name") == "wallet_master"


def test_validate_sql_ident_rejects_injection():
    with pytest.raises(RuntimeError, match="Unsafe schema name"):
        _validate_sql_ident('wallet"; DROP TABLE wallet; --', label="schema name")


def test_jars_exist():
    for jar in H2_JARS.values():
        assert jar.is_file(), f"missing {jar}"


def test_parse_shell_output_semicolon():
    stdout = "A;B;C\n1;2;3\n(1 row)\n"
    assert _parse_shell_output(stdout) == [["1", "2", "3"]]


def test_parse_shell_output_comma():
    stdout = "A,B,C\n1,2,3\n(1 row)\n"
    assert _parse_shell_output(stdout) == [["1", "2", "3"]]


def test_parse_shell_output_pipe():
    stdout = "A | B | C\n1 | 2 | 3\n(1 row)\n"
    assert _parse_shell_output(stdout) == [["1", "2", "3"]]
