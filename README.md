# coldcard-panic-drain

Offline CLI for migrating funds from a compromised Sparrow wallet (Wallet A) to a fresh wallet (Wallet B) without consolidating UTXOs or broadcasting in one shot.

**Local network contract:** wallet processing (`plan`, `generate`, etc.) is file-only. The only network use is optional `broadcast-due`, which talks to **Bitcoin Core on localhost or a `*.local` host** (e.g. `https://happy-feet.local:8332`). Public/remote nodes require manual broadcast in Sparrow.

## Requirements

- Python 3.11+
- Java (for read-only H2 access to Sparrow wallet files)
- Sparrow 2.x BIP84 (`bc1q`) wallets

## Install

```bash
cd coldcard-panic-drain
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Workflow

### 1. Sync in Sparrow (network boundary)

1. Open Wallet A in Sparrow and **sync** so UTXOs and chain tip are current.
2. Copy `~/.sparrow/wallets/<wallet-a>.mv.db` and Wallet B's `.mv.db` to your offline machine or microSD staging area.

### 2. Plan (dry run)

```bash
coldcard-panic-drain plan \
  --source /path/to/compromised.mv.db \
  --dest   /path/to/staging.mv.db \
  --output /Volumes/MICROSD/panic-batch-001 \
  --fee-base 25 \
  --fee-jitter 0.15 \
  --min-blocks-apart 2 \
  --spread-hours 48 \
  --dnd-start 22:00 \
  --dnd-end 08:00 \
  --timezone America/New_York
```

- Lists all spendable UTXOs; prompts for labels on unlabeled coins.
- Frozen UTXOs are excluded with loud warnings.
- Skipping a UTXO triggers incomplete-drain warnings.
- **Required:** confirm Wallet B ownership (Sparrow file matches your signing device).
- Review the mapping table and type `PROCEED` to save the session (no PSBTs exist yet).

### 3. Generate outputs

```bash
coldcard-panic-drain generate --output /Volumes/MICROSD/panic-batch-001
```

If any UTXOs were excluded, you must type `I UNDERSTAND` to proceed.

**Outputs:**

| File | Purpose |
|------|---------|
| `psbts/*.psbt` | Unsigned single-UTXO PSBTs for Coldcard |
| `wallet-a-labels.jsonl` | Re-import labels into Wallet A after drain |
| `wallet-b-labels.jsonl` | Import into Wallet B before broadcast |
| `mapping.csv` | Human audit trail |
| `schedule.yaml` | Shuffled broadcast order + timing |
| `reminders.ics` | Calendar import (Google / Outlook / Apple) |
| `verify/coldcard-checklist.txt` | Address verification list |
| `SKIPPED-UTXOS.txt` | Excluded coins (if any) |

### 4. Sign on Coldcard (Wallet A)

1. Copy each file from `psbts/` to the **root** of the microSD card (not a subfolder).
2. Coldcard → **Ready to Sign** — it only lists `.psbt` files in the card root directory.
3. For **each** PSBT, verify the destination address on the device and in Sparrow Wallet B before signing.
4. Copy `*-signed.psbt` to `psbts_signed/` on the output volume.

### 5. Verify signed PSBTs

```bash
coldcard-panic-drain verify-manifest --output /Volumes/MICROSD/panic-batch-001
```

### 6. Import labels in Sparrow

1. Wallet B: **File → Import Wallet → Labels** → `wallet-b-labels.jsonl`
2. Wallet A: **File → Import Wallet → Labels** → `wallet-a-labels.jsonl` (do this before closing Sparrow)

### 7. Broadcast per schedule

Open each signed PSBT in Sparrow after `broadcast_not_before` in `schedule.yaml`.

```bash
coldcard-panic-drain remind --output /Volumes/MICROSD/panic-batch-001
```

### 8. Calendar reminders (manual broadcast)

Import `reminders.ics` into your calendar app. Quiet hours (`--dnd-start` / `--dnd-end`) shift alarm times so you are not notified during sleep.

```bash
coldcard-panic-drain export-calendar --output /Volumes/MICROSD/panic-batch-001
```

### 9. Auto-broadcast (local Bitcoin Core only)

Use competitive `--fee-base` at plan time — you are racing the attacker. See [docs/FEE-SPIKE-RECOVERY.md](docs/FEE-SPIKE-RECOVERY.md).

Point `--rpc-url` at Core on the same machine (`http://127.0.0.1:8332`) or a LAN node via mDNS (`https://happy-feet.local:8332`). Bare IP addresses like `http://192.168.1.50:8332` are rejected — use a `*.local` hostname instead.

```bash
# Hourly cron — ignores quiet hours; may broadcast overnight
0 * * * * coldcard-panic-drain broadcast-due -o /path/to/batch --max-count 1 \
  --rpc-url https://happy-feet.local:8332
```

`broadcast-state.yaml` tracks completed broadcasts and survives reboots.

## Reuse (Wallet B → Wallet C)

Same commands with `--source` = staging wallet and `--dest` = final wallet.

## Security notes

- Sparrow `.mv.db` files contain xpubs and full transaction history — treat output dirs as sensitive.
- The tool never sees seeds; only watch-only wallet databases.
- RAM workspace is wiped on exit (`wipe` subcommand available).

## License

MIT
