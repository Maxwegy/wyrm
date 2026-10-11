"""HID++ 2.0 over hidapi: just enough to read a Logitech mouse and set its DPI and polling rate.

A request is a long report (0x11, 20 bytes): device index, feature index, function << 4 | software
id, then parameters. The answer comes back the same way. Errors come back with feature index 0xFF
(HID++ 2.0), or from a receiver as a short 0x8F report (HID++ 1.0). Wyrm only calls the features and
functions in ALLOWED, so firmware-update and reset features can't be reached.
"""
from __future__ import annotations

import threading
import time

import hid

REPORT_SHORT, REPORT_LONG = 0x10, 0x11
LONG_LEN = 20
SW_ID = 0x0B
TIMEOUT_S = 0.3
DIRECT = 0xFF             # device index of a mouse plugged in by cable, USB or Bluetooth

ROOT, FEATURE_SET, DEVICE_NAME = 0x0000, 0x0001, 0x0005
BATTERY_STATUS, UNIFIED_BATTERY = 0x1000, 0x1004
ADJUSTABLE_DPI, REPORT_RATE, ONBOARD_PROFILES = 0x2201, 0x8060, 0x8100
ONBOARD, HOST = 1, 2      # 0x8100 modes

ALLOWED = {
    ROOT: {0, 1},                    # get feature index, protocol version
    FEATURE_SET: {0, 1},
    DEVICE_NAME: {0, 1, 2},          # name length, name chunk, device type
    BATTERY_STATUS: {0},
    UNIFIED_BATTERY: {0, 1},
    ADJUSTABLE_DPI: {0, 1, 2, 3},    # 3 = set DPI
    REPORT_RATE: {0, 1, 2},          # 2 = set report rate
    ONBOARD_PROFILES: {1, 2},        # 1 = set mode (onboard / host), 2 = get mode
}
ERRORS = {1: "unknown error", 2: "invalid argument", 3: "out of range", 4: "hardware error",
          5: "internal error", 6: "invalid feature index", 7: "invalid function", 8: "busy", 9: "unsupported"}


class HidppError(RuntimeError):
    def __init__(self, code: int, what: str = ""):
        text = ERRORS.get(code, f"error {code}")
        super().__init__(f"{what}: {text}" if what else text)
        self.code = code


class NoAnswer(RuntimeError):
    """Nothing answered in time: the mouse is asleep, or not there."""


class HidppTransport:
    """The HID++ collections of one USB device: long for requests, short (when present) for the
    HID++ 1.0 errors a receiver sends about its mice."""

    def __init__(self, long_path: bytes, short_path: bytes | None = None):
        self.lock = threading.RLock()
        self.long = self._open(long_path)
        self.short = None
        if short_path:
            try:
                self.short = self._open(short_path)
            except OSError:
                pass

    @staticmethod
    def _open(path: bytes):
        d = hid.device()
        d.open_path(path)
        return d

    def write(self, data: bytes) -> None:
        if len(data) != LONG_LEN or data[0] != REPORT_LONG:
            raise ValueError("HID++ requests are 20-byte long reports")
        if self.long.write(data) < 0:
            raise OSError("HID++ write failed")

    def read(self, timeout_s: float) -> bytes | None:
        devs = [d for d in (self.long, self.short) if d is not None]
        end = time.monotonic() + timeout_s
        while (left := end - time.monotonic()) > 0:
            for d in devs:
                ms = max(1, int(left * 1000))
                r = d.read(64, ms if len(devs) == 1 else min(ms, 10))
                if r:
                    return bytes(r)
        return None

    def close(self) -> None:
        for d in (self.long, self.short):
            if d is not None:
                try:
                    d.close()
                except Exception:
                    pass


class Hidpp:
    """A HID++ 2.0 conversation with one device index behind a transport."""

    def __init__(self, t, index: int):
        self.t, self.index = t, index
        self._features: dict[int, int | None] = {ROOT: 0}

    def _request(self, feature_index: int, function: int, params=(), timeout: float = TIMEOUT_S) -> bytes:
        fsw = (function << 4) | SW_ID
        msg = bytes([REPORT_LONG, self.index, feature_index, fsw, *params]).ljust(LONG_LEN, b"\0")
        with self.t.lock:
            self.t.write(msg)
            end = time.monotonic() + timeout
            while (left := end - time.monotonic()) > 0:
                r = self.t.read(left)
                if r is None:
                    break
                if len(r) < 7 or r[1] != self.index:
                    continue
                if r[0] == REPORT_SHORT and r[2] == 0x8F and r[3] == feature_index and r[4] == fsw:
                    raise HidppError(r[5], "receiver")
                if r[2] == 0xFF and r[3] == feature_index and r[4] == fsw:
                    raise HidppError(r[5])
                if r[2] == feature_index and r[3] == fsw:
                    return bytes(r[4:])
        raise NoAnswer(f"no answer from device {self.index:#04x}")

    def ping(self) -> tuple[int, int] | None:
        """HID++ protocol version, or None when nothing at this index speaks HID++ 2.0."""
        try:
            r = self._request(0, 1, (0, 0, 0x5A))
        except (HidppError, NoAnswer):
            return None
        return r[0], r[1]

    def feature_index(self, feature: int) -> int | None:
        if feature not in self._features:
            r = self._request(0, 0, (feature >> 8, feature & 0xFF))
            self._features[feature] = r[0] or None
        return self._features[feature]

    def has(self, feature: int) -> bool:
        try:
            return self.feature_index(feature) is not None
        except HidppError:
            return False

    def call(self, feature: int, function: int, *params: int) -> bytes:
        if function not in ALLOWED.get(feature, ()):
            raise PermissionError(f"HID++ feature {feature:#06x} function {function} is not on Wyrm's allow-list")
        idx = self.feature_index(feature)
        if idx is None:
            raise HidppError(6, f"feature {feature:#06x}")
        return self._request(idx, function, params)


# --- feature helpers -----------------------------------------------------------------
def read_name(h: Hidpp) -> str:
    count = h.call(DEVICE_NAME, 0)[0]
    out = bytearray()
    while len(out) < count:
        chunk = h.call(DEVICE_NAME, 1, len(out))[:count - len(out)]
        if not chunk.strip(b"\0"):
            break
        out += chunk
    return out.split(b"\0", 1)[0].decode("utf-8", "replace").strip()


def read_battery(h: Hidpp, feature: int) -> tuple[int | None, bool, bool]:
    """(percent, charging, full)."""
    if feature == UNIFIED_BATTERY:
        r = h.call(UNIFIED_BATTERY, 1)
        return r[0], r[2] in (1, 2), r[2] == 3
    r = h.call(BATTERY_STATUS, 0)
    return r[0] or None, r[2] in (1, 2, 4), r[2] == 3


def parse_dpi_list(params: bytes) -> tuple[list[int], int]:
    """(DPI values, step) from a 0x2201 sensor DPI list. Big-endian values after the sensor byte, ending
    at 0. A value of 0xE000 or more is a step marker: the range runs from the value before it to the
    value after it in steps of (marker - 0xE000)."""
    values, step = [], 0
    for i in range(1, len(params) - 1, 2):
        v = params[i] << 8 | params[i + 1]
        if v == 0:
            break
        if v >= 0xE000:
            step = v - 0xE000
        else:
            values.append(v)
    return values, step


def rates_from_mask(mask: int) -> list[int]:
    """0x8060 report-rate list: bit n set means a report every n + 1 ms."""
    return sorted({1000 // (n + 1) for n in range(8) if mask >> n & 1})
