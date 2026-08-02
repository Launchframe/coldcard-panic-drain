"""Tests for localhost-only network guard."""

import socket

import pytest

from coldcard_panic_drain.network_guard import (
    NetworkBlockedError,
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


def test_restore_after_disable():
    enable_localhost_guard()
    disable_localhost_guard()
    s = socket.socket()
    s.close()
