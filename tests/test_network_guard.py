"""Tests for zero-network guard."""

import socket

import pytest

from coldcard_panic_drain.network_guard import (
    NetworkBlockedError,
    disable_network_guard,
    enable_network_guard,
)


def test_socket_blocked_after_guard():
    enable_network_guard()
    with pytest.raises(NetworkBlockedError):
        socket.socket()
    disable_network_guard()


def test_socket_works_after_disable():
    enable_network_guard()
    disable_network_guard()
    # Should not raise (we only test creation, not connect)
    s = socket.socket()
    s.close()
