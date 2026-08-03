# Enhancement: Nunchuk wallet import (BSMS / Descriptor export)

**Labels:** `enhancement`

## Problem

Operators using [Nunchuk](https://nunchuk.io/) cannot run `plan` / `generate` today because the CLI only accepts Sparrow `.mv.db` files. Nunchuk does not expose an H2 cache equivalent in our offline workflow.

## Goal

Support Nunchuk as Wallet A (source) and/or Wallet B (destination) for **BIP84 native-segwit** panic drains, preserving existing safety gates (ownership confirmation, mapping review, zero-network file processing).

## Step 0 — Collect and inspect export samples (**blocking**)

**Status: not started — no sample files yet.**

Before choosing an import format or writing code, collect **redacted or testnet** exports for both wallet roles:

| Role | What to export | Notes |
|------|----------------|-------|
| Wallet A (source) | BSMS + Descriptor | Wallet synced in Nunchuk with spendable UTXOs |
| Wallet B (dest) | BSMS + Descriptor | Fresh receive wallet |
| Optional | Coldcard file export | Only if the wallet menu offers it; compare to BSMS |

### Export procedure (Nunchuk UI)

1. Open wallet in Nunchuk (**sync source wallet first**).
2. **Wallet → View wallet config → hamburger menu (⋮) → Export wallet configuration**.
3. Save **BSMS** and **Descriptor** variants separately.
4. **Do not use Portal** — NFC-only; incompatible with offline file processing.
5. **Coldcard** export may be absent on some wallet types (e.g. only BSMS, Descriptor, Portal available).
6. Store files locally only — **do not commit or paste real exports** into GitHub or agent chat.

### Inspection checklist

Fill in after samples exist (private issue comment or synthetic fixture PR):

| Field | BSMS | Descriptor | Coldcard (if any) |
|-------|------|------------|-------------------|
| File extension / encoding | _TBD_ | _TBD_ | _TBD_ |
| xpub + fingerprint + account path | _TBD_ | _TBD_ | _TBD_ |
| UTXO list (txid, vout, value, path) | _TBD_ | _TBD_ | _TBD_ |
| Labels present | _TBD_ | _TBD_ | _TBD_ |
| Script type (`wpkh` only vs mixed) | _TBD_ | _TBD_ | _TBD_ |
| Multisig / miniscript markers | _TBD_ | _TBD_ | _TBD_ |
| Watch-only vs signing config | _TBD_ | _TBD_ | _TBD_ |
| embit / standard parser fit | _TBD_ | _TBD_ | _TBD_ |

### `WalletSnapshot` field mapping

| `WalletSnapshot` field | Source in export (TBD) |
|------------------------|-------------------------|
| `keystore.fingerprint` | |
| `keystore.derivation_path` | |
| `keystore.xpub` | |
| `keystore.origin` | derive from descriptor |
| `chain_tip_height` | export or companion file? |
| `utxos[]` | export or companion file? |
| `used_receive_indices` | derive from history or export |
| `name` | wallet label from export |

## Step 1 — Format recommendation (after Step 0)

Score **BSMS vs Descriptor** (and Coldcard file export if available):

| Criterion | Weight | BSMS | Descriptor | Notes |
|-----------|--------|------|------------|-------|
| UTXO coverage | High | _TBD_ | _TBD_ | Source needs spendable set without network |
| Derivation path fidelity | High | _TBD_ | _TBD_ | PSBT `bip32_derivations` need full paths |
| Label availability | Medium | _TBD_ | _TBD_ | Frozen/skip UX |
| Parser maturity | Medium | _TBD_ | _TBD_ | Prefer embit-friendly formats |
| Operator friction | Medium | _TBD_ | _TBD_ | Fewer airgap export steps |
| Future multisig | Low | _TBD_ | _TBD_ | Defer to multisig issue |

**Hypothesis to validate:** Descriptor export may suffice for Wallet B (derive receive addresses). Wallet A may need UTXO-bearing export or a **companion data source** (transaction export, manual UTXO list) if both BSMS and Descriptor are descriptor-only.

## Step 2 — Implementation sketch (post-recommendation)

- New reader module: `src/coldcard_panic_drain/nunchuk/` (or generic `wallet_import/`) → `WalletSnapshot`
- CLI: extend `--source` / `--dest` to accept Sparrow `.mv.db` **or** Nunchuk export path(s); exact flags TBD after format choice
- Tests: synthetic BSMS/Descriptor fixtures only (`tests/fixtures/nunchuk/`)
- Docs: README workflow branch for Nunchuk sync/export before offline `plan`
- **Out of scope v1:** Portal/NFC, non-BIP84 script types (see additional-script-types issue)

## Acceptance criteria

- [ ] Step 0 checklist completed (redacted notes in issue comments)
- [ ] Recommended import format documented with rationale
- [ ] `WalletSnapshot` populated from Nunchuk export in unit tests (synthetic fixtures)
- [ ] `plan` + `generate` happy path with Nunchuk source + dest, **or** documented limitation if UTXO gap remains
- [ ] AGENTS.md privacy rules preserved (no real wallet material in repo)

## Related

- #TBD Electrum wallet import
- #TBD Additional script types
- #TBD Multisig / miniscript
