"""RPC URL validation tests."""

import pytest

from coldcard_panic_drain.broadcast.rpc_url import assert_loopback_rpc_url


def test_loopback_urls_ok():
    assert_loopback_rpc_url("http://127.0.0.1:8332")
    assert_loopback_rpc_url("http://localhost:8332")


def test_local_mdns_urls_ok():
    assert_loopback_rpc_url("https://happy-feet.local:8332")
    assert_loopback_rpc_url("http://Happy-Feet.Local.:8332")


def test_remote_url_rejected():
    with pytest.raises(ValueError, match=r"localhost|\.local"):
        assert_loopback_rpc_url("http://192.168.1.50:8332")


def test_public_host_rejected():
    with pytest.raises(ValueError, match=r"localhost|\.local"):
        assert_loopback_rpc_url("http://bitcoin.example.com:8332")
