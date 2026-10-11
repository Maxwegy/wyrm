"""Raw mouse input from every mouse, tagged with the device it came from.

Windows keeps one Raw Input registration per usage per process, so everything that wants raw
mouse reports (the "In use" badge, the polling-rate test) shares this hub. Registering twice, or
one user removing the registration, would silently break the other.
"""
from __future__ import annotations

import ctypes
import re
import time
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_INPUT = 0x00FF
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
RID_HEADER = 0x10000005
RIDI_DEVICENAME = 0x20000007


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                   ctypes.POINTER(wintypes.UINT), wintypes.UINT]
user32.GetRawInputDeviceInfoW.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                          ctypes.POINTER(wintypes.UINT)]
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]

_USB = re.compile(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", re.I)
_BT = re.compile(r"VID&(?:0002|02)([0-9A-F]{4})_PID&([0-9A-F]{4})", re.I)   # Bluetooth HID paths


def parse_device_path(path: str) -> tuple[int, int] | None:
    """(vid, pid) from a device interface path, e.g. \\\\?\\HID#VID_258A&PID_002F&MI_00#..."""
    m = _USB.search(path) or _BT.search(path)
    return (int(m.group(1), 16), int(m.group(2), 16)) if m else None


def device_name(h) -> str:
    size = wintypes.UINT(0)
    user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, None, ctypes.byref(size))
    buf = ctypes.create_unicode_buffer(size.value + 1)
    user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, buf, ctypes.byref(size))
    return buf.value


class _Sink(QWidget):
    def __init__(self, hub: "RawMouse"):
        super().__init__()
        self.hub = hub

    def nativeEvent(self, event_type, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_INPUT:
                self.hub._on_input(msg.lParam)
        except Exception:
            pass
        return False, 0


class RawMouse(QObject):
    activity = Signal(int, int)          # vid, pid of a mouse that moved; at most every THROTTLE_S per mouse
    report = Signal(int, float)          # device handle, perf_counter time; only while "rate" is acquired
    THROTTLE_S = 0.25

    def __init__(self):
        super().__init__()
        self._sink: _Sink | None = None
        self._users: set[str] = set()
        self._ids: dict[int, tuple[int, int] | None] = {}
        self._last: dict[int, float] = {}

    def acquire(self, who: str) -> None:
        if not self._users:
            self._register(True)
        self._users.add(who)

    def release(self, who: str) -> None:
        self._users.discard(who)
        if not self._users:
            self._register(False)

    def _register(self, on: bool) -> None:
        if self._sink is None:
            self._sink = _Sink(self)
        hwnd = wintypes.HWND(int(self._sink.winId())) if on else None
        rid = RAWINPUTDEVICE(1, 2, RIDEV_INPUTSINK if on else RIDEV_REMOVE, hwnd)
        user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))

    def ids(self, h: int) -> tuple[int, int] | None:
        if h not in self._ids:
            self._ids[h] = parse_device_path(device_name(h)) if h else None
        return self._ids[h]

    def _on_input(self, lparam) -> None:
        hdr = RAWINPUTHEADER()
        size = wintypes.UINT(ctypes.sizeof(hdr))
        if user32.GetRawInputData(lparam, RID_HEADER, ctypes.byref(hdr), ctypes.byref(size),
                                  ctypes.sizeof(RAWINPUTHEADER)) == 0xFFFFFFFF:
            return
        h, now = int(hdr.hDevice or 0), time.perf_counter()
        if "rate" in self._users:
            self.report.emit(h, now)
        if "activity" in self._users and now - self._last.get(h, 0.0) >= self.THROTTLE_S:
            self._last[h] = now
            ids = self.ids(h)
            if ids:
                self.activity.emit(*ids)


_hub: RawMouse | None = None


def raw_mouse() -> RawMouse:
    global _hub
    if _hub is None:
        _hub = RawMouse()
    return _hub
