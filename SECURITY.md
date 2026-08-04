# Security Policy

## Supported versions

This project is in **beta**. Security fixes are applied on a best-effort basis to the latest `main` branch.

## Reporting a vulnerability

**Report privately to the repository owner** (GitHub Security Advisories preferred, or contact the maintainers via the GitHub profile for [Launchframe/coldcard-panic-drain](https://github.com/Launchframe/coldcard-panic-drain)).

Do **not** open a public issue for security vulnerabilities until maintainers have had a reasonable chance to respond and, if needed, ship a fix.

## Never paste wallet material

When reporting bugs or vulnerabilities — privately or publicly — **do not** include:

- Sparrow wallet files (`.mv.db`) or database dumps
- Addresses, transaction IDs, outpoints, amounts, or balances
- Labels, xpubs, descriptors, fingerprints, seeds, or mnemonics
- PSBT files or hex/base64
- Screenshots of Sparrow, Coldcard, or microSD output with real data

Describe the issue with **paths**, **error codes**, **redacted** steps to reproduce, and patches against **source code** or **synthetic** test fixtures.

See [AGENTS.md](AGENTS.md) and [DISCLAIMER.md](DISCLAIMER.md).

## Responsible disclosure

We ask that you:

1. Give maintainers a reasonable window to investigate and patch before public disclosure.
2. Avoid exploiting issues against third parties or real user wallets.
3. Keep any accidentally obtained wallet material confidential and delete it when no longer needed for the report.
