# FAQs

## Fees: `--fee-base` and `--fee-jitter`

These options apply at **`plan`** time. Each included UTXO gets its own single-input PSBT with a fee rate chosen then and **fixed in the signed transaction**. You cannot bump fees after Coldcard signing without rebuilding PSBTs.

### What does `--fee-base` do?

`--fee-base` is the **target fee rate in satoshis per virtual byte (sat/vB)** for each PSBT.

- Must be a **whole integer** (e.g. `25`, not `0.1` or `25.5`).
- The tool estimates ~140 vBytes per one-input, one-output P2WPKH transaction and sets:

  `fee_sats = fee_rate_sat_vB × 140` (approximately)

- Check the mapping table during `plan` — the per-UTXO rate is stored in the session and written to `schedule.yaml` / PSBT metadata.

**Panic-drain context:** if someone else has the compromised seed, they can broadcast competing transactions. Use a **competitive** `--fee-base` for your mempool conditions. See [docs/FEE-SPIKE-RECOVERY.md](docs/FEE-SPIKE-RECOVERY.md) if fees spike after you sign.

### What does `--fee-jitter` do?

`--fee-jitter` adds a **random spread** so not every PSBT pays exactly the same rate (slightly harder to fingerprint as one batch).

For each UTXO at `plan` time:

```
jitter     = random value between -fee_jitter and +fee_jitter
fee_sats   = max(140, round(max(1, fee_base) × 140 × (1 + jitter)))
fee_sat_vb = effective integer sat/vB label for schedule metadata
```

The `max(140, …)` floor is **1 sat/vB** on a ~140 vB transaction. When that floor would swallow the lower jitter tail (typical at `fee-base 1`), fees are drawn **uniformly** from the floor to the jittered maximum instead of clustering at 140.

`jitter` is a **fraction**, not sat/vB. Examples:

| `--fee-base` | `--fee-jitter` | Typical per-PSBT fee range |
|--------------|----------------|----------------------------|
| 25 | 0.15 | about 2,975–4,025 sats |
| 50 | 0.10 | about 6,300–7,700 sats |
| 1 | 0.12 | about 140–157 sats |
| 1 | 0.30 | about 140–182 sats (uniform; not piled at 140) |

The exact draw differs per UTXO and is stored in your session.

### Is `--fee-base 0` valid?

**Accepted by the CLI, but not useful.** The formula clamps the base rate to at least **1 sat/vB** before jitter:

```
max(140, round(max(1, fee_base) × 140 × (1 + jitter)))
```

So `--fee-base 0` still jitters around **~140 sats** per PSBT (1 sat/vB × 140 vB). In a race with an attacker, that will almost certainly lose.

### Can I use `--fee-base 0.1`?

**No.** `--fee-base` is an integer (whole sat/vB). Typer will reject non-integer values like `0.1`.

### What if `--fee-jitter` is very large (e.g. 0.5 or 1.0)?

Larger jitter widens the spread. With `--fee-base 10` and `--fee-jitter 0.5`, fees range from about **700 to 2,100 sats**.

**Fees are never negative**, and the **minimum is always 1 sat/vB** (~140 sats on a single-input P2WPKH PSBT) thanks to the `max(140, …)` clamp — even with extreme jitter (e.g. `--fee-jitter 1.5`).

Example edge case: `--fee-base 1` with `--fee-jitter 0.30` spreads fees across **140–182 sats** rather than pinning ~half the UTXOs at exactly 140.

### When are fees locked in?

At **`plan`**. `generate` reuses the session; changing flags on `generate` does not alter fees. To change fees, re-run `plan` (and then `generate`).

### Where do I see the chosen rate?

- **`plan` mapping table** — shown before you type `PROCEED` (use `OPTIONS` to adjust fees or display unit first)
- **`schedule.yaml`** — `fee_sat_vb` per entry
- **`mapping.csv`** — audit column

---

## Signing: Coldcard "wrong pubkey for input" / path `m/0/N`

Sparrow stores UTXO derivation paths **relative to the account** (e.g. `m/0/31`), but Coldcard expects the **full BIP84 path** from master (e.g. `m/84'/0'/0'/0/31`).

If you see:

> Signing failed late. Path (m/0/31) led to wrong pubkey for input#0

your PSBTs were built with an older version of this tool. **Do not sign them.** Upgrade, re-run **`generate`** on the same output directory (your `labels-session.json` from `plan` is still valid), and sign the new PSBTs from `psbts/`.

---

## Broadcast: Electrs vs Bitcoin Core RPC

`broadcast-due` calls **Bitcoin Core JSON-RPC** (`sendrawtransaction`, etc.). Point `--rpc-url` at **bitcoind's RPC port** (mainnet default `8332`), not Electrs.

Electrs is a read-only indexer. Use Core for auto-broadcast; use Sparrow for manual broadcast if you prefer.

See [README.md §9](README.md#9-auto-broadcast-local-bitcoin-core-only) for cookie auth and cron setup.
