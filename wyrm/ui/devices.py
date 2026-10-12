"""Mouse widgets: a card per mouse, the sidebar list, the header picker, the "follows Default" banner."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from ..drivers.base import SUPPORT_LABELS, DeviceInfo
from .theme import PAL, svg_icon, svg_pixmap
from .widgets import BatteryRing, button, chip, label

CONNECTION = {"receiver": "2.4 GHz", "cable": "Cable", "usb": "USB", "bluetooth": "Bluetooth"}
SUPPORT_CHIP = {"full": "ChipOk", "basic": "Chip", "detected": "ChipWarn"}
DRIVER_LABELS = {"sinowealth": "SinoWealth protocol", "logitech": "Logitech HID++"}
ADD_A_MOUSE = "https://github.com/Maxwegy/wyrm/blob/main/docs/adding-a-device.md"


def battery_text(st: dict) -> str:
    if st.get("charging"):
        return "charging"
    return f"{st['battery']}%" if st.get("battery") is not None else ""


def _restyle(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


class DeviceCard(QFrame):
    """One mouse: name, connection, support level, battery. Click a configurable one to edit it."""
    picked = Signal(str)   # model key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DeviceCard")
        self.info: DeviceInfo | None = None
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(28)
        sh.setOffset(0, 6)
        sh.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(sh)
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 18, 16, 18)
        row.setSpacing(16)
        self.icon = QLabel()
        self.icon.setFixedSize(44, 44)
        row.addWidget(self.icon, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(6)
        self.name = label("", "DeviceName", wrap=True)
        col.addWidget(self.name)
        self.sub = label("", "Dim")
        col.addWidget(self.sub)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        col.addLayout(self.chips)
        self.note = label("", "Muted", wrap=True)
        col.addWidget(self.note)
        self.help = button("How to add this mouse", "Ghost", "link")
        self.help.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ADD_A_MOUSE)))
        col.addWidget(self.help, 0, Qt.AlignLeft)
        col.addStretch(1)
        row.addLayout(col, 1)
        self.battery = BatteryRing()
        self.battery.setFixedSize(QSize(108, 108))
        row.addWidget(self.battery, 0, Qt.AlignTop)

    def set(self, info: DeviceInfo, st: dict, *, connected: bool = True, selected: bool = False,
            in_use: bool = False, conflict: str = "", last_seen: str = ""):
        self.info = info
        configurable = info.caps.configurable
        awake = connected and st.get("link", True)
        self.icon.setPixmap(svg_pixmap("mouse", PAL.accent if awake else PAL.dim, 44))
        self.name.setText(info.name)
        bits = [b for b in (info.vendor if not info.name.startswith(info.vendor) else "",
                            DRIVER_LABELS.get(info.driver, ""), info.caps.sensor) if b]
        self.sub.setText(" · ".join(bits))
        while self.chips.count():
            it = self.chips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not connected:
            self.chips.addWidget(chip("Not connected"))
        else:
            self.chips.addWidget(chip(CONNECTION.get(info.connection, info.connection), "ChipAccent"))
            if not st.get("link", True):
                self.chips.addWidget(chip("Asleep", "ChipWarn"))
            elif info.connection in ("receiver", "bluetooth"):
                self.chips.addWidget(chip("Awake"))
            if in_use:
                self.chips.addWidget(chip("● In use", "ChipAccent"))
        if info.fw:
            self.chips.addWidget(chip(f"fw {info.fw}"))
        self.chips.addWidget(chip(SUPPORT_LABELS.get(info.support, info.support), SUPPORT_CHIP.get(info.support, "Chip")))
        if info.demo:
            self.chips.addWidget(chip("Demo", "ChipWarn"))
        self.chips.addStretch(1)

        note = ""
        if not connected:
            note = f"Last seen {last_seen}. Its settings stay in your profiles." if last_seen else ""
        elif st.get("error"):
            note = st["error"]
        elif st.get("pending"):
            note = "Changes are waiting. Move the mouse to wake it and they'll be written."
        elif not st.get("link", True):
            note = "The mouse is asleep. Move it to wake it up."
        elif conflict:
            note = (f"{conflict} is running and may change this mouse's settings too. "
                    f"Quit it to let Wyrm manage the {info.short_name}.")
        elif st.get("note"):
            note = st["note"]
        elif not configurable:
            note = "Wyrm can see this mouse but can't configure it yet."
        self.note.setText(note)
        self.note.setVisible(bool(note))
        self.help.setVisible(not configurable)
        self.battery.setVisible(info.caps.battery and connected)
        self.battery.set(st.get("battery"), bool(st.get("charging")))
        self.setCursor(Qt.PointingHandCursor if configurable else Qt.ArrowCursor)
        self.setToolTip("Click to edit this mouse's settings" if configurable else "")
        for prop, val in (("selected", selected and configurable), ("inuse", in_use)):
            if self.property(prop) != val:
                self.setProperty(prop, val)
                _restyle(self)

    def mousePressEvent(self, e):
        if self.info and self.info.caps.configurable:
            self.picked.emit(self.info.key)
        super().mousePressEvent(e)


class DeviceList(QWidget):
    """The sidebar's mouse list: a status dot, the name and the battery."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(2)
        self._sig = None
        for s in (ctx.devices_changed, ctx.current_changed, ctx.in_use_changed):
            s.connect(self.refresh)
        ctx.status_changed.connect(lambda _: self.refresh())
        self.refresh()

    def refresh(self):
        ctx = self.ctx
        cur = ctx.current()
        rows = []
        for i in ctx.mice():
            st = ctx.status_of(i)
            dot = PAL.accent2 if i.uid in ctx.in_use else (PAL.ok if st.get("link", True) else PAL.warn)
            rows.append((i.uid, i.key, i.short_name, battery_text(st), dot, i.caps.configurable,
                         bool(cur and cur.key == i.key), i.name))
        if rows == self._sig:
            return
        self._sig = rows
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not rows:
            self.lay.addWidget(label("No mouse found", "Dim"))
            return
        for _uid, key, short, bat, dot, editable, selected, full in rows:
            b = QPushButton(f" {short}" + (f"   {bat}" if bat else ""))
            b.setObjectName("DevRow")
            b.setIcon(svg_icon("record", dot, 10))
            b.setIconSize(QSize(10, 10))
            b.setCheckable(True)
            b.setChecked(selected)
            b.setToolTip(full)
            if editable:
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, k=key: self.ctx.set_current(k))
            else:
                b.clicked.connect(lambda _=False, b=b: b.setChecked(False))
            self.lay.addWidget(b)


class DeviceCombo(QComboBox):
    """Header picker for the mouse being edited (plugged in or not)."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setMinimumWidth(200)
        self.activated.connect(lambda i: ctx.set_current(self.itemData(i)))
        for s in (ctx.devices_changed, ctx.current_changed):
            s.connect(self.refresh)
        self.refresh()

    def refresh(self):
        cur = self.ctx.current()
        self.blockSignals(True)
        self.clear()
        for i in self.ctx.editable_mice():
            here = self.ctx.connected(i)
            self.addItem(svg_icon("record", PAL.ok if here else PAL.dim, 10),
                         i.name + ("" if here else "  (not connected)"), i.key)
        if cur:
            self.setCurrentIndex(max(0, self.findData(cur.key)))
        self.blockSignals(False)


class InheritBanner(QFrame):
    """Where the settings on a page come from, with the matching way out."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Banner")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 10, 10)
        self.text = label("", wrap=True)
        row.addWidget(self.text, 1)
        self.btn = button("Follow the default profile", "Ghost")
        self.btn.clicked.connect(ctx.follow_default)
        row.addWidget(self.btn)
        self.hide()

    def refresh(self):
        p, dev, d = self.ctx.editing(), self.ctx.current(), self.ctx.manager.default()
        s, src = self.ctx.device_settings()
        text, own = "", False
        if p and dev and s is not None and d:
            if src == "own" and p.id != d.id:
                text, own = f"{p.name} has its own settings for the {dev.short_name}.", True
            elif src == "default" and p.id != d.id:
                text = (f"{p.name} follows the default profile, {d.name}, for the {dev.short_name}. "
                        f"Change anything here to give {p.name} its own settings.")
            elif src == "mouse":
                text = (f"Showing what's on the {dev.short_name} now. Change anything here and "
                        f"{p.name} takes it over.")
        self.text.setText(text)
        self.btn.setVisible(own)
        self.setVisible(bool(text))
