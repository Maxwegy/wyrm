"""Measure the mouse's real report rate with Windows Raw Input."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget

from .widgets import label

user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_INPUT = 0x00FF
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
RID_HEADER = 0x10000005
RIDI_DEVICENAME = 0x20000007
RATES = [125, 250, 500, 1000]


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


def device_name(h) -> str:
    size = wintypes.UINT(0)
    user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, None, ctypes.byref(size))
    buf = ctypes.create_unicode_buffer(size.value + 1)
    user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, buf, ctypes.byref(size))
    return buf.value


def estimate_rate(stamps: list[float], gap: float = 0.05) -> float | None:
    """Reports per second while the mouse was actually moving."""
    if len(stamps) < 50:
        return None
    active, n = 0.0, 0
    for a, b in zip(stamps, stamps[1:]):
        if b - a < gap:
            active += b - a
            n += 1
    return n / active if active > 0 else None


def snap(rate: float | None) -> int | None:
    if not rate:
        return None
    best = min(RATES, key=lambda r: abs(r - rate))
    return best if abs(best - rate) / best < 0.2 else None


class _Sink(QWidget):
    report = Signal(object)

    def nativeEvent(self, event_type, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_INPUT:
                hdr = RAWINPUTHEADER()
                size = wintypes.UINT(ctypes.sizeof(hdr))
                if user32.GetRawInputData(msg.lParam, RID_HEADER, ctypes.byref(hdr), ctypes.byref(size),
                                          ctypes.sizeof(RAWINPUTHEADER)) != 0xFFFFFFFF:
                    self.report.emit(hdr.hDevice)
        except Exception:
            pass
        return False, 0


class RateTestDialog(QDialog):
    DURATION = 4.0

    def __init__(self, expected_hz: int | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Polling rate test")
        self.setMinimumWidth(460)
        self.expected = expected_hz
        self.result_hz: int | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(label("Move the mouse in quick circles", "PageTitle"))
        lay.addWidget(label("Wyrm counts the reports your M811 PRO sends for a few seconds. "
                            "Nothing is written to the mouse.", "Muted", wrap=True))
        self.big = label("— Hz", "Huge")
        self.big.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.big)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        lay.addWidget(self.bar)
        self.msg = label("", "Muted", wrap=True)
        lay.addWidget(self.msg)
        row = QHBoxLayout()
        row.addStretch(1)
        self.again = QPushButton("Run again")
        self.again.clicked.connect(self.start)
        self.close_btn = QPushButton("Done")
        self.close_btn.setObjectName("Primary")
        self.close_btn.clicked.connect(self.accept)
        row.addWidget(self.again)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        self.sink = _Sink()
        self.sink.report.connect(self._on_report)
        self.stamps: dict[int, list[float]] = {}
        self.names: dict[int, str] = {}
        self.timer = QTimer(self, interval=100)
        self.timer.timeout.connect(self._tick)
        QTimer.singleShot(150, self.start)

    def start(self):
        self.stamps.clear()
        self.t0 = None
        rid = RAWINPUTDEVICE(1, 2, RIDEV_INPUTSINK, wintypes.HWND(int(self.sink.winId())))
        user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
        self.bar.setValue(0)
        self.msg.setText("Waiting for movement…")
        self.again.setEnabled(False)
        self.timer.start()

    def _stop(self):
        self.timer.stop()
        rid = RAWINPUTDEVICE(1, 2, RIDEV_REMOVE, None)
        user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
        self.again.setEnabled(True)

    def _on_report(self, h):
        now = time.perf_counter()
        key = int(h or 0)
        if key not in self.names:
            self.names[key] = device_name(h) if h else ""
        if "VID_258A" not in self.names[key].upper():
            return
        if self.t0 is None:
            self.t0 = now
        self.stamps.setdefault(key, []).append(now)

    def _ours(self) -> list[float]:
        return max(self.stamps.values(), key=len) if self.stamps else []

    def _tick(self):
        if self.t0 is None:
            return
        el = time.perf_counter() - self.t0
        self.bar.setValue(int(min(100, el / self.DURATION * 100)))
        r = estimate_rate(self._ours())
        if r:
            self.big.setText(f"{r:,.0f} Hz")
        if el >= self.DURATION:
            self._stop()
            self._finish(r)

    def _finish(self, r):
        hz = snap(r)
        self.result_hz = hz
        if hz is None:
            self.msg.setText("Couldn't get a clean reading. Keep the mouse moving the whole time and try again.")
            return
        self.big.setText(f"{hz} Hz")
        if self.expected and hz == self.expected:
            self.msg.setText(f"Measured {r:,.0f} reports/s. That matches what Wyrm decoded from the mouse, "
                             "so polling-rate changes can be trusted on your unit.")
        elif self.expected:
            self.msg.setText(f"Measured {r:,.0f} reports/s, but Wyrm decoded {self.expected} Hz from the mouse. "
                             "Polling-rate writes stay off. Please report this so the map can be fixed.")
        else:
            self.msg.setText(f"Measured {r:,.0f} reports/s.")

    def matches(self) -> bool:
        return bool(self.expected and self.result_hz == self.expected)

    def closeEvent(self, e):
        if self.timer.isActive():
            self._stop()
        super().closeEvent(e)

    def done(self, r):
        if self.timer.isActive():
            self._stop()
        super().done(r)
