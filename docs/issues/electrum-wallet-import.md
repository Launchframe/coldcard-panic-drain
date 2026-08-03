# Enhancement: Electrum wallet import

**Labels:** `enhancement`

## Problem

Many operators use [Electrum](https://electrum.org/) instead of Sparrow. The CLI only reads Sparrow H2 `.mv.db` files today, so Electrum users must migrate wallets to Sparrow before a panic drain — extra friction and another software surface on the airgap machine.

## Goal

Read Electrum wallet files offline and produce the same [`WalletSnapshot`](../../src/coldcard_panic_drain/sparrow/models.py) contract as Sparrow, starting with **single-sig BIP84 native segwit** (`bc1q`).

## Step 0 — Wallet file survey (blocking)

Electrum wallet formats vary by version and wallet type. Before implementation, document:

| Wallet type | Typical path | Format | Priority |
|-------------|--------------|--------|----------|
| Standard watch-only | user-chosen `.json` | JSON keystore + history | P0 |
| Standard signing (xpub export) | export watch-only JSON | JSON | P0 |
| Multisig | `.json` | JSON with cosigner xpubs | defer → multisig issue |
| Lightning / embedded | n/a | not in scope | — |

**Collection procedure:**

1. Create **testnet** standard BIP84 wallets in Electrum (source with UTXOs, dest fresh).
2. Sync source wallet online; copy wallet file to offline staging.
3. Capture file structure (keys present, UTXO representation, labels, gap limit, script type fields) in **redacted** notes — no mainnet material in GitHub.

### Inspection checklist

| Field | Electrum JSON location (TBD) | Maps to `WalletSnapshot` |
|-------|---------------------------|----------------------------|
| xpub | | `keystore.xpub` |
| fingerprint / master fp | | `keystore.fingerprint` |
| derivation / purpose | | `keystore.derivation_path` |
| UTXO list | | `utxos[]` |
| labels | | `utxo.label` |
| chain tip / block height | | `chain_tip_height` |
| receive address history | | `used_receive_indices` |

## Proposed implementation

- Module: `src/coldcard_panic_drain/electrum/reader.py` (or `wallet_import/electrum.py`)
- Detect Electrum JSON vs Sparrow `.mv.db` by magic / schema (`load_wallet` dispatcher)
- Password-protected wallets: **out of scope v1** — require watch-only export or decrypted copy (document loudly)
- Tests: minimal synthetic Electrum JSON fixtures in `tests/fixtures/electrum/`
- README: Electrum sync → copy wallet file → `plan` workflow

## Acceptance criteria

- [ ] Step 0 survey completed on testnet fixtures
- [ ] BIP84 single-sig Electrum watch-only → `WalletSnapshot` with UTXOs and labels
- [ ] `plan` + `generate` integration test with synthetic Electrum fixtures
- [ ] Clear error when wallet is encrypted, multisig, or non-BIP84
- [ ] No network calls; AGENTS.md privacy preserved

## Related

- #15 Nunchuk wallet import (BSMS / Descriptor)
- #13 Additional script types
- #14 Multisig / miniscript
