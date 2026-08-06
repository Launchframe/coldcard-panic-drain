"""Tests for localhost-only network guard."""

import socket

import pytest

from coldcard_panic_drain import network_guard
from coldcard_panic_drain.network_guard import (
    NetworkBlockedError,
    _is_allowed_host,
    _strip_ipv6_zone,
    disable_localhost_guard,
    enable_localhost_guard,
)


def test_loopback_socket_allowed():
    enable_localhost_guard()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.close()
    finally:
        disable_localhost_guard()


def test_non_loopback_connect_blocked():
    enable_localhost_guard()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with pytest.raises(NetworkBlockedError):
            s.connect(("8.8.8.8", 80))
        s.close()
    finally:
        disable_localhost_guard()


def test_private_lan_connect_allowed():
    enable_localhost_guard()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect_ex(("192.168.1.50", 8332))
        s.close()
    finally:
        disable_localhost_guard()


def test_shared_address_space_allowed():
    """RFC 6598 100.64.0.0/10 (CGNAT) used by some home routers / Tailscale-like setups."""
    assert _is_allowed_host("100.64.0.1")
    assert _is_allowed_host("100.127.255.254")
    assert not _is_allowed_host("100.63.255.255")
    assert not _is_allowed_host("100.128.0.1")


def test_ipv6_zone_id_stripped_and_link_local_allowed():
    assert _strip_ipv6_zone("fe80::1%eth0") == "fe80::1"
    assert _strip_ipv6_zone("fe80::abcd:1%en0") == "fe80::abcd:1"
    assert _is_allowed_host("fe80::1%eth0")


def test_local_mdns_hostname_allowed():
    assert _is_allowed_host("happy-feet.local")
    assert _is_allowed_host("Happy-Feet.Local.")


def test_mdns_pending_allows_only_prevalidated_resolved_ips():
    """create_connection to *.local may connect() to an IP it already vetted.

    The pending set must only ever contain candidates that independently passed
    _is_allowed_ip (private/loopback/link-local/CGNAT) — never an arbitrary
    resolved address. A public IP must stay blocked even while a *.local lookup
    is in flight, otherwise a poisoned resolver could point a *.local name at
    any remote host and bypass the guard entirely.
    """
    assert not _is_allowed_host("8.8.8.8")
    network_guard._pending.allowed_ips = {"192.168.1.50"}
    try:
        assert _is_allowed_host("192.168.1.50")
        # The pending set must never act as a blanket bypass for other addresses,
        # even while a *.local lookup is in flight for a different host.
        assert not _is_allowed_host("8.8.8.8")
    finally:
        network_guard._pending.allowed_ips = None
    assert getattr(network_guard._pending, "allowed_ips", None) is None


def test_resolve_allowed_ips_filters_out_public_addresses(monkeypatch):
    """A *.local name that resolves to a public IP must not be trusted."""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert network_guard._resolve_allowed_ips("evil.local", 8332) == set()


def test_resolve_allowed_ips_keeps_private_addresses(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert network_guard._resolve_allowed_ips("node.local", 8332) == {"192.168.1.50"}


def test_create_connection_to_local_name_resolving_public_is_blocked(monkeypatch):
    """End-to-end: a *.local RPC host that resolves publicly must be rejected."""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    enable_localhost_guard()
    try:
        with pytest.raises(NetworkBlockedError):
            socket.create_connection(("evil.local", 8332), timeout=1)
    finally:
        disable_localhost_guard()


def test_guarded_create_connection_lets_connect_see_prevalidated_ip(monkeypatch):
    """Exercise `_guarded_create_connection` directly (no global socket patching):

    connect() must see the resolved private IP as allowed via the pending set, and
    the pending set must be cleared again once the call returns.
    """
    seen_by_connect = []

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", port))]

    def fake_original_create_connection(address, *args, **kwargs):
        # Exercises the same _check_host() that the real _LocalhostSocket.connect()
        # runs, without opening a real socket.
        seen_by_connect.append(_is_allowed_host(str(address[0])))
        return object()

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(network_guard, "_ORIGINAL_CREATE_CONNECTION", fake_original_create_connection)

    network_guard._guarded_create_connection(("node.local", 8332))

    assert seen_by_connect == [True]
    assert getattr(network_guard._pending, "allowed_ips", None) is None


def test_restore_after_disable():
    enable_localhost_guard()
    disable_localhost_guard()
    s = socket.socket()
    s.close()


def test_onion_host_blocked_by_default():
    onion = f"{'b' * 56}.onion"
    assert not _is_allowed_host(onion)


def test_onion_host_allowed_when_opt_in_enabled():
    from coldcard_panic_drain.network_guard import (
        disable_onion_connections,
        enable_onion_connections,
    )

    onion = f"{'b' * 56}.onion"
    enable_onion_connections()
    try:
        assert _is_allowed_host(onion)
    finally:
        disable_onion_connections()
    assert not _is_allowed_host(onion)


def test_non_onion_blocked_uses_localhost_msg_when_onion_opt_in_enabled():
    from coldcard_panic_drain.network_guard import (
        _check_host,
        disable_onion_connections,
        enable_onion_connections,
        NetworkBlockedError,
    )

    enable_onion_connections()
    try:
        with pytest.raises(NetworkBlockedError, match="localhost or local"):
            _check_host("8.8.8.8")
    finally:
        disable_onion_connections()
