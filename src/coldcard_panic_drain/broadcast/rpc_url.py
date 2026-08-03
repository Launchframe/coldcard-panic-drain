"""Local-network validation for Bitcoin Core RPC URLs."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def _is_local_mdns_host(host: str) -> bool:
    h = host.strip().lower().rstrip(".")
    return h == "localhost" or h.endswith(".local")


def assert_loopback_rpc_url(url: str) -> str:
    """Accept loopback and *.local RPC hosts; reject public/remote hosts."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"RPC URL must be http(s): {url}")
    host = parsed.hostname
    if not host:
        raise ValueError(f"RPC URL missing host: {url}")
    if _is_local_mdns_host(host):
        return url
    try:
        if ipaddress.ip_address(host).is_loopback:
            return url
    except ValueError:
        pass
    raise ValueError(
        f"RPC URL must point to localhost or a *.local host, not {host!r}. "
        "Use Sparrow for manual broadcast to remote nodes."
    )
