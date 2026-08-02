"""RPC URL validation tests."""

import pytest

from coldcard_panic_drain.broadcast.rpc_url import assert_loopback_rpc_url


def test_loopback_urls_ok():
    assert_loopback_rpc_url("http://127.0.0.1:8332")
    assert_loopback_rpc_url("http://localhost:8332")


def test_remote_url_rejected():
    with pytest.raises(ValueError, match="localhost"):
        assert_loopback_rpc_url("http://192.168.1.50:8332")
