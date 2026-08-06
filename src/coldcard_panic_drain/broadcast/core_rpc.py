"""Bitcoin Core JSON-RPC client (localhost, *.local, optional .onion)."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from coldcard_panic_drain.broadcast.rpc_url import assert_rpc_url
from coldcard_panic_drain.network_guard import (
    NetworkBlockedError,
    disable_onion_connections,
    enable_onion_connections,
)


class CoreRpcError(RuntimeError):
    pass


class CoreRpcClient:
    def __init__(
        self,
        url: str,
        *,
        cookie_file: Optional[Path] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        allow_onion: bool = False,
    ) -> None:
        self.url = assert_rpc_url(url, allow_onion=allow_onion)
        self._allow_onion = allow_onion
        self._auth_header = self._build_auth(cookie_file, user, password)
        if allow_onion:
            enable_onion_connections()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @staticmethod
    def _build_auth(
        cookie_file: Optional[Path],
        user: Optional[str],
        password: Optional[str],
    ) -> str:
        if cookie_file is not None:
            try:
                raw = cookie_file.expanduser().read_text(encoding="utf-8").strip()
            except OSError as e:
                raise ValueError(f"Cannot read RPC cookie file {cookie_file}: {e}") from e
            token = base64.b64encode(raw.encode()).decode()
            return f"Basic {token}"
        if user is not None and password is not None:
            token = base64.b64encode(f"{user}:{password}".encode()).decode()
            return f"Basic {token}"
        raise ValueError("Provide --rpc-cookie-file or --rpc-user and --rpc-password.")

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        params = params or []
        payload = json.dumps({"jsonrpc": "1.0", "id": "cpd", "method": method, "params": params}).encode()
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": self._auth_header},
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=60) as resp:
                body = json.loads(resp.read().decode())
        except NetworkBlockedError as e:
            raise CoreRpcError(
                "RPC blocked by network guard. "
                "Use a localhost / *.local --rpc-url, or pass --allow-onion-rpc for a .onion host."
            ) from e
        except urllib.error.HTTPError as e:
            raise CoreRpcError(f"RPC HTTP {e.code}: {e.read().decode()}") from e
        except urllib.error.URLError as e:
            raise CoreRpcError(f"RPC connection failed: {e}") from e
        if body.get("error"):
            raise CoreRpcError(str(body["error"]))
        return body.get("result")

    def close(self) -> None:
        if self._allow_onion:
            disable_onion_connections()

    def send_raw_transaction(self, hex_tx: str) -> str:
        return self.call("sendrawtransaction", [hex_tx])

    def get_raw_transaction(self, txid: str) -> Optional[dict]:
        try:
            return self.call("getrawtransaction", [txid, True])
        except CoreRpcError:
            return None

    def test_mempool_accept(self, hex_tx: str) -> list[dict]:
        try:
            return self.call("testmempoolaccept", [[hex_tx]])
        except CoreRpcError:
            return []
