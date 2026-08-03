"""Bitcoin Core RPC client tests."""

from pathlib import Path
from unittest.mock import patch

import pytest

from coldcard_panic_drain.broadcast.core_rpc import CoreRpcClient, CoreRpcError
from coldcard_panic_drain.network_guard import NetworkBlockedError


def test_missing_cookie_file_raises_value_error(tmp_path: Path):
    missing = tmp_path / "no-cookie.txt"
    with pytest.raises(ValueError, match="Cannot read RPC cookie file"):
        CoreRpcClient("http://127.0.0.1:8332", cookie_file=missing)


def test_cookie_file_auth_header(tmp_path: Path):
    cookie = tmp_path / ".cookie"
    cookie.write_text("user:pass", encoding="utf-8")
    client = CoreRpcClient("http://127.0.0.1:8332", cookie_file=cookie)
    assert client._auth_header.startswith("Basic ")


def test_network_guard_surfaces_as_core_rpc_error():
    client = CoreRpcClient("http://127.0.0.1:8332", user="u", password="p")
    with patch.object(client._opener, "open", side_effect=NetworkBlockedError("blocked")):
        with pytest.raises(CoreRpcError, match="localhost network guard"):
            client.call("getblockchaininfo")
