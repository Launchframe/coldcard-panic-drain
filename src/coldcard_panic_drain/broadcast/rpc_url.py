"""Local-network validation for Bitcoin Core RPC URLs."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def is_onion_rpc_host(host: str) -> bool:
    """True for v2/v3 hidden-service hostnames (…onion)."""
    h = host.strip().lower().rstrip(".")
    return h.endswith(".onion") and len(h) > len(".onion")


def _is_local_mdns_host(host: str) -> bool:
    h = host.strip().lower().rstrip(".")
    return h == "localhost" or h.endswith(".local")


def assert_rpc_url(url: str, *, allow_onion: bool = False) -> str:
    """Accept loopback, *.local, and (optionally) .onion RPC hosts."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"RPC URL must be http(s): {url}")
    host = parsed.hostname
    if not host:
        raise ValueError(f"RPC URL missing host: {url}")
    if is_onion_rpc_host(host):
        if not allow_onion:
            raise ValueError(
                f"RPC URL host {host!r} is a Tor .onion address. "
                "Pass --allow-onion-rpc and --i-understand-onion-privacy-risk on "
                "broadcast-due to use it."
            )
        return url
    if _is_local_mdns_host(host):
        return url
    try:
        if ipaddress.ip_address(host).is_loopback:
            return url
    except ValueError:
        pass
    raise ValueError(
        f"RPC URL must point to localhost, a *.local host, or (with flags) a .onion "
        f"hidden service — not {host!r}. Use Sparrow for manual broadcast to other remotes."
    )


def validate_onion_rpc_access(url: str, allow_onion: bool, privacy_ack: bool) -> bool:
    """Return True when `url` is .onion and both opt-in flags are set."""
    host = urlparse(url).hostname or ""
    if not is_onion_rpc_host(host):
        if allow_onion or privacy_ack:
            raise ValueError(
                "--allow-onion-rpc and --i-understand-onion-privacy-risk apply only "
                "when --rpc-url uses a .onion host."
            )
        return False
    if not allow_onion or not privacy_ack:
        raise ValueError(
            "Tor .onion RPC requires --allow-onion-rpc and "
            "--i-understand-onion-privacy-risk on broadcast-due."
        )
    return True


def assert_loopback_rpc_url(url: str) -> str:
    """Accept loopback and *.local RPC hosts; reject public/remote hosts."""
    return assert_rpc_url(url, allow_onion=False)
