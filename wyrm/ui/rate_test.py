"""Measure a mouse's real report rate with Windows Raw Input."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout

from ..core.rawinput import raw_mouse
from .widgets import label

RATES = [125, 250, 500, 1000, 2000, 4000, 8000]


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


class RateTestDialog(QDialog):
    DURATION = 4.0

    def __init__(self, expected_hz: int | None, vidpid: tuple[int, int] | None = None, name: str = "mouse",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Polling rate test")
        self.setMinimumWidth(460)
        self.expected = expected_hz
        self.vidpid = vidpid
        self.result_hz: int | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(label(f"Move the {name} in quick circles", "PageTitle"))
        lay.addWidget(label("Wyrm counts the reports it sends for a few seconds. Nothing is written to the mouse.",
                            "Muted", wrap=True))
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
        self.raw = raw_mouse()
        self.raw.report.connect(self._on_report)
        self.stamps: dict[int, list[float]] = {}
        self.running = False
        self.timer = QTimer(self, interval=100)
        self.timer.timeout.connect(self._tick)
        QTimer.singleShot(150, self.start)

    def start(self):
        self.stamps.clear()
        self.t0 = None
        self.raw.acquire("rate")
        self.running = True
        self.bar.setValue(0)
        self.msg.setText("Waiting for movement…")
        self.again.setEnabled(False)
        self.timer.start()

    def _stop(self):
        self.timer.stop()
        if self.running:
            self.running = False
            self.raw.release("rate")
        self.again.setEnabled(True)

    def _on_report(self, h: int, now: float):
        if not self.running or (self.vidpid and self.raw.ids(h) != self.vidpid):
            return
        if self.t0 is None:
            self.t0 = now
        self.stamps.setdefault(h, []).append(now)

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
        self._stop()
        super().closeEvent(e)

    def done(self, r):
        self._stop()
        if self.raw is not None:
            self.raw.report.disconnect(self._on_report)
            self.raw = None
        super().done(r)
