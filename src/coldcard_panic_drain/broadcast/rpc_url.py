"""Loopback validation for Bitcoin Core RPC URLs."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def assert_loopback_rpc_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"RPC URL must be http(s): {url}")
    host = parsed.hostname
    if not host:
        raise ValueError(f"RPC URL missing host: {url}")
    h = host.lower()
    if h == "localhost":
        return url
    try:
        if ipaddress.ip_address(h).is_loopback:
            return url
    except ValueError:
        pass
    raise ValueError(
        f"RPC URL must point to localhost (127.0.0.1 / ::1), not {host!r}. "
        "Use Sparrow for manual broadcast to remote nodes."
    )
