"""Locate the vendor HID collections of a SinoWealth wireless mouse (receiver or cable).

The SinoWealth receiver exposes several 0xFF00 collections on interface 1.
Commands (report 5) are answered on one collection and blocks (report 8) on
another, so both are found by probing rather than by a fixed COLxx index.
"""
from __future__ import annotations

from dataclasses import dataclass

import hid

VID = 0x258A
PID_CABLE = 0x002E
PID_RECEIVER = 0x002F
EXPECTED_FW = "2911"  # Cfg.ini PSD=32,39,31,31


@dataclass(frozen=True)
class DevicePaths:
    pid: int
    cmd_path: bytes      # answers report 5
    block_path: bytes    # answers report 8

    @property
    def wireless(self) -> bool:
        return self.pid == PID_RECEIVER


def vendor_paths(entries: list[dict], pid: int) -> list[bytes]:
    return [d["path"] for d in entries
            if d["vendor_id"] == VID and d["product_id"] == pid
            and d["interface_number"] == 1 and d["usage_page"] == 0xFF00 and d["usage"] == 0x01]


def _open(path: bytes):
    dev = hid.device()
    dev.open_path(path)
    return dev


def _identify(path: bytes) -> bool:
    try:
        dev = _open(path)
    except OSError:
        return False
    try:
        dev.send_feature_report(bytes([5, 0x01, 0, 0, 0, 0, 0, 0]))
        r = bytes(dev.get_feature_report(5, 8))
        return len(r) > 1 and r[1] == 0x01
    except OSError:
        return False
    finally:
        dev.close()


def _answers_block(cmd_dev, path: bytes, read_cmd: int) -> bool:
    try:
        dev = _open(path)
    except OSError:
        return False
    try:
        cmd_dev.send_feature_report(bytes([5, read_cmd, 0, 0, 0, 0, 0, 0]))
        r = bytes(dev.get_feature_report(8, 520))
        return len(r) > 2 and r[1] == read_cmd
    except OSError:
        return False
    finally:
        dev.close()


def probe(pid: int, cands: list[bytes]) -> DevicePaths | None:
    """Find the command collection (it answers identify), then the one that returns blocks."""
    cmd_path = next((p for p in cands if _identify(p)), None)
    if cmd_path is None:
        return None
    read_cmd = 0x21 if pid == PID_RECEIVER else 0x11
    cmd_dev = _open(cmd_path)
    try:
        block_path = next((p for p in cands if p != cmd_path
                           and _answers_block(cmd_dev, p, read_cmd)), None)
    finally:
        cmd_dev.close()
    return DevicePaths(pid, cmd_path, block_path) if block_path else None


def find_device(entries: list[dict] | None = None) -> DevicePaths | None:
    """Cable first when both are plugged in."""
    entries = hid.enumerate(VID) if entries is None else entries
    for pid in (PID_CABLE, PID_RECEIVER):
        paths = probe(pid, vendor_paths(entries, pid))
        if paths:
            return paths
    return None
