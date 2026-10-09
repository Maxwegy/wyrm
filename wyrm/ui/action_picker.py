"""Dialog for choosing what a mouse button does."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QListWidget,
                               QListWidgetItem, QRadioButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from ..core.keys import CONSUMER_NAMES, MOUSE_BUTTONS
from ..core.model import ButtonAction
from .widgets import KeyPicker, label

CATS = [
    ("mouse", "Mouse click"), ("key", "Keyboard key"), ("macro", "Macro"), ("consumer", "Media & apps"),
    ("dpi", "DPI"), ("profile", "Switch profile"), ("fire", "Rapid fire"), ("wheel", "Scroll"),
    ("light", "Lighting on/off"), ("disabled", "Disabled"),
]


def _radio_group(parent_lay, options):
    grp = QButtonGroup(parent_lay.parentWidget())
    for i, (val, text) in enumerate(options):
        rb = QRadioButton(text)
        rb.setProperty("val", val)
        grp.addButton(rb, i)
        parent_lay.addWidget(rb)
    return grp


def _page(title: str, desc: str = ""):
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(4, 0, 0, 0)
    lay.setSpacing(10)
    lay.addWidget(label(title, "CardTitle"))
    if desc:
        lay.addWidget(label(desc, "Muted", wrap=True))
    return w, lay


class ActionPicker(QDialog):
    def __init__(self, slot_name: str, action: ButtonAction, macros: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{slot_name} button")
        self.setMinimumSize(700, 600)
        self.macros = macros
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.addWidget(label(f"What should {slot_name} do?", "PageTitle"))
        body = QHBoxLayout()
        body.setSpacing(16)
        self.cats = QListWidget()
        self.cats.setFixedWidth(190)
        for key, text in CATS:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, key)
            self.cats.addItem(it)
        body.addWidget(self.cats)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        # mouse
        w, lay = _page("Mouse click")
        self.g_mouse = _radio_group(lay, [(bit, n) for bit, n in MOUSE_BUTTONS])
        lay.addStretch(1)
        self.stack.addWidget(w)
        # key
        w, lay = _page("Keyboard key", "Press the key or combo in the box, or build it with the checkboxes.")
        self.keys = KeyPicker()
        lay.addWidget(self.keys)
        lay.addStretch(1)
        self.stack.addWidget(w)
        # macro
        w, lay = _page("Macro", "Macros run on the mouse itself, so they work in every app.")
        self.macro = QComboBox()
        for m in sorted(macros.values(), key=lambda m: m.name.lower()):
            self.macro.addItem(m.name, m.id)
        if not macros:
            lay.addWidget(label("No macros yet. Record one on the Macros page first.", "Warn", wrap=True))
        lay.addWidget(self.macro)
        self.g_mode = _radio_group(lay, [(1, "Play a number of times"), (4, "Repeat while held"),
                                         (2, "Repeat until any key is pressed")])
        row = QHBoxLayout()
        row.addWidget(label("Times"))
        self.macro_count = QSpinBox()
        self.macro_count.setRange(1, 255)
        row.addWidget(self.macro_count)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        self.stack.addWidget(w)
        # consumer
        w, lay = _page("Media & apps")
        self.media = QListWidget()
        for u, n in CONSUMER_NAMES.items():
            it = QListWidgetItem(n)
            it.setData(Qt.UserRole, u)
            self.media.addItem(it)
        lay.addWidget(self.media, 1)
        self.stack.addWidget(w)
        # dpi
        w, lay = _page("DPI")
        self.g_dpi = _radio_group(lay, [("dpi_up", "Next DPI stage"), ("dpi_down", "Previous DPI stage"),
                                        ("dpi_cycle", "Cycle DPI stages"),
                                        ("dpi_lock", "Sniper: hold for a fixed DPI (experimental)")])
        row = QHBoxLayout()
        row.addWidget(label("Sniper DPI"))
        self.dpi_lock = QSpinBox()
        self.dpi_lock.setRange(100, 25500)
        self.dpi_lock.setSingleStep(100)
        self.dpi_lock.setValue(400)
        row.addWidget(self.dpi_lock)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        self.stack.addWidget(w)
        # profile
        w, lay = _page("Switch profile", "Cycles Wyrm profiles while Wyrm is running. "
                                         "Works through the F23/F24 keys, so no extra drivers are needed.")
        self.g_prof = _radio_group(lay, [("profile_next", "Next profile"), ("profile_prev", "Previous profile")])
        lay.addStretch(1)
        self.stack.addWidget(w)
        # fire
        w, lay = _page("Rapid fire", "One press sends several clicks.")
        self.g_fire = _radio_group(lay, [(bit, n) for bit, n in MOUSE_BUTTONS[:3]])
        row = QHBoxLayout()
        row.addWidget(label("Clicks"))
        self.fire_count = QSpinBox()
        self.fire_count.setRange(2, 255)
        self.fire_count.setValue(3)
        row.addWidget(self.fire_count)
        row.addSpacing(16)
        row.addWidget(label("Gap (ms)"))
        self.fire_delay = QSpinBox()
        self.fire_delay.setRange(1, 255)
        self.fire_delay.setValue(50)
        row.addWidget(self.fire_delay)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        self.stack.addWidget(w)
        # wheel
        w, lay = _page("Scroll")
        self.g_wheel = _radio_group(lay, [(1, "Scroll up"), (-1, "Scroll down")])
        lay.addStretch(1)
        self.stack.addWidget(w)
        # light, disabled
        for title, desc in (("Lighting on/off", "Toggles the mouse LEDs."),
                            ("Disabled", "The button does nothing.")):
            w, lay = _page(title, desc)
            lay.addStretch(1)
            self.stack.addWidget(w)

        self.cats.currentRowChanged.connect(self.stack.setCurrentIndex)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self._load(action)

    def _check(self, grp: QButtonGroup, val):
        for b in grp.buttons():
            if b.property("val") == val:
                b.setChecked(True)
                return
        grp.buttons()[0].setChecked(True)

    def _load(self, a: ButtonAction):
        k = a.kind
        cat = {"mouse": 0, "key": 1, "macro": 2, "consumer": 3, "dpi_up": 4, "dpi_down": 4, "dpi_cycle": 4,
               "dpi_lock": 4, "profile_next": 5, "profile_prev": 5, "profile_cycle": 5, "fire": 6,
               "wheel": 7, "light_toggle": 8, "disabled": 9}.get(k, 9)
        self.cats.setCurrentRow(cat)
        self._check(self.g_mouse, a.mouse_mask if k == "mouse" else 1)
        if k == "key":
            self.keys.set(a.usage, a.modifiers)
        i = self.macro.findData(a.macro_id)
        self.macro.setCurrentIndex(max(0, i))
        self._check(self.g_mode, a.macro_mode if k == "macro" else 1)
        self.macro_count.setValue(a.count if k == "macro" else 1)
        for r in range(self.media.count()):
            if self.media.item(r).data(Qt.UserRole) == (a.usage if k == "consumer" else 0xCD):
                self.media.setCurrentRow(r)
        self._check(self.g_dpi, k if k.startswith("dpi") else "dpi_up")
        if k == "dpi_lock":
            self.dpi_lock.setValue(a.usage)
        self._check(self.g_prof, k if k in ("profile_next", "profile_prev") else "profile_next")
        self._check(self.g_fire, a.mouse_mask if k == "fire" else 1)
        if k == "fire":
            self.fire_count.setValue(a.count)
            self.fire_delay.setValue(a.delay)
        self._check(self.g_wheel, a.usage if k == "wheel" else 1)

    def result_action(self) -> ButtonAction:
        cat = CATS[self.cats.currentRow()][0]
        if cat == "mouse":
            return ButtonAction.mouse(self.g_mouse.checkedButton().property("val"))
        if cat == "key":
            u, m = self.keys.value()
            return ButtonAction.key(u, m)
        if cat == "macro":
            if self.macro.currentData() is None:
                return ButtonAction("disabled")
            return ButtonAction("macro", macro_id=self.macro.currentData(),
                                macro_mode=self.g_mode.checkedButton().property("val"),
                                count=self.macro_count.value())
        if cat == "consumer":
            it = self.media.currentItem()
            return ButtonAction("consumer", usage=it.data(Qt.UserRole) if it else 0xCD)
        if cat == "dpi":
            k = self.g_dpi.checkedButton().property("val")
            return ButtonAction(k, usage=self.dpi_lock.value() if k == "dpi_lock" else 0)
        if cat == "profile":
            return ButtonAction(self.g_prof.checkedButton().property("val"))
        if cat == "fire":
            return ButtonAction("fire", mouse_mask=self.g_fire.checkedButton().property("val"),
                                count=self.fire_count.value(), delay=self.fire_delay.value())
        if cat == "wheel":
            return ButtonAction("wheel", usage=self.g_wheel.checkedButton().property("val"))
        if cat == "light":
            return ButtonAction("light_toggle")
        return ButtonAction("disabled")
