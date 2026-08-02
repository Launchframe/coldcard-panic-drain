"""Tests for external receive chain helpers."""

from coldcard_panic_drain.sparrow.receive import receive_index_from_path

from conftest import make_test_wallet_b


def test_receive_index_from_path_accepts_short_relative_paths():
    assert receive_index_from_path("0/1") == 1
    assert receive_index_from_path("m/84'/0'/0'/0/1") == 1


def test_receive_index_from_path_ignores_change_chain():
    assert receive_index_from_path("m/84'/0'/0'/1/0") is None


def test_next_receive_index_honors_used_addresses_without_index():
    addr1 = make_test_wallet_b().keystore
    from coldcard_panic_drain.util import derive_address_for_chain_index

    used_addr = derive_address_for_chain_index(addr1, 0, 1)
    wallet = make_test_wallet_b(used_receive_indices=[0], used_receive_addresses=[used_addr])
    assert wallet.next_receive_index == 2
