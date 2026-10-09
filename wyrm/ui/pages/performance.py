from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QRadioButton, QSlider, QSpinBox, QWidget

from ...core.model import POLLING_RATES, DpiStage
from ...hid.codec.layout import load_layout
from ..rate_test import RateTestDialog
from ..widgets import Card, ColorSwatch, Segmented, Toggle, button, chip, hrow, label
from .base import Page

DPI_MIN, DPI_MAX, DPI_STEP = 50, 26000, 50
PRESETS = {
    "Default": [1000, 2000, 4000, 8000, 26000],
    "Precise": [400, 800, 1200, 1600, 3200],
    "Shooter": [400, 800, 1600, 3200, 6400],
    "Desktop": [800, 1600, 2400, 3200, 4800],
}


def dpi_to_pos(dpi: int) -> int:
    return int(round(math.sqrt((dpi - DPI_MIN) / (DPI_MAX - DPI_MIN)) * 1000))


def pos_to_dpi(pos: int) -> int:
    d = DPI_MIN + (pos / 1000) ** 2 * (DPI_MAX - DPI_MIN)
    return int(round(d / DPI_STEP) * DPI_STEP)


class StageRow(QWidget):
    def __init__(self, idx: int, page: "PerformancePage", group: QButtonGroup):
        super().__init__()
        self.idx, self.page = idx, page
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(12)
        self.swatch = ColorSwatch((255, 0, 0), 28)
        self.swatch.setToolTip("Indicator colour for this stage")
        self.swatch.colorChanged.connect(lambda c: page.edit_stage(idx, color=c))
        lay.addWidget(self.swatch)
        name = label(f"Stage {idx + 1}")
        name.setFixedWidth(56)
        lay.addWidget(name)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.valueChanged.connect(self._slid)
        self.slider.sliderReleased.connect(lambda: page.edit_stage(idx, dpi=self.spin.value()))
        lay.addWidget(self.slider, 1)
        self.spin = QSpinBox()
        self.spin.setRange(DPI_MIN, DPI_MAX)
        self.spin.setSingleStep(DPI_STEP)
        self.spin.setSuffix(" dpi")
        self.spin.setFixedWidth(110)
        self.spin.setKeyboardTracking(False)
        self.spin.valueChanged.connect(self._spun)
        lay.addWidget(self.spin)
        self.radio = QRadioButton("Default")
        self.radio.setToolTip("The stage the mouse starts in")
        group.addButton(self.radio, idx)
        lay.addWidget(self.radio)
        self.enabled = Toggle(True)
        self.enabled.setToolTip("Include this stage when cycling (experimental)")
        self.enabled.toggled.connect(lambda v: page.edit_stage(idx, enabled=v))
        lay.addWidget(self.enabled)

    def set(self, st: DpiStage, can_disable: bool):
        for w in (self.slider, self.spin, self.enabled):
            w.blockSignals(True)
        self.swatch.setColor(st.color)
        self.slider.setValue(dpi_to_pos(st.dpi))
        self.spin.setValue(st.dpi)
        self.enabled.setChecked(st.enabled)
        self.enabled._pos = 1.0 if st.enabled else 0.0
        self.enabled.setEnabled(can_disable)
        for w in (self.slider, self.spin, self.enabled):
            w.blockSignals(False)

    def _slid(self, pos):
        self.spin.blockSignals(True)
        self.spin.setValue(pos_to_dpi(pos))
        self.spin.blockSignals(False)
        if not self.slider.isSliderDown():
            self.page.edit_stage(self.idx, dpi=self.spin.value())

    def _spun(self, v):
        v = int(round(v / DPI_STEP) * DPI_STEP)
        self.slider.blockSignals(True)
        self.slider.setValue(dpi_to_pos(v))
        self.slider.blockSignals(False)
        self.page.edit_stage(self.idx, dpi=v)


class PerformancePage(Page):
    title = "Performance"
    subtitle = "DPI stages and polling rate"
    icon = "performance"
    edits_profile = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        card = Card("DPI stages", "The DPI buttons step through these. Range 50 – 26,000 in steps of 50 "
                                  "(PixArt PAW3395 sensor).")
        self.group = QButtonGroup(self)
        self.group.idClicked.connect(lambda i: ctx.edit(lambda p: setattr(p, "active_stage", i), self))
        self.rows = [StageRow(i, self, self.group) for i in range(5)]
        for r in self.rows:
            card.add(r)
        pres = []
        for name, vals in PRESETS.items():
            b = button(name, "Ghost")
            b.clicked.connect(lambda _=False, v=vals: self._preset(v))
            pres.append(b)
        card.add(hrow(label("Presets", "Dim"), *pres, None))
        self.lay.addWidget(card)

        poll = Card("Polling rate", "How often the mouse reports to the PC. Higher is smoother; "
                                    "lower saves battery.")
        self.seg = Segmented([(None, "Keep")] + [(r, f"{r} Hz") for r in POLLING_RATES])
        self.seg.changed.connect(lambda v: ctx.edit(lambda p: setattr(p, "polling_hz", v), self))
        poll.add(self.seg)
        self.poll_state = QHBoxLayout()
        poll.add(self.poll_state)
        self.poll_note = label("", "Muted", wrap=True)
        poll.add(self.poll_note)
        test = button("Test polling rate", None, "performance")
        test.clicked.connect(self._test)
        poll.add(hrow(test, None))
        self.lay.addWidget(poll)
        self.lay.addStretch(1)
        ctx.state_changed.connect(lambda _: self.isVisible() and self.refresh())
        ctx.config_changed.connect(lambda: self.isVisible() and self.refresh())

    def refresh(self):
        p = self.ctx.editing()
        if not p:
            return
        allow = self.ctx.allow()
        can_disable = "*" in allow or "stage_enable" in allow
        while len(p.dpi_stages) < 5:
            p.dpi_stages.append(DpiStage())
        for r, st in zip(self.rows, p.dpi_stages):
            r.set(st, can_disable)
        b = self.group.button(min(p.active_stage, 4))
        if b:
            b.setChecked(True)
        self.seg.set(p.polling_hz)
        while self.poll_state.count():
            w = self.poll_state.takeAt(0).widget()
            if w:
                w.deleteLater()
        verified = "*" not in allow and "polling" in allow
        unlocked = "*" in allow or "polling" in allow
        dev = self._device_rate()
        if dev:
            self.poll_state.addWidget(chip(f"Mouse reports {dev} Hz"))
        self.poll_state.addWidget(chip("Verified on your mouse", "ChipAccent") if verified else
                                  chip("Experimental" if unlocked else "Not yet verified", "ChipWarn"))
        self.poll_state.addStretch(1)
        if not unlocked:
            self.poll_note.setText("Wyrm hasn't confirmed how this firmware encodes the polling rate, so it won't "
                                   "change it yet. Run the test: if the measured rate matches what Wyrm decoded, "
                                   "polling-rate changes unlock.")
        else:
            self.poll_note.setText("")

    def _device_rate(self):
        st = self.ctx.state
        if not st or "raw_settings" not in st:
            return None
        L = load_layout()
        code = st["raw_settings"][L["polling"]["offset"]] & 0x0F
        return L["polling"]["map"].get(str(code))

    def edit_stage(self, idx: int, **kw):
        def fn(p):
            st = p.dpi_stages[idx]
            for k, v in kw.items():
                setattr(st, k, tuple(v) if k == "color" else v)
        self.ctx.edit(fn, self)

    def _preset(self, vals):
        def fn(p):
            for st, v in zip(p.dpi_stages, vals):
                st.dpi = v
        self.ctx.edit(fn, self)
        self.refresh()

    def _test(self):
        d = RateTestDialog(self._device_rate(), self)
        d.exec()
        if d.matches():
            cfg = self.ctx.store.config
            if "polling" not in cfg.verified:
                cfg.verified.append("polling")
                self.ctx.save_config()
        self.refresh()
