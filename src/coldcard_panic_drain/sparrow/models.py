"""Data models for Sparrow wallet reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SkipReason(str, Enum):
    FROZEN = "frozen"
    USER_SKIPPED = "user_skipped"
    UNLABELED = "unlabeled"


class LabelSource(str, Enum):
    EXISTING = "existing"
    USER_PROMPTED = "user_prompted"


@dataclass
class KeystoreInfo:
    fingerprint: str
    derivation_path: str
    xpub: str
    origin: str  # BIP-329 origin descriptor fragment


@dataclass
class UtxoRecord:
    txid: str
    vout: int
    value_sats: int
    height: int
    received_at: Optional[datetime]
    address: str
    derivation_path: str
    label: str = ""
    frozen: bool = False
    spent: bool = False
    # user session fields
    skip_reason: Optional[SkipReason] = None
    label_source: Optional[LabelSource] = None
    included: bool = True

    @property
    def ref(self) -> str:
        return f"{self.txid}:{self.vout}"

    @property
    def btc(self) -> float:
        return self.value_sats / 100_000_000


@dataclass
class WalletSnapshot:
    path: str
    name: str
    chain_tip_height: int
    keystore: KeystoreInfo
    utxos: list[UtxoRecord] = field(default_factory=list)
    used_receive_indices: list[int] = field(default_factory=list)
    used_receive_addresses: list[str] = field(default_factory=list)

    @property
    def next_receive_index(self) -> int:
        """Smallest external receive index with no prior on-chain use."""
        from coldcard_panic_drain.sparrow.receive import next_free_receive_index

        return next_free_receive_index(self)


@dataclass
class DestinationAssignment:
    utxo: UtxoRecord
    receive_index: int
    address: str
    fee_sat_vb: int
    fee_sats: int
    nlocktime: int
    psbt_filename: str = ""
