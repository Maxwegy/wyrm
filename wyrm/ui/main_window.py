from __future__ import annotations

import ctypes
import time

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..core.rawinput import raw_mouse
from ..drivers.base import DeviceInfo
from . import theme
from .context import AppContext
from .devices import DeviceCombo, DeviceList
from .pages.buttons import ButtonsPage
from .pages.dashboard import DashboardPage
from .pages.lighting import LightingPage
from .pages.macros import MacrosPage
from .pages.performance import PerformancePage
from .pages.profiles import ProfilesPage
from .pages.settings import SettingsPage
from .theme import PAL, logo_svg, render_svg, svg_icon
from .widgets import button, label

PAGES = [("home", DashboardPage), ("profiles", ProfilesPage), ("performance", PerformancePage),
         ("buttons", ButtonsPage), ("lighting", LightingPage), ("macros", MacrosPage), ("settings", SettingsPage)]


def dark_titlebar(hwnd: int) -> None:
    try:
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.eff)
        self.anim = QPropertyAnimation(self.eff, b"opacity", self)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self._fade)
        self.hide()

    def pop(self, text: str, kind: str = "info"):
        col = {"ok": PAL.ok, "warn": PAL.warn, "bad": PAL.bad}.get(kind, PAL.accent)
        self.setStyleSheet(f"background: {PAL.surface3}; border: 1px solid {col}; border-radius: 12px;"
                           f"padding: 10px 18px; font-weight: 600; color: {PAL.text};")
        self.setText(text)
        self.adjustSize()
        par = self.parentWidget()
        self.move(par.width() - self.width() - 24, par.height() - self.height() - 24)
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.setDuration(150)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.timer.start(2600 if kind != "bad" else 6000)

    def _fade(self):
        self.anim.stop()
        self.anim.setDuration(400)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()
        self.anim.finished.connect(self.hide, Qt.SingleShotConnection)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self._quitting = False
        self.setWindowTitle("Wyrm")
        self.setMinimumSize(1120, 760)
        self.resize(1280, 840)
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # --- sidebar ---------------------------------------------------------------
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(16, 22, 16, 18)
        sv.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        self.brand_logo = QLabel()
        self.brand_logo.setFixedSize(40, 40)
        brand.addWidget(self.brand_logo)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        bt.addWidget(label("WYRM", "Brand"))
        bt.addWidget(label("MOUSE PROFILES", "BrandSub"))
        brand.addLayout(bt)
        brand.addStretch(1)
        sv.addLayout(brand)
        sv.addSpacing(22)
        self.nav = QButtonGroup(self)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.stack = QStackedWidget()
        self.pages = {}
        for i, (key, cls) in enumerate(PAGES):
            page = cls(ctx)
            self.pages[key] = page
            self.stack.addWidget(page)
            b = QPushButton("  " + page.title)
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIconSize(QSize(18, 18))
            b.setProperty("icon_name", page.icon)
            self.nav.addButton(b, i)
            self.nav_buttons[key] = b
            sv.addWidget(b)
            if key == "macros":
                sv.addSpacing(8)
        self.nav.idClicked.connect(self._go_index)
        sv.addStretch(1)
        sv.addWidget(label("YOUR MICE", "SideHead"))
        self.device_list = DeviceList(ctx)
        sv.addWidget(self.device_list)
        sv.addSpacing(10)
        self.side_status = label("", "Dim", wrap=True)
        sv.addWidget(self.side_status)
        sv.addWidget(label(f"v{__version__} · offline", "Dim"))
        h.addWidget(side)

        # --- content ---------------------------------------------------------------
        content = QWidget()
        cv = QVBoxLayout(content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        header = QWidget()
        hh = QHBoxLayout(header)
        hh.setContentsMargins(28, 24, 28, 12)
        tt = QVBoxLayout()
        tt.setSpacing(2)
        self.title = label("", "PageTitle")
        self.sub = label("", "PageSub")
        tt.addWidget(self.title)
        tt.addWidget(self.sub)
        hh.addLayout(tt, 1)
        self.mouse_box = QWidget()
        mb = QHBoxLayout(self.mouse_box)
        mb.setContentsMargins(0, 0, 12, 0)
        mb.setSpacing(8)
        mb.addWidget(label("Mouse", "Dim"))
        self.mouse_combo = DeviceCombo(ctx)
        mb.addWidget(self.mouse_combo)
        hh.addWidget(self.mouse_box)
        self.edit_box = QWidget()
        eb = QHBoxLayout(self.edit_box)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(8)
        eb.addWidget(label("Editing", "Dim"))
        self.edit_combo = QComboBox()
        self.edit_combo.setMinimumWidth(180)
        self.edit_combo.activated.connect(self._pick_editing)
        eb.addWidget(self.edit_combo)
        self.activate_btn = button("Activate", "Primary", "bolt")
        self.activate_btn.clicked.connect(self._activate_editing)
        eb.addWidget(self.activate_btn)
        hh.addWidget(self.edit_box)
        self.save_state = label("", "Dim")
        self.save_state.setMinimumWidth(170)
        self.save_state.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hh.addWidget(self.save_state)
        cv.addWidget(header)
        cv.addWidget(self.stack, 1)
        h.addWidget(content, 1)
        self.toast = Toast(content)

        ctx.toast.connect(self.toast.pop)
        ctx.manager.profiles_changed.connect(self._fill_edit_combo)
        ctx.manager.active_changed.connect(lambda *_: self._fill_edit_combo())
        ctx.editing_changed.connect(lambda *_: self._fill_edit_combo())
        ctx.manager.write_blocked.connect(lambda msg: self.toast.pop(msg, "warn"))
        ctx.device.applied.connect(self._applied)
        ctx.device.apply_failed.connect(self._failed)
        ctx.status_changed.connect(lambda _: self._status())
        ctx.devices_changed.connect(self._status)
        ctx.devices_changed.connect(self._header)
        raw_mouse().activity.connect(ctx.on_activity)
        self._told: set[str] = set()
        self.apply_theme()
        self.go("home")
        self._status()

    # --- navigation --------------------------------------------------------------------
    def go(self, key: str):
        keys = [k for k, _ in PAGES]
        self._go_index(keys.index(key))

    def _go_index(self, i: int):
        self.nav.button(i).setChecked(True)
        self.stack.setCurrentIndex(i)
        page = self.stack.currentWidget()
        self.title.setText(page.title)
        self.sub.setText(page.subtitle)
        self._header()

    def _header(self):
        page = self.stack.currentWidget()
        self.edit_box.setVisible(page.edits_profile)
        self.mouse_box.setVisible(page.edits_device and bool(self.ctx.editable_mice()))
        self._fill_edit_combo()

    def _fill_edit_combo(self):
        m = self.ctx.manager
        cur = self.ctx.editing()
        self.edit_combo.blockSignals(True)
        self.edit_combo.clear()
        for p in m.profiles():
            suffix = "  (active)" if self.ctx.is_active(p) else ""
            self.edit_combo.addItem(svg_icon("record", p.accent, 12), p.name + suffix, p.id)
        if cur:
            self.edit_combo.setCurrentIndex(max(0, self.edit_combo.findData(cur.id)))
        self.edit_combo.blockSignals(False)
        self.activate_btn.setVisible(bool(cur) and not self.ctx.is_active(cur))

    def _pick_editing(self, i):
        self.ctx.set_editing(self.edit_combo.itemData(i))
        self._fill_edit_combo()

    def _activate_editing(self):
        p = self.ctx.editing()
        if p:
            self.ctx.manager.switch(p.id, "manual")

    # --- status ---------------------------------------------------------------------------
    def _name(self, uid: str) -> str:
        info = self.ctx.devices.get(uid)
        return info.short_name if info else "mouse"

    def _status(self, *_):
        mice = self.ctx.mice()
        sts = [self.ctx.status_of(i) for i in mice]
        asleep = [i for i, st in zip(mice, sts) if not st.get("link", True)]
        if not mice:
            txt, col = "● No mouse found", PAL.warn
        elif len(mice) == 1:
            bat = sts[0].get("battery")
            txt = ("● Asleep, move the mouse" if asleep else
                   "● Connected" + (f" · {bat}%" if bat is not None else ""))
            col = PAL.warn if asleep else PAL.ok
        else:
            txt = f"● {len(mice)} mice connected" + (f" · {len(asleep)} asleep" if asleep else "")
            col = PAL.ok
        self.side_status.setText(txt)
        self.side_status.setStyleSheet(f"color: {col};")
        if any(st.get("pending") for st in sts):
            self.save_state.setText("Waiting for the mouse…")

    def _applied(self, uid: str, pid: str, info: dict):
        name = self._name(uid)
        if info.get("restored") is not None:
            self.toast.pop(f"{name}: original settings restored" if info["restored"] else
                           f"{name}: the restore didn't stick", "ok" if info["restored"] else "bad")
            return
        if info.get("dry_run"):
            self.save_state.setText("Dry run · nothing written")
            return
        for msg in info.get("skipped", []):
            if msg not in self._told:
                self._told.add(msg)
                self.toast.pop(f"Not written: {msg}. See the mouse card on Home.", "warn")
        self.save_state.setText(f"✓ Saved to {name} {time.strftime('%H:%M:%S')}" if info.get("changed") else
                                f"✓ {name} is up to date")

    def _failed(self, uid: str, pid: str, msg: str):
        self.toast.pop(f"{self._name(uid)}: {msg}" if uid else msg, "bad")

    # --- theme / window -------------------------------------------------------------------
    def apply_theme(self):
        theme.set_accent(self.ctx.store.config.accent)
        QApplication.instance().setStyleSheet(theme.stylesheet())
        self.brand_logo.setPixmap(render_svg(logo_svg(), 40))
        for b in self.nav_buttons.values():
            b.setIcon(svg_icon(b.property("icon_name"), PAL.muted, 18))
        self.setWindowIcon(theme.logo_icon())
        for p in self.pages.values():
            p.update()
        self._fill_edit_combo()

    def showEvent(self, e):
        dark_titlebar(int(self.winId()))
        if not e.spontaneous():
            raw_mouse().acquire("activity")      # light up "In use" while the window is open
        super().showEvent(e)

    def hideEvent(self, e):
        if not e.spontaneous():
            raw_mouse().release("activity")
        super().hideEvent(e)

    def show_and_raise(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        if self._quitting:
            e.accept()
            return
        e.ignore()
        self.hide()
        if not getattr(self, "_told_tray", False):
            self._told_tray = True
            tray = getattr(self, "tray", None)
            if tray:
                tray.showMessage("Wyrm is still running", "Profiles and auto-switch keep working from the tray.",
                                 theme.logo_icon(), 3500)

    def quit_app(self):
        self._quitting = True
        self.close()
        QApplication.instance().quit()

    # --- first write -----------------------------------------------------------------------
    def confirm_first_write(self, info: DeviceInfo) -> bool:
        if self.ctx.demo or info.demo:
            return True
        self.show_and_raise()
        box = QMessageBox(self)
        box.setWindowTitle("Write to your mouse?")
        box.setIcon(QMessageBox.Question)
        box.setText(f"Wyrm is about to save your profile to the {info.name}.")
        box.setInformativeText(
            "Its current settings were saved first, so you can restore them any time from Settings. "
            "Wyrm only changes the settings it understands and checks every write.\n\n"
            "Allow Wyrm to write to this mouse?")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.button(QMessageBox.Yes).setText("Allow")
        box.button(QMessageBox.No).setText("Not now")
        return box.exec() == QMessageBox.Yes
