# Fee spike recovery

Fees are **fixed when you run `generate`**. The broadcast schedule only controls *when* txs are sent, not whether they confirm. If mempool fees rise after signing, later broadcasts may sit unconfirmed until you intervene.

## Use competitive fees (especially with auto-broadcast)

You are racing an attacker who may know the compromised seed. If you use `broadcast-due` cron or a multi-day `spread_hours` window:

- Set `--fee-base` **above** current priority at `plan` time.
- Plan for the **worst** fee environment over the whole spread, not day-one conditions.
- `broadcast-due` does not estimate or bump fees.

## Mid-drain fee spike — replan remaining UTXOs

1. **Pause** `broadcast-due` cron (or stop manual broadcasts).
2. **Sync Wallet A** in Sparrow; note which UTXOs already confirmed.
3. **Re-copy** fresh Wallet A and Wallet B `.mv.db` files.
4. **Do not broadcast** old signed PSBTs for UTXOs you will regenerate — they carry the old fee. If already in mempool, RBF in Sparrow or wait for eviction.
5. **Re-run `plan`** with a higher `--fee-base` (same `--source`, `--dest`, `--output`). Only still-unspent UTXOs appear.
6. **Coldcard re-sign** new `psbts/*.psbt` files.
7. **Re-run `generate`**. Archive or delete stale `psbts_signed/` and `broadcast-state.yaml`.
8. **Resume** broadcast.

## Already-broadcast but stuck unconfirmed

Use Sparrow **RBF / fee bump** on individual txs (PSBTs are built with RBF enabled). Full replan is only needed for txs **not yet broadcast** when fees are too low for the window ahead.

## Partial drain

Confirmed UTXOs drop out of a re-synced wallet automatically. Wallet B receive indices for remaining coins are re-allocated — re-verify on Coldcard.
