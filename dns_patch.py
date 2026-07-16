#!/usr/bin/env python3
"""
Optional DNS helper for Eastmoney/akshare access issues.

Some networks return unstable DNS results for Eastmoney hosts used by akshare.
Import this module before calling akshare if requests to Eastmoney fail with
name resolution errors.
"""

from __future__ import annotations

import socket


EASTMONEY_HOSTS = {
    "push2.eastmoney.com": "202.108.253.154",
    "push2his.eastmoney.com": "202.108.253.154",
    "datacenter-web.eastmoney.com": "202.108.253.154",
}


_original_getaddrinfo = socket.getaddrinfo


def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    mapped_host = EASTMONEY_HOSTS.get(host, host)
    return _original_getaddrinfo(mapped_host, port, family, type, proto, flags)


def apply_patch() -> None:
    """Apply the DNS host mapping process-wide."""
    socket.getaddrinfo = patched_getaddrinfo


if __name__ == "__main__":
    apply_patch()
    print("DNS patch applied for Eastmoney hosts.")
