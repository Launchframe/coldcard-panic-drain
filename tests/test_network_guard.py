"""Tests for localhost-only network guard."""

import socket

import pytest

from coldcard_panic_drain.network_guard import (
    NetworkBlockedError,
    _is_allowed_host,
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


def test_local_mdns_hostname_allowed():
    assert _is_allowed_host("happy-feet.local")
    assert _is_allowed_host("Happy-Feet.Local.")


def test_restore_after_disable():
    enable_localhost_guard()
    disable_localhost_guard()
    s = socket.socket()
    s.close()
