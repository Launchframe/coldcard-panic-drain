# Enhancement: Additional script types (beyond BIP84 P2WPKH)

**Labels:** `enhancement`

## Problem

Sparrow and other wallets support multiple script types. Today [`h2_reader.py`](../../src/coldcard_panic_drain/sparrow/h2_reader.py) rejects anything except `SCRIPT_TYPE_P2WPKH` (native segwit P2WPKH). Operators with BIP49 P2SH-wrapped segwit or BIP44 legacy wallets cannot drain without converting wallets first.

## Goal

Extend wallet read, PSBT build, fee estimation, and address validation to support additional **single-sig** script types commonly used with Coldcard, in priority order:

| Priority | Script | BIP | Address encoding | Sparrow `scriptType` ordinal |
|----------|--------|-----|------------------|------------------------------|
| P0 | P2WPKH | BIP84 | native segwit v0 (P2WPKH) | 6 (done) |
| P1 | P2SH-P2WPKH | BIP49 | P2SH-wrapped segwit | 4 |
| P2 | P2PKH | BIP44 | legacy P2PKH | 1 (evaluate demand) |

## Scope

### In scope

- Sparrow H2 reader: accept additional `scriptType` values; map to descriptor templates
- [`psbt/builder.py`](../../src/coldcard_panic_drain/psbt/builder.py): correct input/output script types, witness vs legacy signing metadata
- [`psbt/fees.py`](../../src/coldcard_panic_drain/psbt/fees.py): vsize estimates per script type (not fixed 140 vB)
- [`util.py`](../../src/coldcard_panic_drain/util.py) `derive_address_for_chain_index`: branch per script type
- Validation: `validate_dest_address`, `validate_source_utxo`, manifest verify
- Tests per script type with synthetic keys in `tests/conftest.py`
- FAQS + README script-type matrix

### Out of scope (see multisig issue)

- `sortedmulti`, miniscript, taproot v1 (P2TR), P2WSH singlesig

## Implementation notes

- Store `script_type` on `WalletSnapshot` / `KeystoreInfo` (new field)
- PSBT input: P2SH-P2WPKH needs `witness_utxo` + redeem script; P2PKH needs non-witness UTXO fields
- Coldcard signing: confirm device UX per script type in checklist docs
- Fee jitter math unchanged; vsize constant becomes per-type function

## Acceptance criteria

- [ ] BIP49 Sparrow wallet (synthetic fixture) completes `plan` → `generate` → PSBT structure test
- [ ] Mixed script-type source/dest rejected with clear error (Wallet A and B must match type for v1)
- [ ] Existing BIP84 tests unchanged
- [ ] `h2_reader` error messages list supported types

## Related

- #12 Electrum wallet import
- #15 Nunchuk wallet import
- #14 Multisig / miniscript
