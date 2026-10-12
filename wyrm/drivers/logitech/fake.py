"""A simulated HID++ 2.0 mouse, alone or behind a receiver, for tests and `python -m wyrm --demo`.

It answers like a real device (feature table, errors, on-board mode) and fails loudly if Wyrm
sends anything that isn't on the allow-list.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .hidpp import (ADJUSTABLE_DPI, ALLOWED, BATTERY_STATUS, DEVICE_NAME, FEATURE_SET, LONG_LEN, ONBOARD,
                    ONBOARD_PROFILES, REPORT_LONG, REPORT_RATE, REPORT_SHORT, ROOT, UNIFIED_BATTERY)


@dataclass
class FakeHidppMouse:
    name: str = "Demo Mouse"
    kind: int = 3                                   # mouse
    features: list[int] = field(default_factory=lambda: [
        ROOT, FEATURE_SET, DEVICE_NAME, UNIFIED_BATTERY, ADJUSTABLE_DPI, REPORT_RATE, ONBOARD_PROFILES])
    battery: int = 80
    charging: int = 0
    dpi: int = 1600
    dpi_list: list[int] = field(default_factory=lambda: [100, 0xE000 + 50, 25600])   # 100-25600, steps of 50
    rate_mask: int = 0b10001011                     # 1, 2, 4 and 8 ms
    rate_ms: int = 1
    onboard_mode: int = 2                           # 1 on-board, 2 host
    asleep: bool = False
    calls: list = field(default_factory=list)      # (feature, function, params) Wyrm sent

    def dpi_ok(self, v: int) -> bool:
        lo, hi, step = self.dpi_list[0], self.dpi_list[-1], self.dpi_list[1] - 0xE000
        return lo <= v <= hi and (v - lo) % step == 0


class FakeHidppTransport:
    def __init__(self, mice: dict[int, FakeHidppMouse], receiver: bool = False):
        self.mice, self.receiver = mice, receiver
        self.lock = threading.RLock()
        self.closed = False
        self._out: list[bytes] = []

    def write(self, data: bytes) -> None:
        assert len(data) == LONG_LEN and data[0] == REPORT_LONG
        idx, fi, fsw, params = data[1], data[2], data[3], bytes(data[4:])
        m = self.mice.get(idx)
        if m is None or m.asleep:
            if self.receiver:   # HID++ 1.0: 0x08 unknown device, 0x09 not reachable
                self._out.append(bytes([REPORT_SHORT, idx, 0x8F, fi, fsw, 0x09 if m else 0x08, 0]))
            return
        if fi >= len(m.features):
            return self._reply(idx, fi, fsw, 6)
        feature, fn = m.features[fi], fsw >> 4
        assert fn in ALLOWED.get(feature, ()), f"Wyrm sent feature {feature:#06x} function {fn} (not allowed)"
        m.calls.append((feature, fn, params))
        self._reply(idx, fi, fsw, self._answer(m, feature, fn, params))

    def _reply(self, idx: int, fi: int, fsw: int, ans) -> None:
        if isinstance(ans, int):
            self._out.append(bytes([REPORT_LONG, idx, 0xFF, fi, fsw, ans]).ljust(LONG_LEN, b"\0"))
        else:
            self._out.append(bytes([REPORT_LONG, idx, fi, fsw]) + bytes(ans).ljust(16, b"\0")[:16])

    @staticmethod
    def _answer(m: FakeHidppMouse, feature: int, fn: int, p: bytes):
        if feature == ROOT:
            if fn == 0:
                fid = p[0] << 8 | p[1]
                return [m.features.index(fid) if fid in m.features else 0, 0, 0]
            return [4, 2, p[2]]                             # protocol 4.2, echo the ping byte
        if feature == FEATURE_SET:
            return [len(m.features) - 1] if fn == 0 else [m.features[p[0]] >> 8, m.features[p[0]] & 0xFF]
        if feature == DEVICE_NAME:
            name = m.name.encode()
            return [len(name)] if fn == 0 else (name[p[0]:p[0] + 16] if fn == 1 else [m.kind])
        if feature == UNIFIED_BATTERY:
            return [0x0F, 0] if fn == 0 else [m.battery, 4, m.charging, 0]
        if feature == BATTERY_STATUS:
            return [m.battery, 0, m.charging]
        if feature == ADJUSTABLE_DPI:
            if fn == 0:
                return [1]
            if fn == 1:
                return [0] + [b for v in m.dpi_list for b in v.to_bytes(2, "big")]
            if fn == 2:
                return [0, m.dpi >> 8, m.dpi & 0xFF, 800 >> 8, 800 & 0xFF]
            v = p[1] << 8 | p[2]
            if not m.dpi_ok(v):
                return 3
            if m.onboard_mode != ONBOARD:               # on-board profiles own the DPI
                m.dpi = v
            return [0, p[1], p[2]]
        if feature == REPORT_RATE:
            if fn == 0:
                return [m.rate_mask]
            if fn == 1:
                return [m.rate_ms]
            if not p[0] or not m.rate_mask >> (p[0] - 1) & 1:
                return 2
            if m.onboard_mode != ONBOARD:
                m.rate_ms = p[0]
            return []
        if feature == ONBOARD_PROFILES:
            if fn == 1:
                m.onboard_mode = p[0]
                return []
            return [m.onboard_mode]
        return 7

    def read(self, timeout_s: float) -> bytes | None:
        return self._out.pop(0) if self._out else None

    def close(self) -> None:
        self.closed = True
