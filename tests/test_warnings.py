"""Warning and session tests."""

from coldcard_panic_drain.export.warnings import summarize_skips
from coldcard_panic_drain.plan.session import DrainSession
from coldcard_panic_drain.sparrow.models import KeystoreInfo, SkipReason, UtxoRecord, WalletSnapshot


def _utxo(**kwargs) -> UtxoRecord:
    defaults = dict(
        txid="cc" * 32,
        vout=0,
        value_sats=100_000,
        height=1,
        received_at=None,
        address="bc1q",
        derivation_path="m/84'/0'/0'/0/0",
    )
    defaults.update(kwargs)
    return UtxoRecord(**defaults)


def test_summarize_skips():
    utxos = [
        _utxo(included=True),
        _utxo(vout=1, frozen=True, included=False, skip_reason=SkipReason.FROZEN, value_sats=200_000),
        _utxo(vout=2, included=False, skip_reason=SkipReason.USER_SKIPPED, value_sats=50_000),
    ]
    s = summarize_skips(utxos)
    assert s.incomplete
    assert s.total_excluded == 2
    assert s.frozen == 1
    assert s.user_skipped == 1
    assert s.at_risk_sats == 250_000


def test_session_roundtrip(tmp_path):
    ks = KeystoreInfo("abcd", "m/84'/0'/0'", "xpub", "origin")
    src = WalletSnapshot("/a.mv.db", "a", 100, ks, utxos=[_utxo()])
    dest = WalletSnapshot("/b.mv.db", "b", 100, ks)
    session = DrainSession.from_wallets(src, dest, 25, 0.1, 2, 48.0)
    path = tmp_path / "labels-session.json"
    session.save(path)
    loaded = DrainSession.load(path)
    assert loaded.fee_base == 25
    assert len(loaded.utxo_objects()) == 1
