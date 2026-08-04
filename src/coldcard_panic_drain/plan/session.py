"""Drain session state persisted only in output dir."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from coldcard_panic_drain.psbt.fees import estimate_psbt_fee_sats
from coldcard_panic_drain.sparrow.models import (
    DestinationAssignment,
    LabelSource,
    SkipReason,
    UtxoRecord,
    WalletSnapshot,
)


@dataclass
class DrainSession:
    source_path: str
    dest_path: str
    chain_tip_height: int
    fee_base: int
    fee_jitter: float
    min_blocks_apart: int
    spread_hours: float
    schedule_jitter: float = 0.35
    utxos: list[dict[str, Any]] = field(default_factory=list)
    assignments: list[dict[str, Any]] = field(default_factory=list)
    mapping_confirmed: bool = False
    dest_ownership_confirmed: bool = False
    dest_ownership_checked_index: int = -1
    dest_xpub: str = ""
    dest_fingerprint: str = ""
    source_xpub: str = ""
    source_fingerprint: str = ""
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    quiet_hours_timezone: Optional[str] = None
    calendar_alarm_minutes: int = 15

    @classmethod
    def from_wallets(
        cls,
        source: WalletSnapshot,
        dest: WalletSnapshot,
        fee_base: int,
        fee_jitter: float,
        min_blocks_apart: int,
        spread_hours: float,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
        quiet_hours_timezone: Optional[str] = None,
        calendar_alarm_minutes: int = 15,
        schedule_jitter: float = 0.35,
    ) -> "DrainSession":
        return cls(
            source_path=source.path,
            dest_path=dest.path,
            chain_tip_height=source.chain_tip_height,
            fee_base=fee_base,
            fee_jitter=fee_jitter,
            min_blocks_apart=min_blocks_apart,
            spread_hours=spread_hours,
            schedule_jitter=schedule_jitter,
            utxos=[_utxo_to_dict(u) for u in source.utxos],
            dest_xpub=dest.keystore.xpub,
            dest_fingerprint=dest.keystore.fingerprint,
            source_xpub=source.keystore.xpub,
            source_fingerprint=source.keystore.fingerprint,
            quiet_hours_start=quiet_hours_start,
            quiet_hours_end=quiet_hours_end,
            quiet_hours_timezone=quiet_hours_timezone,
            calendar_alarm_minutes=calendar_alarm_minutes,
        )

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "DrainSession":
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("quiet_hours_start", None)
        data.setdefault("quiet_hours_end", None)
        data.setdefault("quiet_hours_timezone", None)
        data.setdefault("calendar_alarm_minutes", 15)
        data.setdefault("schedule_jitter", 0.35)
        if "mapping_confirmed" not in data and "addresses_confirmed" in data:
            data["mapping_confirmed"] = data["addresses_confirmed"]
        data.pop("addresses_confirmed", None)
        return cls(**data)

    def quiet_hours(self):
        from coldcard_panic_drain.schedule.quiet_hours import parse_quiet_hours

        return parse_quiet_hours(
            self.quiet_hours_start,
            self.quiet_hours_end,
            self.quiet_hours_timezone,
        )

    def utxo_objects(self) -> list[UtxoRecord]:
        out: list[UtxoRecord] = []
        for d in self.utxos:
            u = UtxoRecord(
                txid=d["txid"],
                vout=d["vout"],
                value_sats=d["value_sats"],
                height=d["height"],
                received_at=None,
                address=d["address"],
                derivation_path=d["derivation_path"],
                label=d.get("label", ""),
                frozen=d.get("frozen", False),
                included=d.get("included", True),
            )
            if d.get("skip_reason"):
                u.skip_reason = SkipReason(d["skip_reason"])
            if d.get("label_source"):
                u.label_source = LabelSource(d["label_source"])
            out.append(u)
        return out

    def update_utxo(self, utxo: UtxoRecord) -> None:
        for d in self.utxos:
            if d["txid"] == utxo.txid and d["vout"] == utxo.vout:
                d["label"] = utxo.label
                d["included"] = utxo.included
                d["skip_reason"] = utxo.skip_reason.value if utxo.skip_reason else None
                d["label_source"] = utxo.label_source.value if utxo.label_source else None
                return
        raise KeyError(utxo.ref)

    def set_assignments(self, assignments: list[DestinationAssignment]) -> None:
        self.assignments = [
            {
                "utxo_ref": a.utxo.ref,
                "receive_index": a.receive_index,
                "address": a.address,
                "fee_sat_vb": a.fee_sat_vb,
                "fee_sats": a.fee_sats,
                "nlocktime": a.nlocktime,
                "psbt_filename": a.psbt_filename,
                "label": a.utxo.label,
                "value_sats": a.utxo.value_sats,
            }
            for a in assignments
        ]

    def require_plan_gates(self) -> None:
        """Abort generate if mandatory human checks from `plan` were not completed."""
        if not self.dest_ownership_confirmed:
            raise ValueError(
                "Destination wallet ownership was not confirmed during `plan`. "
                "Re-run `plan` and complete the Wallet B ownership check."
            )
        if not self.mapping_confirmed:
            raise ValueError(
                "UTXO mapping was not confirmed during `plan`. "
                "Re-run `plan` and review the mapping table."
            )

    def verify_dest_wallet(self, dest: WalletSnapshot) -> None:
        """Abort if Wallet B identity changed since plan (wallet-swap detection)."""
        if not self.dest_xpub or not self.dest_fingerprint:
            raise ValueError(
                "Session missing destination wallet snapshot — re-run `plan` "
                "to capture Wallet B xpub/fingerprint."
            )
        if dest.keystore.xpub != self.dest_xpub:
            raise ValueError(
                "Destination wallet xpub changed since plan — wrong Wallet B file "
                "or keystore rotated. Re-run `plan` after confirming the correct wallet."
            )
        if dest.keystore.fingerprint != self.dest_fingerprint:
            raise ValueError(
                "Destination wallet fingerprint changed since plan — possible "
                "wallet swap. Re-run `plan` with the intended Wallet B."
            )

    def verify_source_wallet(self, source: WalletSnapshot) -> None:
        """Abort if Wallet A identity changed since plan (source wallet-swap detection).

        Mirrors `verify_dest_wallet`. Without this, swapping `--source` (or the
        file at that path) between `plan` and `generate` would silently build
        PSBTs against session-cached UTXO data that no longer matches the wallet
        actually loaded — the prior pass only snapshotted the destination side.
        """
        if not self.source_xpub or not self.source_fingerprint:
            raise ValueError(
                "Session missing source wallet snapshot — re-run `plan` "
                "to capture Wallet A xpub/fingerprint."
            )
        if source.keystore.xpub != self.source_xpub:
            raise ValueError(
                "Source wallet xpub changed since plan — wrong Wallet A file "
                "or keystore rotated. Re-run `plan` after confirming the correct wallet."
            )
        if source.keystore.fingerprint != self.source_fingerprint:
            raise ValueError(
                "Source wallet fingerprint changed since plan — possible "
                "wallet swap. Re-run `plan` with the intended Wallet A."
            )

    def assignment_objects(self, utxos: list[UtxoRecord]) -> list[DestinationAssignment]:
        if not self.assignments:
            raise ValueError("Session has no assignments — run `plan` first.")
        utxo_by_ref = {u.ref: u for u in utxos}
        out: list[DestinationAssignment] = []
        for d in self.assignments:
            u = utxo_by_ref.get(d["utxo_ref"])
            if u is None:
                raise ValueError(
                    f"Session assignment references unknown UTXO {d['utxo_ref']}"
                )
            fee_sat_vb = d["fee_sat_vb"]
            out.append(
                DestinationAssignment(
                    utxo=u,
                    receive_index=d["receive_index"],
                    address=d["address"],
                    fee_sat_vb=fee_sat_vb,
                    fee_sats=d.get("fee_sats", estimate_psbt_fee_sats(fee_sat_vb)),
                    nlocktime=d["nlocktime"],
                    psbt_filename=d["psbt_filename"],
                )
            )
        return out


def _utxo_to_dict(u: UtxoRecord) -> dict[str, Any]:
    return {
        "txid": u.txid,
        "vout": u.vout,
        "value_sats": u.value_sats,
        "height": u.height,
        "address": u.address,
        "derivation_path": u.derivation_path,
        "label": u.label,
        "frozen": u.frozen,
        "included": u.included,
        "skip_reason": u.skip_reason.value if u.skip_reason else None,
        "label_source": u.label_source.value if u.label_source else None,
    }


def session_path(output_dir: Path) -> Path:
    return output_dir / "labels-session.json"
