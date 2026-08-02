"""Read-only Sparrow H2 wallet database access via embedded H2 JAR."""

from __future__ import annotations

import csv
import io
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from coldcard_panic_drain.sparrow.models import KeystoreInfo, UtxoRecord, WalletSnapshot
from coldcard_panic_drain.util import derive_address_for_chain_index, path_to_hardened

# Sparrow Status.FROZEN enum ordinal
STATUS_FROZEN = 0

VENDOR_DIR = Path(__file__).resolve().parents[3] / "vendor"
# Sparrow pins com.h2database:h2:2.1.214 (MVStore format 2). H2 2.2.x uses format 3 only.
H2_JARS: dict[int, Path] = {
    2: VENDOR_DIR / "h2-2.1.214.jar",
    3: VENDOR_DIR / "h2-2.2.224.jar",
}

# Sparrow Drongo ScriptType enum ordinal for P2WPKH (Native Segwit / BIP84).
# Enum order: P2PK=0, P2PKH=1, MULTISIG=2, P2SH=3, P2SH_P2WPKH=4, P2SH_P2WSH=5, P2WPKH=6, ...
SCRIPT_TYPE_P2WPKH = 6

# Sparrow 2.x stores wallet tables in a dedicated schema (not PUBLIC).
DEFAULT_SPARROW_SCHEMA = "wallet_master"

# H2 Shell truncates each displayed column at ~100 characters.
_VARCHAR_CHUNK_SIZE = 50

_schema_cache: dict[str, str] = {}

# H2 / SQL identifiers from Sparrow schema discovery (not user-supplied CLI args).
_SQL_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MVSTORE_FORMAT_RE = re.compile(rb"format:(\d+),")


def _q(ident: str) -> str:
    return f'"{ident}"'


def _validate_sql_ident(ident: str, *, label: str) -> str:
    ident = ident.strip()
    if not _SQL_IDENT_RE.fullmatch(ident):
        raise RuntimeError(
            f"Unsafe {label} {ident!r} from wallet file. "
            "Expected a Sparrow schema/table name."
        )
    return ident


def _safe_sql_int(val: str, *, label: str) -> int:
    try:
        return int(val.strip())
    except ValueError as e:
        raise RuntimeError(
            f"Invalid {label} {val!r} from wallet file (expected integer)."
        ) from e


def _tbl(schema: str, table: str) -> str:
    return f"{_q(schema)}.{_q(table)}"


def _jdbc_base_path(wallet_path: Path) -> str:
    p = wallet_path.resolve()
    name = p.name
    if name.endswith(".mv.db"):
        return str(p.with_name(name[:-6]))
    return str(p)


def _detect_mvstore_format(wallet_path: Path) -> int:
    """Read MVStore format from file header (format:2 or format:3)."""
    try:
        head = wallet_path.read_bytes()[:512]
    except OSError as e:
        raise RuntimeError(f"Cannot read wallet file {wallet_path}: {e}") from e
    match = _MVSTORE_FORMAT_RE.search(head)
    if match:
        fmt = int(match.group(1))
        if fmt in H2_JARS:
            return fmt
    raise RuntimeError(
        f"Unrecognized Sparrow/H2 file format in {wallet_path.name}. "
        "Expected an H2 MVStore .mv.db from Sparrow."
    )


def _h2_jar_for_wallet(wallet_path: Path) -> Path:
    fmt = _detect_mvstore_format(wallet_path)
    jar = H2_JARS.get(fmt)
    if jar is None or not jar.is_file():
        raise FileNotFoundError(
            f"H2 JAR for format {fmt} not found under {VENDOR_DIR}. "
            f"Expected {H2_JARS.get(fmt)}"
        )
    return jar


def _query_rows(wallet_path: Path, sql: str) -> list[list[str]]:
    h2_jar = _h2_jar_for_wallet(wallet_path)
    url = f"jdbc:h2:file:{_jdbc_base_path(wallet_path)};ACCESS_MODE_DATA=r"
    proc = subprocess.run(
        [
            "java",
            "-cp",
            str(h2_jar),
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
        if "Unsupported database file version" in err or "read format" in err:
            fmt = _detect_mvstore_format(wallet_path)
            raise RuntimeError(
                f"H2 version mismatch for {wallet_path.name} (MVStore format {fmt}). "
                f"Using {h2_jar.name}. If this persists, file a bug with Sparrow version."
            ) from None
        raise RuntimeError(f"H2 query failed for {wallet_path}: {err}")
    if any(ln.startswith("Error:") for ln in proc.stdout.splitlines()):
        err = proc.stdout.strip()
        raise RuntimeError(f"H2 query failed for {wallet_path}: {err}")
    return _parse_shell_output(proc.stdout)


def _wallet_schema(wallet_path: Path) -> str:
    key = str(wallet_path.resolve())
    if key in _schema_cache:
        return _schema_cache[key]
    rows = _query_rows(
        wallet_path,
        "SELECT TABLE_SCHEMA FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_NAME = 'wallet' AND TABLE_SCHEMA <> 'INFORMATION_SCHEMA' "
        "ORDER BY TABLE_SCHEMA LIMIT 1;",
    )
    schema = rows[0][0].strip() if rows else DEFAULT_SPARROW_SCHEMA
    schema = _validate_sql_ident(schema, label="schema name")
    _schema_cache[key] = schema
    return schema


def _parse_shell_output(stdout: str) -> list[list[str]]:
    lines = [ln.rstrip("\n") for ln in stdout.splitlines() if ln.strip()]
    if not lines:
        return []

    def _rows_for_delimiter(delim: str) -> list[list[str]]:
        reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delim, quotechar='"')
        parsed = list(reader)
        if not parsed:
            return []
        while parsed and parsed[-1] and parsed[-1][0].startswith("("):
            parsed.pop()
        if len(parsed) <= 1:
            return []
        return parsed[1:]

    # H2 2.1 Shell uses pipe-separated rows; 2.2 uses semicolons.
    best: list[list[str]] = []
    for delim in ("|", ";", ","):
        rows = _rows_for_delimiter(delim)
        if rows and (not best or len(rows[0]) > len(best[0])):
            best = [[cell.strip() for cell in row] for row in rows]
    return best


def _fetch_column_chunks(
    wallet_path: Path,
    *,
    column: str,
    from_clause: str,
) -> str:
    """Read a VARCHAR column via chunked SUBSTRING (H2 Shell truncates wide columns)."""
    col = _q(column)
    len_rows = _query_rows(wallet_path, f"SELECT LENGTH({col}) {from_clause};")
    if not len_rows or not len_rows[0][0] or len_rows[0][0].upper() == "NULL":
        return ""
    total = int(len_rows[0][0])
    parts: list[str] = []
    for start in range(1, total + 1, _VARCHAR_CHUNK_SIZE):
        chunk_rows = _query_rows(
            wallet_path,
            f"SELECT SUBSTRING({col}, {start}, {_VARCHAR_CHUNK_SIZE}) {from_clause};",
        )
        parts.append(chunk_rows[0][0] if chunk_rows else "")
    return "".join(parts)


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

    schema = _wallet_schema(wallet_path)
    wallet_tbl = _tbl(schema, "wallet")
    keystore_tbl = _tbl(schema, "keystore")
    wallet_node_tbl = _tbl(schema, "walletNode")
    block_tx_tbl = _tbl(schema, "blockTransaction")
    bthi_tbl = _tbl(schema, "blockTransactionHashIndex")

    wallet_rows = _query_rows(
        wallet_path,
        f"SELECT {_q('id')}, {_q('name')}, {_q('storedBlockHeight')}, {_q('scriptType')} "
        f"FROM {wallet_tbl} LIMIT 1;",
    )
    if not wallet_rows:
        raise RuntimeError(f"No wallet table row in {wallet_path}")
    wallet_id_raw, name, stored_height, script_type = wallet_rows[0]
    wallet_id = _safe_sql_int(wallet_id_raw, label="wallet id")
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
        f"SELECT {_q('masterFingerprint')}, {_q('derivationPath')} "
        f"FROM {keystore_tbl} WHERE {_q('wallet')} = {wallet_id} "
        f"ORDER BY {_q('index')} LIMIT 1;",
    )
    if not ks_rows:
        raise RuntimeError(f"No keystore in {wallet_path}")
    fingerprint, deriv_path = ks_rows[0]
    ks_from = (
        f"FROM {keystore_tbl} WHERE {_q('wallet')} = {wallet_id} "
        f"ORDER BY {_q('index')} LIMIT 1"
    )
    xpub = _fetch_column_chunks(wallet_path, column="extendedPublicKey", from_clause=ks_from)
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
        f"SELECT {_q('derivationPath')} FROM {wallet_node_tbl} "
        f"WHERE {_q('wallet')} = {wallet_id} "
        f"AND {_q('derivationPath')} LIKE '%/0/%' "
        f"ORDER BY {_q('id')};",
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
            RAWTOHEX(bt.{_q('txid')}),
            bthi.{_q('index')},
            bthi.{_q('outputValue')},
            bthi.{_q('height')},
            bthi.{_q('date')},
            bthi.{_q('label')},
            bthi.{_q('status')},
            bthi.{_q('spentBy')},
            wn.{_q('derivationPath')}
        FROM {bthi_tbl} bthi
        JOIN {block_tx_tbl} bt ON bt.{_q('hash')} = bthi.{_q('hash')}
        JOIN {wallet_node_tbl} wn ON wn.{_q('id')} = bthi.{_q('node')}
        WHERE bt.{_q('wallet')} = {wallet_id}
        ORDER BY bthi.{_q('outputValue')} DESC;
    """
    utxo_rows = _query_rows(wallet_path, utxo_sql)
    utxos: list[UtxoRecord] = []
    for row in utxo_rows:
        if len(row) != 9:
            raise RuntimeError(
                f"Malformed UTXO row from {wallet_path.name} ({len(row)} columns, expected 9). "
                "Close Sparrow if the wallet is open, then retry."
            )
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
    """Derive bc1q address for a wallet node path using embit.

    CRITICAL FIX (Real Steel pass 2 / Sonnet): the previous implementation always
    built a descriptor hardcoded to chain "0" and called
    ``desc.derive(chain, idx)``, which fills the descriptor's *wildcard* from the
    first argument (`chain`) and silently discards the second (`idx`, the real
    receive/change index) since this descriptor has no multipath branch. Every
    UTXO's address therefore collapsed to whatever the wildcard resolved to
    (effectively index 0 on chain 0) regardless of its true derivation path —
    breaking address-per-UTXO uniqueness and any PSBT built from it.
    """
    # node_path like m/84'/0'/0'/0/5 -> index 5 on external chain
    parts = node_path.split("/")
    idx = int(parts[-1])
    chain = int(parts[-2])
    return derive_address_for_chain_index(keystore, chain, idx)
