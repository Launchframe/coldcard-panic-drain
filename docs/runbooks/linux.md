# Linux runbook

Preferred for airgapped machines (x86_64 and arm64).

## Install dependencies

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install python3 python3-venv default-jre
# or: sudo apt install openjdk-17-jre-headless
```

Need Python ≥ 3.11. On Ubuntu 22.04+ / recent Debian, distro `python3` is usually enough.
On older Ubuntu (e.g. 20.04) where default `python3` is below 3.11, install 3.12 from
[deadsnakes](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa):

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv
```

### Fedora

```bash
sudo dnf install python3 java-17-openjdk
```

Confirm:

```bash
python3 --version   # must be ≥ 3.11
java -version       # 11+
```

## Project setup

```bash
cd coldcard-panic-drain
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
bash scripts/verify-env.sh
```

If `python3` is still below 3.11 after installing a versioned package, create the venv with
that binary instead (e.g. `python3.12 -m venv .venv`).

H2 JARs ship under `vendor/` — do not fetch them during a drain run.

## Airgap notes

- Runtime needs **no** network. The app blocks non-localhost sockets.
- Install Python packages **once** on an online machine (`pip install -e ".[dev]"`), or vendor wheels offline:

  ```bash
  # online machine
  pip download -e ".[dev]" -d wheels/
  # airgapped machine
  pip install --no-index -f wheels/ -e ".[dev]"
  ```

- Do not bundle user wallet files in wheel directories.
- Copy synced Sparrow `.mv.db` files via trusted media (e.g. microSD), then run offline.

## Sparrow wallet paths

```text
~/.sparrow/wallets/*.mv.db
```

## microSD / output paths

```text
/media/<user>/<NAME>/
# or
/mnt/
```

## Next steps

- Dry-run with `plan` before `generate` — see [README.md](../../README.md).
- Read [DISCLAIMER.md](../../DISCLAIMER.md).
