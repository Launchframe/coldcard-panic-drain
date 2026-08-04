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

See [README.md §9](README.md#9-auto-broadcast-local-bitcoin-core-only) for cookie auth and `--follow`/cron setup.

---

## Broadcast cadence (auto-broadcast jitter and follow mode)

### Why not just an hourly cron?

An exact hourly cron (`0 * * * *`) fires every batch's broadcasts at the same minute, every hour, forever — a fixed cadence with no randomness is one more signal that ties a set of transactions together as a single automated drain, on top of whatever the fee/timing analysis already reveals. It also has no built-in notion of quiet hours (cron doesn't know about `schedule.yaml`), so a plain hourly job can broadcast overnight unless you also manage cron's own schedule window.

`--follow` (see [README.md §9](README.md#9-auto-broadcast-local-bitcoin-core-only)) exists mainly so **`--broadcast-jitter-minutes`** has somewhere to take effect without waiting for the next cron tick, and so you don't have to hand-manage a cron schedule around quiet hours. It is not required — cron with `--broadcast-jitter-minutes` and `--respect-quiet-hours` works too, since both flags apply identically in either mode. `--follow` is just one long-lived process instead of many short-lived ones.

### What does `--schedule-jitter` do?

Applied at **`plan`** time, inside `write_schedule()`. For each entry, on top of its even step spacing:

```
offset  = uniform(-schedule_jitter, +schedule_jitter) * step
t       = scheduled_time + offset
```

then two floors are enforced, in order: entries are pushed forward if needed so they stay **at least 15 minutes apart** (monotonic — jitter can never make entry *N* land before entry *N-1*), and if quiet hours are configured, `next_allowed_time()` is **re-applied after** jitter so a jittered timestamp can't land back inside the quiet window. The chosen `schedule_jitter` value is stored in `schedule.yaml` for reference. Default `0.35`; `0` reproduces the old fixed-step cadence.

### What does `--broadcast-jitter-minutes` do?

Applied at **`broadcast-due`** runtime (both `--follow` and cron/single-shot). Once an entry's `broadcast_not_before` has passed **and** its signed PSBT exists in `psbts_signed/`, the actual broadcast is delayed by a further:

```
ready_at = broadcast_not_before + uniform(0, broadcast_jitter_minutes) minutes
```

`ready_at` is drawn **once** and persisted to `broadcast-state.yaml`; re-running `broadcast-due` (a new cron tick, or a restarted `--follow` process) reads the same `ready_at` back rather than re-rolling it. Until `now >= ready_at`, the entry is reported as `skipped` with detail `broadcast jitter window`. Default `90` minutes; `0` disables the gate (broadcasts as soon as `broadcast_not_before` passes, same as before this feature).

### What does `--respect-quiet-hours` do (on `broadcast-due`)?

Off by default. `broadcast-due` is meant to run unattended, and quiet hours (`--dnd-start`/`--dnd-end`/`--timezone` from `plan`) otherwise only affect calendar reminders (`reminders.ics`) and the manual `remind` command. Pass `--respect-quiet-hours` if you also want the automated broadcaster itself to pause during the configured quiet window — due entries are reported as `skipped` with detail `quiet hours` until the window ends, then broadcast on the next check.

---

## Reschedule vs. re-plan

### I already signed my PSBTs — can I still change broadcast timing?

Yes, with **`reschedule`** (see [README.md §10](README.md#10-reschedule-broadcast-timing-optional)) — you do **not** need to re-run `plan`/`generate` or re-sign anything just to change *when* unbroadcast entries go out.

### `reschedule` vs. `plan` — which do I need?

| Change you want | Command |
|---|---|
| New broadcast timing only (spread/jitter) for entries not yet broadcast | `reschedule` |
| Different UTXOs, fees, destination addresses, or nLockTime spacing | `plan` + `generate` (re-sign PSBTs) |
| Retry a `failed` broadcast with the same PSBT, new timing | `reschedule` |
| Anything that changes what's inside a PSBT | `plan` + `generate` — `reschedule` never touches `psbts/`, labels, or fees |

### What exactly does `reschedule` touch?

Only `broadcast_not_before` in `schedule.yaml`, for entries whose `broadcast-state.yaml` status is **not** `broadcast` (pending and `failed` entries are both eligible — a prior failure doesn't exclude an entry from being rescheduled, and its `failed` status is left as-is so you know it needs a retry). It also clears any persisted runtime-jitter `ready_at` for those same entries, and can regenerate `reminders.ics` with `--update-calendar`. PSBTs, BIP-329 labels, `mapping.csv`, and fee rates are never rewritten.

### Does `reschedule` affect entries that already broadcast?

No. Any entry marked `status: broadcast` in `broadcast-state.yaml` keeps its original `broadcast_not_before` untouched, and is not counted toward `--spread-hours` for the remaining entries.
