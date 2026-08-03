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


def test_mdns_pending_allows_resolved_ip():
    """create_connection to *.local may connect() to a resolved non-loopback IP."""
    assert not _is_allowed_host("8.8.8.8")
    network_guard._pending.hostname = "node.local"
    try:
        assert _is_allowed_host("8.8.8.8")
    finally:
        network_guard._pending.hostname = None
    assert not _is_allowed_host("8.8.8.8")


def test_restore_after_disable():
    enable_localhost_guard()
    disable_localhost_guard()
    s = socket.socket()
    s.close()
