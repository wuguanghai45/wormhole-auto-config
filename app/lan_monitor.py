"""Host LAN interface monitoring helpers."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Optional

import psutil

from app.i18n import t


@dataclass(frozen=True)
class LanAddress:
    """IPv4 address observed on a host interface."""

    interface: str
    ip: str


def _is_usable_ipv4(address: str) -> bool:
    """Return True for non-loopback, non-link-local IPv4 addresses."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.version != 4:
        return False
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
        return False
    return True


def _is_af_inet(family: object) -> bool:
    """Return True when an address family represents IPv4."""
    try:
        return int(family) == int(socket.AF_INET)
    except (TypeError, ValueError):
        return family == socket.AF_INET


def list_ipv4_addresses(preferred_interface: str = "") -> list[LanAddress]:
    """List usable IPv4 addresses on up interfaces, optionally filtered."""
    preferred = preferred_interface.strip()
    results: list[LanAddress] = []
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()

    for name, entries in addrs.items():
        if preferred and name != preferred:
            continue
        if name.startswith("lo"):
            continue
        iface_stats = stats.get(name)
        if iface_stats is not None and not iface_stats.isup:
            continue
        for entry in entries:
            if not _is_af_inet(entry.family):
                continue
            address = entry.address
            if not address or not _is_usable_ipv4(address):
                continue
            results.append(LanAddress(interface=name, ip=address))
    return results


def find_lan_address(preferred_interface: str = "") -> Optional[LanAddress]:
    """Return the first usable LAN IPv4 address, preferring the given interface."""
    addresses = list_ipv4_addresses(preferred_interface)
    if addresses:
        return addresses[0]
    return None


def format_lan_snapshot(preferred_interface: str = "", locale: str = "zh-CN") -> str:
    """Human-readable snapshot of candidate LAN addresses for logs."""
    addresses = list_ipv4_addresses(preferred_interface)
    if not addresses and preferred_interface.strip():
        return t(locale, "lan.no_ip_on_iface", iface=preferred_interface)
    if not addresses:
        return t(locale, "lan.none")
    return ", ".join(f"{item.interface}={item.ip}" for item in addresses)
