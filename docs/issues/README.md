# Wallet support enhancement issues

Specs for GitHub issues tracking wallet-format expansion beyond Sparrow BIP84 `.mv.db`.

| # | Spec file | GitHub issue |
|---|-----------|--------------|
| 1 | [electrum-wallet-import.md](electrum-wallet-import.md) | [#12](https://github.com/Launchframe/coldcard-panic-drain/issues/12) |
| 2 | [additional-script-types.md](additional-script-types.md) | [#13](https://github.com/Launchframe/coldcard-panic-drain/issues/13) |
| 3 | [multisig-miniscript.md](multisig-miniscript.md) | [#14](https://github.com/Launchframe/coldcard-panic-drain/issues/14) |
| 4 | [nunchuk-wallet-import.md](nunchuk-wallet-import.md) | [#15](https://github.com/Launchframe/coldcard-panic-drain/issues/15) |

## Filing issues

From repo root (requires `gh` authenticated with issue-create permission):

```bash
./scripts/file-wallet-support-issues.sh
```

The script creates issues with label `enhancement` and records issue numbers back into this README.

## Privacy

Issue bodies use **no real wallet data**. Nunchuk Step 0 requires operators to collect BSMS/Descriptor exports locally; inspection notes go in private issue comments or synthetic fixtures in tests — never committed exports from mainnet wallets.

## Target contract

All wallet readers should produce [`WalletSnapshot`](../../src/coldcard_panic_drain/sparrow/models.py) so `plan` / `generate` stay wallet-agnostic:

- `KeystoreInfo` — fingerprint, derivation path, xpub, BIP-329 origin fragment
- `UtxoRecord` — txid, vout, value, height, address, derivation path, label, frozen
- `chain_tip_height`, used receive indices/addresses for Wallet B gap avoidance
