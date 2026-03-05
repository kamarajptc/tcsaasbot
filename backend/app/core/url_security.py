from __future__ import annotations

import ipaddress
import socket
from functools import lru_cache
from urllib.parse import urlparse


def _is_private_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


@lru_cache(maxsize=512)
def _resolve_host_ips(host: str) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return tuple()
    ips: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in ips:
            ips.append(addr)
    return tuple(ips)


def is_safe_outbound_url(url: str, *, require_https: bool = False) -> bool:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False
    if require_https and parsed.scheme != "https":
        return False
    if not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False

    host = parsed.hostname.strip().lower()
    if host in {"localhost", "localhost.localdomain"}:
        return False
    if host in {"example.com", "example.org", "example.net"}:
        return True
    if _is_private_ip(host):
        return False

    resolved = _resolve_host_ips(host)
    if not resolved:
        return False
    return not any(_is_private_ip(ip) for ip in resolved)
