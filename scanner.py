#!/usr/bin/env python3
"""
NetBox Scanner
 - Scan a single IP (--ip)
 - Scan a full prefix (--prefix)
 - Auto mode (--auto): find all prefixes with cf scan_enabled=true and scan them

Relies on:
  config.py          -> NETBOX_URL, NETBOX_API_TOKEN, MAX_CONCURRENT_IP_SCANS, SCAN_TIMEOUT
  logging_setup.py   -> setup_logger(name) returning a configured logger
"""

import os
import sys
import subprocess
import ipaddress
import socket
from datetime import datetime
from typing import Optional, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

import pynetbox

from config import (
    NETBOX_URL,
    NETBOX_API_TOKEN,
    MAX_CONCURRENT_IP_SCANS,
    SCAN_TIMEOUT,
)
from logging_setup import setup_logger

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------
logger = setup_logger("scanner")

# Coerce to ints in case config provides strings
_MAX_IP_WORKERS = int(MAX_CONCURRENT_IP_SCANS or 32)

if not NETBOX_URL:
    sys.exit("NETBOX_URL must be set in config.py")
if not NETBOX_API_TOKEN:
    sys.exit("NETBOX_API_TOKEN must be set in config.py")

netbox = pynetbox.api(NETBOX_URL, token=NETBOX_API_TOKEN)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def log_error(message: str) -> None:
    """Log scan errors with timestamp (kept for compatibility with existing logs)."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.error(f"{ts} - {message}")


def is_pingable(ip: str) -> bool:
    """Use fping to test reachability."""
    try:
        res = subprocess.run(
            ["/usr/sbin/fping", "-q", "-r1", "-t500", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return res.returncode == 0
    except FileNotFoundError:
        try:
            res = subprocess.run(
                ["/usr/bin/fping", "-q", "-r1", "-t500", ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return res.returncode == 0
        except Exception as e:
            log_error(f"Ping exception (no fping) {ip}: {e}")
            return False
    except Exception as e:
        log_error(f"Ping exception {ip}: {e}")
        return False


def get_mac(ip: str) -> Optional[str]:
    """Return MAC address if present in ARP/ND cache."""
    try:
        out = subprocess.check_output(["/usr/sbin/ip", "neigh", "show", ip]).decode()
        for line in out.splitlines():
            if "lladdr" in line:
                return line.split("lladdr")[1].split()[0]
    except FileNotFoundError:
        try:
            out = subprocess.check_output(["/sbin/ip", "neigh", "show", ip]).decode()
            for line in out.splitlines():
                if "lladdr" in line:
                    return line.split("lladdr")[1].split()[0]
        except Exception:
            return None
    except subprocess.CalledProcessError:
        return None
    except Exception as e:
        log_error(f"MAC lookup failed for {ip}: {e}")
    return None


def get_dns(ip: str) -> Optional[str]:
    """Reverse DNS; silence errors."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


# -----------------------------------------------------------------------------
# NetBox updates
# -----------------------------------------------------------------------------
def _first_or_none(recordset: Iterable) -> Optional[object]:
    """Return first element of an iterable RecordSet or None."""
    return next(iter(recordset), None)


def scan_ip(ip_str: str, prefixlen: int = 32) -> None:
    """
    Perform a single-IP scan and update or create the /32 entry in NetBox.
    - Updates custom fields: reachability, last_scan, last_online, mac_address
    - Updates dns_name if changed (when DNS is available)
    - Creates a new record if host is Online and no record exists
    """
    pinged = is_pingable(ip_str)
    dns = get_dns(ip_str) if pinged else None
    mac = get_mac(ip_str) if pinged else None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "Online" if pinged else "Offline"

    try:
        obj = netbox.ipam.ip_addresses.get(address=f"{ip_str}/32")

        if not obj:
            matches = netbox.ipam.ip_addresses.filter(address=ip_str)
            obj = _first_or_none(matches)

        if obj:
            updates = {"custom_fields": {}}
            cf = obj.custom_fields or {}

            if cf.get("reachability") != status:
                updates["custom_fields"]["reachability"] = status

            updates["custom_fields"]["last_scan"] = now
            if pinged:
                updates["custom_fields"]["last_online"] = now

            if mac and cf.get("mac_address") != mac:
                updates["custom_fields"]["mac_address"] = mac

            if dns and getattr(obj, "dns_name", None) != dns:
                updates["dns_name"] = dns

            changed = bool(updates["custom_fields"]) or ("dns_name" in updates)
            if changed:
                obj.update(updates)
                logger.info(f"Updated {ip_str}: {updates}")

        else:
            if pinged:
                payload = {
                    "address": f"{ip_str}/32",
                    "custom_fields": {
                        "reachability": "Online",
                        "last_scan": now,
                        "last_online": now,
                        "mac_address": mac or "",
                    },
                }
                if dns:
                    payload["dns_name"] = dns

                netbox.ipam.ip_addresses.create(payload)
                logger.info(f"Created IP {ip_str}/32")

    except Exception as e:
        log_error(f"Error scanning {ip_str}: {e}")


def scan_prefix(prefix_str: str) -> None:
    """
    Scan all usable hosts in a prefix (each as /32).
    """
    try:
        net = ipaddress.ip_network(prefix_str, strict=False)
    except ValueError as e:
        log_error(f"Invalid prefix {prefix_str}: {e}")
        return

    max_workers = _MAX_IP_WORKERS
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        it = (str(ip) for ip in net.hosts())
        futures = {pool.submit(scan_ip, ip, net.prefixlen): ip for _, ip in zip(range(max_workers), it)}
        for ip in it:
            done, futures = next(as_completed(futures)), futures
            futures.pop(done, None)
            futures[pool.submit(scan_ip, ip, net.prefixlen)] = ip
        for _ in as_completed(futures):
            pass

    logger.info(f"Prefix scan complete: {prefix_str}")

# -----------------------------------------------------------------------------
# Auto mode: find all scan-enabled prefixes via CF and scan them
# -----------------------------------------------------------------------------
def fetch_enabled_prefixes() -> list:
    """
    Return a list of prefix strings (e.g. '10.0.0.0/24') where custom field
    `scan_enabled` is true.

    NetBox allows filtering on custom fields with `cf_<key>=<value>`.
    Some versions/clients are picky about true/false (bool vs string), so we try both.
    """
    try:
        records = list(netbox.ipam.prefixes.filter(cf_scan_enabled=True))
        if records:
            return [str(p.prefix) for p in records]
    except Exception as e:
        log_error(f"Error filtering prefixes (bool True): {e}")

    try:
        records = list(netbox.ipam.prefixes.filter(cf_scan_enabled="true"))
        if records:
            return [str(p.prefix) for p in records]
    except Exception as e:
        log_error(f"Error filtering prefixes (string 'true'): {e}")

    return []


def run_auto_scan() -> None:
    """
    Find all scan-enabled prefixes (cf_scan_enabled=true) and scan them sequentially.
    (Each prefix itself is scanned in parallel across hosts.)
    """
    prefixes = fetch_enabled_prefixes()
    if not prefixes:
        logger.info("No scan-enabled prefixes found (cf_scan_enabled).")
        return

    logger.info(f"Auto-scan: found {len(prefixes)} enabled prefixes")
    for p in prefixes:
        logger.info(f"Auto-scan: scanning {p}")
        scan_prefix(p)

    logger.info("Auto-scan complete.")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def _parse_args():
    parser = argparse.ArgumentParser(description="NetBox Scanner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ip", help="Scan a single IP (e.g. 10.0.0.5)")
    group.add_argument("--prefix", help="Scan a prefix (e.g. 10.0.0.0/24)")
    group.add_argument("--auto", action="store_true", help="Scan all prefixes with cf scan_enabled=true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.ip:
        scan_ip(args.ip, 32)
    elif args.prefix:
        scan_prefix(args.prefix)
    elif args.auto:
        run_auto_scan()
