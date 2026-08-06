"""RPC URL validation tests."""

import pytest

from coldcard_panic_drain.broadcast.rpc_url import (
    assert_loopback_rpc_url,
    assert_rpc_url,
    is_onion_rpc_host,
    validate_onion_rpc_access,
)

ONION_HOST = f"{'a' * 56}.onion"
ONION_HTTP = f"http://{ONION_HOST}:8332"
ONION_HTTPS = f"https://{ONION_HOST}:8332"


def test_loopback_urls_ok():
    assert_loopback_rpc_url("http://127.0.0.1:8332")
    assert_loopback_rpc_url("http://localhost:8332")


def test_local_mdns_urls_ok():
    assert_loopback_rpc_url("https://happy-feet.local:8332")
    assert_loopback_rpc_url("http://Happy-Feet.Local.:8332")


def test_remote_url_rejected():
    with pytest.raises(ValueError, match=r"localhost|\.local|\.onion"):
        assert_loopback_rpc_url("http://192.168.1.50:8332")


def test_public_host_rejected():
    with pytest.raises(ValueError, match=r"localhost|\.local|\.onion"):
        assert_loopback_rpc_url("http://bitcoin.example.com:8332")


def test_onion_host_detection():
    assert is_onion_rpc_host(ONION_HOST)
    assert not is_onion_rpc_host("bitcoin.example.com")


def test_onion_url_rejected_without_flag():
    with pytest.raises(ValueError, match="allow-onion-rpc"):
        assert_rpc_url(ONION_HTTP, allow_onion=False)


def test_onion_http_and_https_ok_with_flag():
    assert_rpc_url(ONION_HTTP, allow_onion=True) == ONION_HTTP
    assert_rpc_url(ONION_HTTPS, allow_onion=True) == ONION_HTTPS


def test_validate_onion_access_requires_both_flags():
    with pytest.raises(ValueError, match="allow-onion-rpc"):
        validate_onion_rpc_access(ONION_HTTP, allow_onion=False, privacy_ack=False)
    with pytest.raises(ValueError, match="allow-onion-rpc"):
        validate_onion_rpc_access(ONION_HTTP, allow_onion=True, privacy_ack=False)


def test_validate_onion_access_ok():
    assert validate_onion_rpc_access(ONION_HTTP, allow_onion=True, privacy_ack=True)


def test_onion_flags_rejected_for_loopback_url():
    with pytest.raises(ValueError, match="apply only"):
        validate_onion_rpc_access("http://127.0.0.1:8332", allow_onion=True, privacy_ack=True)
