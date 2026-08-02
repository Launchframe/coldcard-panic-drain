"""Shared test fixtures."""

from embit import bip32

from coldcard_panic_drain.sparrow.models import KeystoreInfo, WalletSnapshot

_SEED = b"panic-drain-test-seed-32-bytes!!"
_ACCOUNT = bip32.HDKey.from_seed(_SEED).derive("m/84'/0'/0'")
TEST_XPUB = _ACCOUNT.to_base58()
TEST_FP = _ACCOUNT.fingerprint.hex()


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
