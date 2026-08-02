"""Read-only Sparrow H2 wallet database access via embedded H2 JAR."""

from __future__ import annotations

import csv
import io
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from coldcard_panic_drain.sparrow.models import KeystoreInfo, UtxoRecord, WalletSnapshot
from coldcard_panic_drain.util import path_to_hardened

# Sparrow Status.FROZEN enum ordinal
STATUS_FROZEN = 0

H2_JAR = Path(__file__).resolve().parents[3] / "vendor" / "h2-2.2.224.jar"

# BIP84 native segwit
SCRIPT_TYPE_P2WPKH = 1


def _jdbc_base_path(wallet_path: Path) -> str:
    p = wallet_path.resolve()
    name = p.name
    if name.endswith(".mv.db"):
        return str(p.with_name(name[:-6]))
    return str(p)


def _query_rows(wallet_path: Path, sql: str) -> list[list[str]]:
    if not H2_JAR.is_file():
        raise FileNotFoundError(f"H2 JAR not found at {H2_JAR}")
    url = f"jdbc:h2:file:{_jdbc_base_path(wallet_path)};ACCESS_MODE_DATA=r"
    proc = subprocess.run(
        [
            "java",
            "-cp",
            str(H2_JAR),
            "org.h2.tools.Shell",
            "-url",
            url,
            "-user",
            "sa",
            "-password",
            "",
            "-sql",
            sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"H2 query failed for {wallet_path}: {err}")
    return _parse_shell_output(proc.stdout)


def _parse_shell_output(stdout: str) -> list[list[str]]:
    lines = [ln.rstrip("\n") for ln in stdout.splitlines() if ln.strip()]
    if not lines:
        return []
    # H2 shell prints a header row then data; skip "(N rows)" footer
    rows: list[list[str]] = []
    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=";", quotechar='"')
    parsed = list(reader)
    if not parsed:
        return []
    # drop footer like "(2 rows)"
    while parsed and parsed[-1] and parsed[-1][0].startswith("("):
        parsed.pop()
    if len(parsed) <= 1:
        return []
    return parsed[1:]


def _hex_txid(blob_hex: str) -> str:
    raw = bytes.fromhex(blob_hex.strip())
    return raw[::-1].hex()


def _parse_ts(val: str) -> Optional[datetime]:
    val = val.strip()
    if not val or val.upper() == "NULL":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _build_origin(fingerprint: str, derivation_path: str) -> str:
    return f"wpkh([{fingerprint.lower()}/{path_to_hardened(derivation_path)}])"


def load_wallet(wallet_path: Path) -> WalletSnapshot:
    wallet_path = Path(wallet_path)
    if not wallet_path.exists():
        raise FileNotFoundError(wallet_path)

    wallet_rows = _query_rows(
        wallet_path,
        "SELECT id, name, storedBlockHeight, scriptType FROM wallet LIMIT 1;",
    )
    if not wallet_rows:
        raise RuntimeError(f"No wallet table row in {wallet_path}")
    wallet_id, name, stored_height, script_type = wallet_rows[0]
    if int(script_type) != SCRIPT_TYPE_P2WPKH:
        raise RuntimeError(
            f"Wallet {name} is not BIP84 P2WPKH (scriptType={script_type}). "
            "Only native segwit (bc1q) is supported."
        )
    chain_tip = int(stored_height or 0)
    if chain_tip <= 0:
        raise RuntimeError(
            f"Wallet {name} has no stored block height. "
            "Sync in Sparrow, re-copy the .mv.db, and retry."
        )

    ks_rows = _query_rows(
        wallet_path,
        f"SELECT masterFingerprint, derivationPath, extendedPublicKey "
        f"FROM keystore WHERE wallet = {wallet_id} ORDER BY index LIMIT 1;",
    )
    if not ks_rows:
        raise RuntimeError(f"No keystore in {wallet_path}")
    fingerprint, deriv_path, xpub = ks_rows[0]
    if not xpub or xpub.upper() == "NULL":
        raise RuntimeError("Keystore has no extended public key (watch-only xpub required).")
    fingerprint = (fingerprint or "").strip().lower()
    keystore = KeystoreInfo(
        fingerprint=fingerprint,
        derivation_path=deriv_path.strip(),
        xpub=xpub.strip(),
        origin=_build_origin(fingerprint, deriv_path),
    )

    # Used receive indices: external chain paths m/84'/0'/0'/0/i
    node_rows = _query_rows(
        wallet_path,
        f"""
        SELECT derivationPath FROM walletNode
        WHERE wallet = {wallet_id}
          AND derivationPath LIKE '%/0/%'
        ORDER BY id;
        """,
    )
    used_receive: list[int] = []
    for (path,) in node_rows:
        parts = path.strip().split("/")
        if len(parts) >= 6 and parts[-2] == "0":
            try:
                used_receive.append(int(parts[-1]))
            except ValueError:
                pass

    utxo_sql = f"""
        SELECT
            bt.txid,
            bthi.index,
            bthi.outputValue,
            bthi.height,
            bthi.date,
            bthi.label,
            bthi.status,
            bthi.spentBy,
            wn.derivationPath
        FROM blockTransactionHashIndex bthi
        JOIN blockTransaction bt ON bt.hash = bthi.hash
        JOIN walletNode wn ON wn.id = bthi.node
        WHERE bt.wallet = {wallet_id}
        ORDER BY bthi.outputValue DESC;
    """
    utxo_rows = _query_rows(wallet_path, utxo_sql)
    utxos: list[UtxoRecord] = []
    for row in utxo_rows:
        (
            txid_hex,
            vout,
            value_sats,
            height,
            date_s,
            label,
            status,
            spent_by,
            deriv_path,
        ) = row
        if spent_by and spent_by.upper() != "NULL":
            continue
        frozen = status.strip() == str(STATUS_FROZEN)
        address = _derive_address_from_path(keystore, deriv_path.strip())
        utxos.append(
            UtxoRecord(
                txid=_hex_txid(txid_hex),
                vout=int(vout),
                value_sats=int(value_sats),
                height=int(height or 0),
                received_at=_parse_ts(date_s),
                address=address,
                derivation_path=deriv_path.strip(),
                label=(label or "").strip() if label and label.upper() != "NULL" else "",
                frozen=frozen,
            )
        )

    return WalletSnapshot(
        path=str(wallet_path),
        name=name,
        chain_tip_height=chain_tip,
        keystore=keystore,
        utxos=utxos,
        used_receive_indices=sorted(set(used_receive)),
    )


def _derive_address_from_path(keystore: KeystoreInfo, node_path: str) -> str:
    """Derive bc1q address for a wallet node path using embit."""
    from embit.descriptor import Descriptor

    # account-level descriptor /0/*
    account_path = keystore.derivation_path.rstrip("/")
    desc_str = f"wpkh([{keystore.fingerprint}/{path_to_hardened(account_path)}]{keystore.xpub}/0/*)"
    desc = Descriptor.from_string(desc_str)
    # node_path like m/84'/0'/0'/0/5 -> index 5 on external chain
    parts = node_path.split("/")
    idx = int(parts[-1])
    chain = int(parts[-2])
    return desc.derive(chain, idx).address()
