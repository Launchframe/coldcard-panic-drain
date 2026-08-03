# Enhancement: Multisig and miniscript wallet support

**Labels:** `enhancement`

## Problem

Coldcard supports multisig and miniscript policies. Sparrow, Nunchuk, and Electrum can host multisig wallets. This tool currently assumes **single-sig BIP84 P2WPKH** only. Multisig operators facing a compromised cosigner or policy migration have no supported panic-drain path.

## Goal

Design and implement multisig-aware panic drains for a **narrow v1 policy** after single-sig wallet imports stabilize. v1 target: **N-of-M native segwit multisig** exported from Sparrow (or descriptor files), signed on Coldcard with all required keys.

## Step 0 — Policy and format survey (blocking)

Document before coding:

| Question | Notes |
|----------|-------|
| Which multisig schemes? | 2-of-3 P2WSH? 2-of-2? miniscript policies? |
| Sparrow H2 schema for multisig | Multiple keystores, `scriptType` MULTISIG |
| Descriptor / BSMS multisig exports | Nunchuk, Sparrow, Coldcard coordination file |
| PSBT signing flow | Multiple `bip32_derivations` per input; Coldcard partial vs final |
| Wallet B receive | Multisig receive descriptors vs single-sig dest (likely **require matching policy**) |
| Fee / vsize | P2WSH input sizes vary with M |

**Defer:** taproot multisig, complex miniscript, heterogeneous cosigner hardware.

## Proposed architecture

```
WalletSnapshot
  script_type: MULTISIG
  keystores: list[KeystoreInfo]   # new
  multisig_threshold: int          # N
  multisig_total: int              # M
  redeem_script or descriptor: str
```

- PSBT builder: witness script / `witness_script` in input; per-cosigner derivations
- `generate`: checklist lists all cosigner verification steps
- `verify-manifest`: match multisig descriptor hash
- Session snapshot: all cosigner xpubs + fingerprints (wallet-swap detection)

## Acceptance criteria (v1)

- [ ] Step 0 survey doc in `docs/` with supported policy template(s)
- [ ] Synthetic 2-of-3 P2WSH fixture → `plan` → PSBT with correct witness structure
- [ ] Document Coldcard signing order and partial-SIG workflow for operators
- [ ] Single-sig paths unchanged
- [ ] Non-supported policies fail with actionable error

## Related

- Nunchuk BSMS/Descriptor import (multisig markers in exports)
- Electrum multisig JSON
- Additional script types (P2WSH singlesig vs multisig distinction)
