"""Tray icon, on-screen profile toast, and global profile hotkeys."""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRect, QSequentialAnimationGroup, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from ..core import winapi
from ..core.keys import HID_TO_VK, HOTKEY_NEXT_PROFILE, HOTKEY_PREV_PROFILE
from .theme import PAL, logo_icon, logo_svg, qc, render_svg

log = logging.getLogger(__name__)


class HotkeyWindow(QWidget):
    """Owns F24 / F23 system-wide so mouse buttons can switch profiles."""
    next = Signal()
    prev = Signal()

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_DontShowOnScreen)
        self.hwnd = int(self.winId())
        self.ok = {}
        for ident, usage in ((1, HOTKEY_NEXT_PROFILE), (2, HOTKEY_PREV_PROFILE)):
            self.ok[ident] = winapi.register_hotkey(self.hwnd, ident, HID_TO_VK[usage])
            if not self.ok[ident]:
                log.warning("could not register hotkey %d (another app owns it?)", ident)

    def nativeEvent(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == winapi.WM_HOTKEY:
            if msg.wParam == 1:
                self.next.emit()
            elif msg.wParam == 2:
                self.prev.emit()
            return True, 0
        return False, 0

    def unregister(self):
        for ident in (1, 2):
            winapi.unregister_hotkey(self.hwnd, ident)


class Osd(QWidget):
    """A small glass badge near the bottom of the screen when the profile changes."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(380, 92)
        self.name, self.sub, self.color = "", "", PAL.accent
        self.anim = QSequentialAnimationGroup(self)
        fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        fade_in.setDuration(160)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.addAnimation(fade_in)
        self.anim.addPause(1300)
        fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        fade_out.setDuration(420)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        self.anim.addAnimation(fade_out)
        self.anim.finished.connect(self.hide)

    def show_profile(self, name: str, color: str, sub: str):
        self.name, self.color, self.sub = name, color, sub
        scr = QGuiApplication.primaryScreen().availableGeometry()
        self.move(scr.center().x() - self.width() // 2, scr.bottom() - self.height() - 70)
        self.anim.stop()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.update()
        self.anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(4, 4, -4, -4)
        bg = QColor(PAL.surface)
        bg.setAlpha(238)
        p.setPen(QPen(qc(self.color, 200), 1.5))
        p.setBrush(bg)
        p.drawRoundedRect(r, 20, 20)
        p.drawPixmap(QRect(r.left() + 18, r.top() + 18, 48, 48), render_svg(logo_svg(), 48))
        p.setPen(Qt.NoPen)
        p.setBrush(qc(self.color))
        p.drawRoundedRect(QRect(r.left() + 78, r.top() + 22, 4, 40), 2, 2)
        f = self.font()
        f.setPointSize(16)
        f.setBold(True)
        p.setFont(f)
        p.setPen(qc(PAL.text))
        p.drawText(QRect(r.left() + 94, r.top() + 14, r.width() - 104, 34), Qt.AlignLeft | Qt.AlignVCenter,
                   self.name)
        f.setPointSize(9)
        f.setBold(False)
        p.setFont(f)
        p.setPen(qc(PAL.muted))
        p.drawText(QRect(r.left() + 94, r.top() + 46, r.width() - 104, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   self.sub)


class Tray(QSystemTrayIcon):
    def __init__(self, ctx, window):
        super().__init__(logo_icon(mono=True))
        self.ctx, self.window = ctx, window
        self.menu = QMenu()
        self.menu.aboutToHide.connect(lambda: QTimer.singleShot(0, self.rebuild))
        self.setContextMenu(self.menu)
        self._sig = None
        self.activated.connect(self._activated)
        ctx.manager.profiles_changed.connect(self.rebuild)
        ctx.manager.active_changed.connect(lambda *_: self.rebuild())
        ctx.status_changed.connect(lambda _: self._status())
        ctx.devices_changed.connect(self._status)
        ctx.config_changed.connect(self.rebuild)
        self._connected = None
        self.rebuild()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.window.show_and_raise()

    def _status(self):
        conn = bool(self.ctx.devices)
        if conn != self._connected:
            self._connected = conn
            self.setIcon(logo_icon(mono=not conn))
        self.rebuild()

    @staticmethod
    def _state(st: dict) -> str:
        if not st.get("link", True):
            return "asleep"
        bat = st.get("battery")
        return "charging" if st.get("charging") else (f"{bat}%" if bat is not None else "connected")

    def rebuild(self):
        m = self.ctx.manager
        active = m.active()
        mice = [(i.short_name, self._state(self.ctx.status_of(i))) for i in self.ctx.mice()]
        sig = (tuple(mice), active.id if active else None, tuple((p.id, p.name) for p in m.profiles()),
               self.ctx.store.config.auto_switch)
        if self.menu.isVisible() or sig == self._sig:
            return          # never rebuild an open menu; aboutToHide catches up
        self._sig = sig
        state = " · ".join(f"{n} {st}" for n, st in mice) if mice else "no mouse found"
        tip = f"Wyrm · {active.name if active else '—'} · {state}"
        self.setToolTip(tip if len(tip) < 128 else tip[:125] + "…")
        self.menu.clear()
        for line in ([f"{n}  ·  {st}" for n, st in mice] or ["No mouse found"]):
            head = self.menu.addAction(line)
            head.setEnabled(False)
        self.menu.addSeparator()
        grp = QActionGroup(self.menu)
        for p in m.profiles():
            a = QAction(p.name, self.menu, checkable=True)
            a.setChecked(bool(active and p.id == active.id))
            a.triggered.connect(lambda _=False, pid=p.id: m.switch(pid, "manual"))
            grp.addAction(a)
            self.menu.addAction(a)
        self.menu.addSeparator()
        auto = QAction("Auto-switch by app", self.menu, checkable=True)
        auto.setChecked(self.ctx.store.config.auto_switch)
        auto.toggled.connect(lambda v: (m.set_auto(v), self.ctx.config_changed.emit()))
        self.menu.addAction(auto)
        self.menu.addAction("Open Wyrm", self.window.show_and_raise)
        self.menu.addSeparator()
        self.menu.addAction("Quit", self.window.quit_app)


__all__ = ["HotkeyWindow", "Osd", "Tray", "QPoint", "QTimer", "ctypes"]
