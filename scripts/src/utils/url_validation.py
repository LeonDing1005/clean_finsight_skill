"""Validation helpers for outbound public-web requests."""

import ipaddress
from urllib.parse import urlparse


def validate_public_http_url(url: str) -> str | None:
    """Return an error for URLs that are unsuitable for the public web fetcher."""
    parsed = urlparse(str(url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "URL must use http or https and include a hostname"

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return "Local and internal hostnames are not allowed"

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None

    if not address.is_global:
        return "Private, loopback, and link-local IP addresses are not allowed"
    return None
