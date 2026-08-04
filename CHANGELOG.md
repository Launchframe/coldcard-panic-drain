# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial **0.1.0 beta** open-source release packaging:
  - Offline `plan` / `generate` workflow for Sparrow BIP84 wallets
  - Single-UTXO PSBT export, BIP-329 labels, `schedule.yaml`, and Coldcard checklists
  - Optional localhost Bitcoin Core `broadcast-due` (including `--follow`)
  - `verify-manifest`, `export-calendar`, `reschedule`, `remind`, and `wipe`
  - Localhost-only network guard and real-wallet path guard for agent safety
  - MIT license, disclaimer, security policy, platform runbooks, and `scripts/verify-env.sh`
  - Beta notices in README and on `plan` / `generate` CLI entry points

[Unreleased]: https://github.com/Launchframe/coldcard-panic-drain/compare/HEAD...HEAD
