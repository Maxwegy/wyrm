"""Reusable themed widgets."""
from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF, QSize, Qt,
                            Property, Signal)
from PySide6.QtGui import QColor, QConicalGradient, QFont, QKeyEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QFrame,
                               QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..core.keys import HID_NAMES, MODIFIER_USAGES, MOD_NAMES, VK_TO_HID, key_name
from .theme import PAL, qc, svg_icon


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def chip(text: str, kind: str = "Chip") -> QLabel:
    lb = QLabel(text)
    lb.setObjectName(kind)
    lb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return lb


def button(text: str = "", kind: str | None = None, icon: str | None = None, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if icon:
        color = "#140b06" if kind == "Primary" else PAL.muted
        b.setIcon(svg_icon(icon, color, 18))
        b.setIconSize(QSize(16, 16))
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b


class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 18, 20, 18)
        self.body.setSpacing(12)
        if title or subtitle:
            head = QVBoxLayout()
            head.setSpacing(2)
            if title:
                head.addWidget(label(title, "CardTitle"))
            if subtitle:
                head.addWidget(label(subtitle, "Muted", wrap=True))
            self.body.addLayout(head)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(28)
        sh.setOffset(0, 6)
        sh.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(sh)

    def add(self, w):
        if isinstance(w, QWidget):
            self.body.addWidget(w)
        else:
            self.body.addLayout(w)
        return w


def hrow(*items, spacing: int = 10, stretch_last: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(0, 0, 0, 0)
    for it in items:
        if it is None:
            lay.addStretch(1)
        elif isinstance(it, QWidget):
            lay.addWidget(it)
        else:
            lay.addLayout(it)
    if stretch_last:
        lay.addStretch(1)
    return lay


class Toggle(QAbstractButton):
    """An animated on/off switch."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        return QSize(44, 24)

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get(self):
        return self._pos

    def _set(self, v):
        self._pos = v
        self.update()

    pos = Property(float, _get, _set)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 2, 42, 20)
        off, on = qc(PAL.surface3), qc(PAL.accent)
        c = QColor(int(off.red() + (on.red() - off.red()) * self._pos),
                   int(off.green() + (on.green() - off.green()) * self._pos),
                   int(off.blue() + (on.blue() - off.blue()) * self._pos))
        if not self.isEnabled():
            c = qc(PAL.surface2)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(r, 10, 10)
        x = 3 + self._pos * 20
        p.setBrush(qc(PAL.text if self.isEnabled() else PAL.dim))
        p.drawEllipse(QRectF(x, 4, 16, 16))


class ToggleRow(QWidget):
    """Title + description on the left, toggle on the right."""
    toggled = Signal(bool)

    def __init__(self, title: str, desc: str = "", checked: bool = False, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        txt = QVBoxLayout()
        txt.setSpacing(2)
        self.title = label(title)
        f = self.title.font()
        f.setWeight(QFont.DemiBold)
        self.title.setFont(f)
        txt.addWidget(self.title)
        if desc:
            self.desc = label(desc, "Muted", wrap=True)
            txt.addWidget(self.desc)
        lay.addLayout(txt, 1)
        self.toggle = Toggle(checked)
        self.toggle.toggled.connect(self.toggled)
        lay.addWidget(self.toggle, 0, Qt.AlignVCenter)

    def setChecked(self, v: bool):
        self.toggle.blockSignals(True)
        self.toggle.setChecked(v)
        self.toggle._pos = 1.0 if v else 0.0
        self.toggle.update()
        self.toggle.blockSignals(False)

    def isChecked(self) -> bool:
        return self.toggle.isChecked()


class ColorSwatch(QAbstractButton):
    colorChanged = Signal(tuple)

    def __init__(self, color=(255, 0, 0), size: int = 26, editable: bool = True, parent=None):
        super().__init__(parent)
        self._c = tuple(color)
        self._size = size
        self._editable = editable
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor if editable else Qt.ArrowCursor)
        if editable:
            self.clicked.connect(self._pick)

    def color(self) -> tuple:
        return self._c

    def setColor(self, c):
        self._c = tuple(c)
        self.update()

    def _pick(self):
        c = QColorDialog.getColor(QColor(*self._c), self, "Pick a colour")
        if c.isValid():
            self.setColor((c.red(), c.green(), c.blue()))
            self.colorChanged.emit(self._c)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(2, 2, self._size - 4, self._size - 4)
        p.setPen(QPen(qc(PAL.text if self.isChecked() or self.underMouse() else PAL.border), 2))
        p.setBrush(QColor(*self._c))
        p.drawEllipse(r)


class BatteryRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level: int | None = None
        self.charging = False
        self.setMinimumSize(132, 132)

    def set(self, level: int | None, charging: bool = False):
        self.level, self.charging = level, charging
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height()) - 16
        r = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        p.setPen(QPen(qc(PAL.surface3), 11, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 0, 360 * 16)
        if self.level is not None:
            g = QConicalGradient(r.center(), 90)
            col = PAL.bad if self.level <= 15 else (PAL.warn if self.level <= 30 else PAL.accent)
            g.setColorAt(0, qc(PAL.accent2 if self.level > 30 else col))
            g.setColorAt(1, qc(col))
            pen = QPen(g, 11)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(r, 90 * 16, int(-360 * 16 * max(0, min(100, self.level)) / 100))
        p.setPen(qc(PAL.text))
        f = QFont(self.font())
        f.setPointSize(19)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        txt = "—" if self.level is None else f"{self.level}%"
        if self.charging:
            txt = "⚡"
        p.drawText(r, Qt.AlignCenter, txt)
        f.setPointSize(8)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(qc(PAL.muted))
        p.drawText(r.adjusted(0, s * 0.42, 0, 0), Qt.AlignHCenter | Qt.AlignVCenter, "BATTERY")


class Segmented(QWidget):
    changed = Signal(object)

    def __init__(self, options: list[tuple[object, str]], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._values = []
        for i, (val, text) in enumerate(options):
            b = QPushButton(text)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b, i)
            lay.addWidget(b)
            self._values.append(val)
        lay.addStretch(1)
        self.group.idClicked.connect(lambda i: self.changed.emit(self._values[i]))

    def set(self, val):
        for i, v in enumerate(self._values):
            if v == val:
                self.group.button(i).setChecked(True)
                return
        self.group.setExclusive(False)
        for b in self.group.buttons():
            b.setChecked(False)
        self.group.setExclusive(True)

    def value(self):
        i = self.group.checkedId()
        return self._values[i] if i >= 0 else None


class KeyCapture(QLineEdit):
    """Click, then press a key combo. Emits (usage, modifiers)."""
    captured = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Click here, then press a key or combo…")
        self.setCursor(Qt.PointingHandCursor)
        self._pending_mod: int | None = None

    def event(self, e):
        # Grab Tab instead of moving focus.
        if e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.keyPressEvent(e)
            return True
        return super().event(e)

    @staticmethod
    def _mods(e: QKeyEvent) -> int:
        m = 0
        mods = e.modifiers()
        if mods & Qt.ControlModifier:
            m |= 0x01
        if mods & Qt.ShiftModifier:
            m |= 0x02
        if mods & Qt.AltModifier:
            m |= 0x04
        if mods & Qt.MetaModifier:
            m |= 0x08
        return m

    def keyPressEvent(self, e: QKeyEvent):
        if e.isAutoRepeat():
            return
        usage = VK_TO_HID.get(e.nativeVirtualKey())
        if usage is None:
            return
        if usage in MODIFIER_USAGES:
            self._pending_mod = usage
            self.setText(key_name(usage) + " …")
            return
        mods = self._mods(e)
        self._pending_mod = None
        self.setText(key_name(usage, mods))
        self.captured.emit(usage, mods)

    def keyReleaseEvent(self, e: QKeyEvent):
        if e.isAutoRepeat():
            return
        usage = VK_TO_HID.get(e.nativeVirtualKey())
        if usage == 0x46:  # Print Screen only arrives as a release on Windows
            self.setText(key_name(usage))
            self.captured.emit(usage, 0)
            return
        if self._pending_mod is not None and usage == self._pending_mod:
            # A lone modifier key (e.g. Shift for crouch) is a valid binding.
            self.setText(key_name(usage))
            self.captured.emit(usage, 0)
            self._pending_mod = None


class KeyPicker(QWidget):
    """Capture field + manual modifier checkboxes + key list, kept in sync."""
    changed = Signal(int, int)

    def __init__(self, usage: int = 0x04, modifiers: int = 0, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.capture = KeyCapture()
        lay.addWidget(self.capture)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.mods: dict[int, QCheckBox] = {}
        for bit, name in MOD_NAMES[:4]:
            cb = QCheckBox(name)
            cb.toggled.connect(self._emit)
            self.mods[bit] = cb
            row.addWidget(cb)
        row.addStretch(1)
        self.key = QComboBox()
        self.key.setMinimumWidth(170)
        for u, n in sorted(HID_NAMES.items(), key=lambda kv: kv[0]):
            self.key.addItem(n, u)
        self.key.currentIndexChanged.connect(self._emit)
        row.addWidget(self.key)
        lay.addLayout(row)
        self.capture.captured.connect(self.set)
        self.set(usage, modifiers)

    def set(self, usage: int, modifiers: int):
        for w in list(self.mods.values()) + [self.key]:
            w.blockSignals(True)
        for bit, cb in self.mods.items():
            cb.setChecked(bool(modifiers & bit))
        i = self.key.findData(usage)
        self.key.setCurrentIndex(max(0, i))
        for w in list(self.mods.values()) + [self.key]:
            w.blockSignals(False)
        self.capture.setText(key_name(usage, modifiers))
        self.changed.emit(usage, modifiers)

    def value(self) -> tuple[int, int]:
        m = sum(bit for bit, cb in self.mods.items() if cb.isChecked())
        return self.key.currentData(), m

    def _emit(self, *_):
        u, m = self.value()
        self.capture.setText(key_name(u, m))
        self.changed.emit(u, m)


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {PAL.border};")


def accent_bar(color: str, width: int = 4, height: int = 34) -> QWidget:
    w = QWidget()
    w.setFixedSize(width, height)
    w.setStyleSheet(f"background: {color}; border-radius: {width // 2}px;")
    return w


def rounded_path(r: QRectF, rad: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(r, rad, rad)
    return path


__all__ = ["label", "chip", "button", "Card", "hrow", "Toggle", "ToggleRow", "ColorSwatch", "BatteryRing",
           "Segmented", "KeyCapture", "KeyPicker", "Divider", "accent_bar", "rounded_path", "QPointF"]
