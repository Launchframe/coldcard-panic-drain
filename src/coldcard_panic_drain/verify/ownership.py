"""Guided Wallet B ownership verification at plan."""

from __future__ import annotations

import sys
from typing import TextIO

from coldcard_panic_drain.plan.mapper import derive_receive_address
from coldcard_panic_drain.sparrow.models import WalletSnapshot

OWNERSHIP_ACK = "OWNERSHIP CONFIRMED"
_OWNERSHIP_EXIT = frozenset({"exit", "q"})


def _write_ownership_prompt(
    dest_wallet: WalletSnapshot,
    *,
    index: int,
    address: str,
    path: str,
    stdout: TextIO,
    retry: bool,
) -> None:
    if retry:
        stdout.write(
            f"\nNot recognized. Type {OWNERSHIP_ACK} after verifying on your signing device, "
            "or exit/q to abort: "
        )
        return

    account = dest_wallet.keystore.derivation_path.rstrip("/")
    stdout.write(
        "\n"
        "=== Wallet B ownership check (required) ===\n"
        f"Wallet file: {dest_wallet.name}\n"
        f"Fingerprint: {dest_wallet.keystore.fingerprint}\n"
        f"Account:     {account}\n"
        f"Next receive index: {index}\n"
        f"Address:     {address}\n"
        f"Path:        {path}\n\n"
        "This proves the Sparrow Wallet B file matches the device you will sign with.\n"
        "On Coldcard: Advanced → View Identity → Address → select the index above.\n"
        "Confirm the address on the device matches what is shown here.\n"
        "If Sparrow Wallet B is open elsewhere, you may cross-check the same index there.\n\n"
        f"Type {OWNERSHIP_ACK} after verifying on your signing device "
        "(or exit/q to abort): "
    )


def confirm_dest_wallet_ownership(
    dest_wallet: WalletSnapshot,
    *,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> int:
    """Prompt operator to prove Sparrow Wallet B matches the signing device.

    Verifies the next receive index on Coldcard (or other HW) matches the address
    derived from the destination `.mv.db` xpub. Returns the checked receive index.
    """
    account = dest_wallet.keystore.derivation_path.rstrip("/")
    index = dest_wallet.next_receive_index
    address = derive_receive_address(dest_wallet, index)
    path = f"{account}/0/{index}"

    retry = False
    while True:
        _write_ownership_prompt(
            dest_wallet,
            index=index,
            address=address,
            path=path,
            stdout=stdout,
            retry=retry,
        )
        stdout.flush()
        raw = stdin.readline()
        if raw == "":
            # EOF (closed/exhausted stdin) — never treat as "just retry" or the
            # loop would spin forever re-printing the prompt with no way for a
            # non-interactive caller to make progress.
            raise ValueError(
                "Aborted: destination wallet ownership not confirmed (no input received)."
            )
        line = raw.strip()
        if line == OWNERSHIP_ACK:
            return index
        if line.lower() in _OWNERSHIP_EXIT:
            raise ValueError(
                "Aborted: destination wallet ownership not confirmed."
            )
        retry = True
