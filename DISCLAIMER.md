# Disclaimer

**coldcard-panic-drain is beta software.** Use at your own risk.

## Not financial advice

This tool is provided for technical convenience only. Nothing in the documentation, CLI output, or related materials constitutes financial, legal, or investment advice.

## You are responsible for verification

Before signing or broadcasting any transaction:

- Verify every destination address on your Coldcard (and in Sparrow Wallet B).
- Confirm fee rates and amounts match your intent.
- Confirm you control Wallet B and that the Sparrow file matches your signing device.

**Incorrect destinations or fees can result in permanent loss of funds.**

## Funds can be lost

Bugs, user error, stale wallet files, wrong fee settings, incomplete drains, or misuse of signed PSBTs can cause irreversible loss. Authors and contributors are not liable for any loss of funds, data, or other damages arising from use of this software. See [LICENSE](LICENSE).

## Test on testnet first

Practice the full workflow (`plan` → `generate` → sign → verify → broadcast) on **Bitcoin testnet** with throwaway wallets before using mainnet funds.

## Security reporting

For vulnerability disclosure and what not to paste into public issues, see [SECURITY.md](SECURITY.md).
