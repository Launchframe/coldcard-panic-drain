# AGENTS.md — coldcard-panic-drain

Instructions for AI agents planning and executing work in this repository.

**Read this file before doing anything else in this project.**

---

## Mission

`coldcard-panic-drain` is an **offline** CLI that:

1. Reads Sparrow BIP84 wallet files (`.mv.db`) locally
2. Maps spendable UTXOs from Wallet A → fresh receive addresses on Wallet B
3. Exports single-UTXO PSBTs, BIP-329 label files, broadcast schedule, and checklists
4. Never opens a network socket (enforced in `network_guard.py`)

Sparrow alone handles sync and broadcast. This tool is a local file processor.

Repository: `github.com/Launchframe/coldcard-panic-drain`

---

## Non-negotiable: no wallet data over the wire

This project handles **high-sensitivity financial data**. The agent router (cloud LLM, subagents, MCP tools that leave the machine, PR bots, telemetry, etc.) must **never** receive wallet or transaction content.

### Allowed to send to the agent router

Only these categories:

| Category | Examples |
|----------|----------|
| **User conversational text** | Questions, preferences, task descriptions the user typed |
| **File paths** | `/Users/alice/Projects/coldcard-panic-drain/src/cli.py`, `~/.sparrow/wallets/foo.mv.db` as a path string |
| **Source code** | Files in this repo; generic test fixtures with **synthetic** data committed to git |

### Prohibited — never transmit to the agent router

Do **not** include in chat messages, tool arguments, subagent prompts, MCP calls, commit messages, PR bodies, issue text, logs pasted to the agent, or any other channel that reaches the agent router:

- Sparrow `.mv.db` contents or H2/SQL query **results**
- **Addresses** (`bc1…`, `tb1…`, legacy, etc.)
- **Transaction IDs**, outpoints (`txid:vout`), or raw tx hex
- **UTXO amounts**, balances, fee rates applied to real coins, or sat/BTC values from real wallets
- **Labels** from real wallets (BIP-329 JSONL, Sparrow label fields, user-assigned drain labels)
- **xpubs**, **xprvs**, **descriptors**, **master fingerprints** from real wallets
- **Seeds**, **mnemonics**, **PSBT** files (unsigned or signed), or PSBT hex/base64
- **mapping.csv**, **schedule.yaml**, **manifest.json**, **SKIPPED-UTXOS.txt**, **labels-session.json**, or any **generate** output containing real data
- **Coldcard checklist** lines with real indices/addresses
- **Terminal output** from running `plan` / `generate` / `verify-manifest` against real wallet files
- **Screenshots** or snapshots of Sparrow, Coldcard, or microSD output directories with real data
- **Stack traces** that embed any of the above

If the user pastes prohibited content in chat, **do not repeat it**, **do not quote it**, **do not forward it to subagents**. Acknowledge the category (“you shared a txid”) and continue using paths and code only.

### Path vs. payload

A path like `--source ~/.sparrow/wallets/compromised.mv.db` is allowed.

Reading that file and returning rows, addresses, or labels is **not** allowed in agent-router traffic. Inspect structure via **source code** and **synthetic fixtures** only.

### Local execution

Running the CLI locally on the user’s machine is fine **if** stdout/stderr is **not** copied into agent-router messages. Summarize outcomes in abstract terms: “plan completed, N PSBTs generated” without listing refs, amounts, or addresses.

---

## Zero-network contract (application)

The **application** must never open sockets. Agents must not:

- Add `--allow-network` or similar escape hatches
- Call Esplora, Electrum, mempool APIs, Bitcoin Core RPC, or Sparrow APIs
- Add dependencies that phone home by default

Sparrow is the only network boundary for the user’s workflow.

---

## Conversational planning

When the user asks for features, fixes, or workflow help:

1. **Clarify offline constraints** — no live chain data; values come from Sparrow DB cache or CLI flags.
2. **Prefer dry-run language** — `plan` before `generate`; incomplete-drain warnings and `I UNDERSTAND` gate must stay.
3. **Do not ask for real wallet material** — ask for file **paths**, error **codes**, or **redacted** descriptions instead of txids/addresses/amounts.
4. **Split large work** — H2 reader, labeling, PSBT builder, export, CLI, tests are separate concerns; minimal diffs per task.
5. **Document user-facing steps in README** — not in agent chat with real examples containing mainnet data.

### Planning checklist

- [ ] Does the change preserve the zero-network guard?
- [ ] Could it leak wallet fields into logs or default CLI output?
- [ ] Are tests using **synthetic** keys/addresses only (see `tests/conftest.py`)?
- [ ] Does incomplete-drain behavior stay loud (banner, `SKIPPED-UTXOS.txt`, `I UNDERSTAND`)?
- [ ] Are Wallet A label re-import reminders preserved?
- [ ] Does setup docs mention Python ≥ 3.11, Java on PATH, and platform (macOS/Linux/WSL)?

---

## Platform compatibility

### Supported targets

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** (Apple Silicon & Intel) | Primary | Dev/tested on darwin. Homebrew `python@3.12` + Temurin/OpenJDK common. |
| **Linux** (x86_64, arm64) | Supported | Preferred for airgapped machines. Use distro `python3` ≥ 3.11 and `default-jre` or `openjdk-17-jre`. |
| **Windows** | Best-effort | Native Windows untested. Prefer **WSL2** (Ubuntu) and follow Linux steps. Native path: `py -3.12`, Microsoft OpenJDK, Git Bash or PowerShell. |

### Runtime requirements

| Dependency | Version | Purpose |
|------------|---------|---------|
| **Python** | ≥ 3.11 (`requires-python` in `pyproject.toml`) | CLI, embit PSBT/descriptors, typer |
| **Java** | JRE/JDK **11+** (17 LTS recommended) | `java` on `PATH`; invokes vendored H2 via `org.h2.tools.Shell` |
| **H2 JAR** | `vendor/h2-2.1.214.jar` (Sparrow MVStore format 2) and `vendor/h2-2.2.224.jar` (format 3) | Read-only Sparrow `.mv.db` access — **do not** fetch at runtime. Both JARs are dual-licensed (MPL 2.0 / EPL 1.0); ~2.5 MB each vendored in-repo. |
| **pip packages** | `embit`, `typer`, `pyyaml` (+ `pytest` for dev) | Installed into project venv |

### Not required

- Node.js, Rust, Bitcoin Core, Sparrow running headless, Docker (unless user chooses)
- Network at **runtime** (app blocks sockets); network is OK once for **initial** `pip install` on a dev/online machine

### OS-specific paths (agents may reference as paths only)

| Item | macOS | Linux | Windows (WSL) |
|------|-------|-------|----------------|
| Sparrow wallets | `~/.sparrow/wallets/*.mv.db` | same | `/mnt/c/Users/<user>/AppData/Roaming/Sparrow/wallets/` or sync copy |
| microSD output | `/Volumes/<NAME>/` | `/media/<user>/<NAME>/` or `/mnt/` | `/mnt/<drive>/` under WSL |
| venv activate | `source .venv/bin/activate` | same | `source .venv/bin/activate` (WSL) or `.venv\Scripts\activate` (native) |

### Sparrow wallet compatibility

- **BIP84 native segwit** (`bc1q…`) only — enforced in `h2_reader.py`
- Sparrow **2.0.x – 2.2.x** H2 schema expected; unknown schema should fail loudly
- Wallet file must be **synced in Sparrow first** (stored block height > 0)

---

## Dependency install (agent playbook)

Agents helping a user set up or debug the environment should **run checks locally** and report only pass/fail + version strings — **never** paste CLI output that includes wallet fields (see privacy rules above).

### 1. Detect platform

```bash
uname -s    # Darwin | Linux
uname -m    # arm64 | x86_64
```

On Windows, confirm WSL vs native and use the matching column in the table above.

### 2. Verify Python (must be ≥ 3.11)

```bash
python3 --version
# or: python3.12 --version, py -3.12 --version (Windows)
```

**If too old:** install before creating the venv.

| Platform | Agent action |
|----------|----------------|
| macOS | `brew install python@3.12` → use `python3.12` explicitly for venv |
| Linux (Debian/Ubuntu) | `sudo apt install python3.12 python3.12-venv` |
| Linux (Fedora) | `sudo dnf install python3.12` |
| Windows WSL | `sudo apt install python3.12 python3.12-venv` |

Always create the venv with the **3.11+** interpreter, not the system default if it is 3.8/3.9:

```bash
cd /path/to/coldcard-panic-drain
python3.12 -m venv .venv    # adjust minor version to what is installed
source .venv/bin/activate   # Windows native: .venv\Scripts\activate
python --version            # confirm ≥ 3.11 inside venv
```

### 3. Verify Java (must be on PATH)

```bash
java -version
which java    # macOS/Linux
```

**If missing:**

| Platform | Agent action |
|----------|----------------|
| macOS | `brew install openjdk@17` — ensure `java` is on PATH (brew prints caveats) |
| Linux (Debian/Ubuntu) | `sudo apt install default-jre` or `openjdk-17-jre-headless` |
| Linux (Fedora) | `sudo dnf install java-17-openjdk` |
| Windows | Install [Microsoft Build of OpenJDK 17](https://learn.microsoft.com/en-us/java/openjdk/download) or Temurin; add `java` to PATH |

Smoke-test H2 (no wallet file — only checks JAR + Java):

```bash
java -cp vendor/h2-2.1.214.jar org.h2.tools.Shell -help
```

Expect help text, not `FileNotFoundError` for the JAR. If JAR missing, it must ship with the repo under `vendor/` — do not download during a drain run.

### 4. Install Python dependencies

From repo root with venv activated:

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

This needs network **once** on the install machine. On a fully airgapped box, user must vendor wheels offline (`pip download -e ".[dev]" -d wheels/` on an online machine, then `pip install --no-index -f wheels/ -e ".[dev]"` offline). Agents should describe that flow when asked; do not bundle user wallet files in wheel dirs.

### 5. Verify install (safe to summarize to agent router)

```bash
pytest -q
coldcard-panic-drain --help
```

Report to the user/router: exit codes, test count, and `--help` subcommand names only. Do **not** paste output from `plan`/`generate` against real `.mv.db` files.

### 6. Common failures (agent triage)

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `python3` is 3.8/3.9 | macOS system Python | Use `python3.12 -m venv .venv` |
| `H2 JAR not found` | Missing `vendor/h2-2.1.214.jar` or `vendor/h2-2.2.224.jar` | Restore from repo checkout |
| `H2 query failed` | No Java, bad path, corrupt `.mv.db` | Fix Java; verify **path** to `.mv.db`; do not paste SQL rows |
| `not BIP84` | P2SH/P2PKH Sparrow wallet | User needs BIP84 `bc1q` wallets |
| `no stored block height` | Stale wallet file | User syncs in Sparrow, re-copies `.mv.db` |
| `NetworkBlockedError` in tests | Guard left enabled | Expected in app; tests call `disable_network_guard()` where needed |
| Permission error on microSD | RO volume or macOS privacy | Remount RW; grant Full Disk Access if needed |

### 7. PyInstaller (optional packaging — not yet default)

When implementing one-file binaries:

- Build on the **same OS** you ship for (darwin → macOS, linux → linux)
- Bundle both H2 JARs as data files; Java must still exist on target host unless you also ship a JRE (out of scope unless requested)
- Document that **Java remains an external dependency** for H2 reads

---

## Execution

### Workspace

Project root: `coldcard-panic-drain` (Python package under `src/coldcard_panic_drain/`).

Use `move_agent_to_root` to this repo before substantive edits.

### Commands (local only; do not paste output to agent router)

See **Dependency install (agent playbook)** above for full setup. Day-to-day:

```bash
source .venv/bin/activate
pip install -e ".[dev]"   # first time / after pull
pytest -q
coldcard-panic-drain --help
```

Java + vendored H2 JARs (`h2-2.1.214` for Sparrow wallets, `h2-2.2.224` for format 3) required for Sparrow DB reads.

### Code conventions

- **Python ≥ 3.11**, **typer** CLI, **embit** for PSBT/descriptors
- Match existing module layout: `sparrow/`, `plan/`, `psbt/`, `export/`, `schedule/`, `verify/`
- Minimal scope — no drive-by refactors
- Comments only for non-obvious protocol/H2 details

### Testing

- Unit tests with **generated test keys** (`tests/conftest.py`); never commit real wallet files
- `test_network_guard.py` must keep passing
- H2 integration tests: use minimal **synthetic** `.mv.db` fixtures in `tests/fixtures/` if added — do not upload real Sparrow DBs

### Subagents and automation

When launching Task/subagent/MCP workflows:

- Pass **file paths and task descriptions only**
- Explicitly instruct: **no wallet or transaction data in responses**
- Do not attach microSD output dirs, PSBTs, or label JSONL as context
- Bugbot/security-review: diff **source code** only; redact any accidental secrets before review

### Git and PRs

- Commit only when the user asks
- PR descriptions: architecture and test plan — **no** sample txids, addresses, or amounts
- Never commit `.mv.db`, `psbts/`, `psbts_signed/`, `labels-session.json`, or real drain output

---

## Subcommands (reference)

| Command | Role |
|---------|------|
| `plan` | Read wallets, label UTXOs, preview mapping, save `labels-session.json` — no PSBT writes |
| `generate` | PSBTs, BIP-329 exports, `schedule.yaml`, checklists |
| `verify-manifest` | Validate signed PSBTs in `psbts_signed/` |
| `remind` | Local-clock next broadcast hint from `schedule.yaml` |
| `wipe` | Clear RAM workspace |

---

## Sensitive artifacts (local only)

Treat as **confidential** on the user’s machine; agents must not read and relay contents:

- `~/.sparrow/wallets/*.mv.db`
- `--output` directory: `psbts/`, `wallet-*-labels.jsonl`, `mapping.csv`, `schedule.yaml`, `verify/`, `SKIPPED-UTXOS.txt`, `POST-FLOW-CHECKLIST.txt`, `labels-session.json`

---

## If unsure

**Default to not transmitting.** Use paths, module names, and synthetic test data. Ask the user to describe problems without pasting chain data.

When implementing, mirror the privacy model of the tool itself: **local processing, zero wallet data on the wire.**
