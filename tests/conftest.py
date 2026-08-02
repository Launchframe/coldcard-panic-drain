"""Shared test fixtures."""

from embit import bip32

from coldcard_panic_drain.sparrow.models import KeystoreInfo, WalletSnapshot

_SEED = b"panic-drain-test-seed-32-bytes!!"
_ACCOUNT = bip32.HDKey.from_seed(_SEED).derive("m/84'/0'/0'")
TEST_XPUB = _ACCOUNT.to_base58()
TEST_FP = _ACCOUNT.fingerprint.hex()

_SEED_B = b"panic-drain-wallet-b-seed-32byte"
_ACCOUNT_B = bip32.HDKey.from_seed(_SEED_B).derive("m/84'/0'/0'")
TEST_XPUB_B = _ACCOUNT_B.to_base58()
TEST_FP_B = _ACCOUNT_B.fingerprint.hex()


def make_test_wallet(**kwargs) -> WalletSnapshot:
    ks = KeystoreInfo(
        fingerprint=TEST_FP,
        derivation_path="m/84'/0'/0'",
        xpub=TEST_XPUB,
        origin=f"wpkh([{TEST_FP}/84h/0h/0h])",
    )
    defaults = dict(
        path="/tmp/wallet.mv.db",
        name="test",
        chain_tip_height=900_000,
        keystore=ks,
        used_receive_indices=[],
    )
    defaults.update(kwargs)
    return WalletSnapshot(**defaults)


def make_test_wallet_b(**kwargs) -> WalletSnapshot:
    ks = KeystoreInfo(
        fingerprint=TEST_FP_B,
        derivation_path="m/84'/0'/0'",
        xpub=TEST_XPUB_B,
        origin=f"wpkh([{TEST_FP_B}/84h/0h/0h])",
    )
    defaults = dict(
        path="/tmp/wallet-b.mv.db",
        name="test-b",
        chain_tip_height=900_000,
        keystore=ks,
        used_receive_indices=[],
    )
    defaults.update(kwargs)
    return WalletSnapshot(**defaults)
