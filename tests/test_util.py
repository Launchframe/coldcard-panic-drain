"""Unit tests for coldcard_panic_drain.util helpers."""

from coldcard_panic_drain.util import full_bip32_path_ints, parse_bip32_path


def test_full_bip32_path_ints_expands_sparrow_relative_path():
    account = "m/84'/0'/0'"
    assert full_bip32_path_ints(account, "m/0/31") == parse_bip32_path("m/84'/0'/0'/0/31")


def test_full_bip32_path_ints_keeps_absolute_node_path():
    full = "m/84'/0'/0'/1/6"
    assert full_bip32_path_ints("m/84'/0'/0'", full) == parse_bip32_path(full)
