from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QRadioButton, QSlider, QSpinBox, QWidget

from ...core.model import DpiStage
from ...drivers.base import Capabilities
from ..devices import InheritBanner
from ..rate_test import RateTestDialog
from ..widgets import Card, ColorSwatch, Segmented, Toggle, button, chip, hrow, label
from .base import Page

PRESETS = {
    "Default": [1000, 2000, 4000, 8000, 26000],
    "Precise": [400, 800, 1200, 1600, 3200],
    "Shooter": [400, 800, 1600, 3200, 6400],
    "Desktop": [800, 1600, 2400, 3200, 4800],
}
STAGE_COLORS = [(255, 0, 0), (0, 0, 255), (0, 255, 255), (255, 0, 255), (255, 255, 0),
                (0, 255, 0), (255, 128, 0), (255, 255, 255)]


def dpi_to_pos(dpi: int, caps: Capabilities) -> int:
    lo, hi = caps.dpi_min, max(caps.dpi_max, caps.dpi_min + 1)
    return int(round(math.sqrt(max(0.0, min(1.0, (dpi - lo) / (hi - lo)))) * 1000))


def pos_to_dpi(pos: int, caps: Capabilities) -> int:
    return caps.snap_dpi(caps.dpi_min + (pos / 1000) ** 2 * (caps.dpi_max - caps.dpi_min))


class StageRow(QWidget):
    def __init__(self, idx: int, page: "PerformancePage", group: QButtonGroup):
        super().__init__()
        self.idx, self.page = idx, page
        self.caps = Capabilities(dpi_min=50, dpi_max=26000, dpi_step=50)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(12)
        self.swatch = ColorSwatch((255, 0, 0), 28)
        self.swatch.setToolTip("Indicator colour for this stage")
        self.swatch.colorChanged.connect(lambda c: page.edit_stage(idx, color=c))
        lay.addWidget(self.swatch)
        self.name = label(f"Stage {idx + 1}")
        self.name.setFixedWidth(56)
        lay.addWidget(self.name)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.valueChanged.connect(self._slid)
        self.slider.sliderReleased.connect(lambda: page.edit_stage(idx, dpi=self.spin.value()))
        lay.addWidget(self.slider, 1)
        self.spin = QSpinBox()
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

    def set(self, st: DpiStage, caps: Capabilities, can_disable: bool):
        self.caps = caps
        single = caps.dpi_stages == 1
        for w in (self.slider, self.spin, self.enabled):
            w.blockSignals(True)
        self.spin.setRange(caps.dpi_min, caps.dpi_max)
        self.spin.setSingleStep(caps.dpi_step or 50)
        self.name.setText("DPI" if single else f"Stage {self.idx + 1}")
        self.swatch.setVisible(caps.stage_colors)
        self.radio.setVisible(not single)
        self.enabled.setVisible(not single)
        self.swatch.setColor(st.color)
        self.slider.setValue(dpi_to_pos(st.dpi, caps))
        self.spin.setValue(st.dpi)
        self.enabled.setChecked(st.enabled)
        self.enabled._pos = 1.0 if st.enabled else 0.0
        self.enabled.setEnabled(can_disable)
        for w in (self.slider, self.spin, self.enabled):
            w.blockSignals(False)

    def _slid(self, pos):
        self.spin.blockSignals(True)
        self.spin.setValue(pos_to_dpi(pos, self.caps))
        self.spin.blockSignals(False)
        if not self.slider.isSliderDown():
            self.page.edit_stage(self.idx, dpi=self.spin.value())

    def _spun(self, v):
        v = self.caps.snap_dpi(v)
        self.slider.blockSignals(True)
        self.slider.setValue(dpi_to_pos(v, self.caps))
        self.slider.blockSignals(False)
        self.page.edit_stage(self.idx, dpi=v)


class PerformancePage(Page):
    title = "Performance"
    subtitle = "DPI and polling rate"
    icon = "performance"
    edits_profile = True
    edits_device = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.banner = InheritBanner(ctx)
        self.lay.addWidget(self.banner)
        self.notice, self.notice_text = self.notice_card()
        self.lay.addWidget(self.notice)

        self.dpi_card = Card()
        self.dpi_title = label("DPI stages", "CardTitle")
        self.dpi_card.add(self.dpi_title)
        self.dpi_sub = label("", "Muted", wrap=True)
        self.dpi_card.add(self.dpi_sub)
        self.group = QButtonGroup(self)
        self.group.idClicked.connect(lambda i: ctx.edit_device(lambda s: setattr(s, "active_stage", i), self))
        self.rows = [StageRow(i, self, self.group) for i in range(8)]
        for r in self.rows:
            self.dpi_card.add(r)
        pres = []
        for name, vals in PRESETS.items():
            b = button(name, "Ghost")
            b.clicked.connect(lambda _=False, v=vals: self._preset(v))
            pres.append(b)
        self.presets = QWidget()
        self.presets.setLayout(hrow(label("Presets", "Dim"), *pres, None))
        self.dpi_card.add(self.presets)
        self.lay.addWidget(self.dpi_card)

        self.poll = Card("Polling rate", "How often the mouse reports to the PC. Higher is smoother; "
                                         "lower saves battery.")
        self.seg_row = QHBoxLayout()
        self.poll.add(self.seg_row)
        self.seg: Segmented | None = None
        self._rates: list[int] | None = None
        self.poll_state = QHBoxLayout()
        self.poll.add(self.poll_state)
        self.poll_note = label("", "Muted", wrap=True)
        self.poll.add(self.poll_note)
        test = button("Test polling rate", None, "performance")
        test.clicked.connect(self._test)
        self.poll.add(hrow(test, None))
        self.lay.addWidget(self.poll)
        self.lay.addStretch(1)
        ctx.state_changed.connect(lambda _: self.isVisible() and self.refresh())
        ctx.status_changed.connect(lambda _: self.isVisible() and self._poll_info())
        ctx.config_changed.connect(lambda: self.isVisible() and self.refresh())

    def refresh(self):
        self.banner.refresh()
        dev, caps = self.ctx.current(), self.ctx.caps()
        s, _ = self.ctx.device_settings()
        has_dpi, has_rate = bool(caps.dpi_stages), bool(caps.polling_rates)
        if dev is None or not (has_dpi or has_rate) or s is None:
            self.notice_text.setText("Plug in a mouse Wyrm can configure to change its DPI and polling rate."
                                     if dev is None else
                                     f"Waiting to read the {dev.short_name}'s current settings. Move it to wake it up."
                                     if s is None else f"Wyrm can't change the {dev.short_name}'s DPI or polling "
                                                       "rate yet.")
            self.notice.show()
            for w in (self.dpi_card, self.poll):
                w.hide()
            return
        self.notice.hide()
        self.dpi_card.setVisible(has_dpi)
        self.poll.setVisible(has_rate)
        if has_dpi:
            self._fill_dpi(s, caps)
        if has_rate:
            self._fill_rates(caps)
            self.seg.set(s.polling_hz)
            self._poll_info()

    def _fill_dpi(self, s, caps):
        n = caps.dpi_stages
        allow = self.ctx.allow()
        can_disable = "*" in allow or "stage_enable" in allow
        stages = list(s.dpi_stages[:n])
        while len(stages) < n:
            stages.append(DpiStage(caps.snap_dpi(800 * (len(stages) + 1)), True, STAGE_COLORS[len(stages) % 8]))
        for i, r in enumerate(self.rows):
            r.setVisible(i < n)
            if i < n:
                r.set(stages[i], caps, can_disable)
        b = self.group.button(min(s.active_stage, n - 1))
        if b:
            b.setChecked(True)
        sensor =f" ({caps.sensor} sensor)" if caps.sensor else ""
        step = f" in steps of {caps.dpi_step}" if caps.dpi_step else ""
        what = "The DPI buttons step through these. " if n > 1 else ""
        self.dpi_title.setText("DPI stages" if n > 1 else "DPI")
        self.dpi_sub.setText(f"{what}Range {caps.dpi_min:,} – {caps.dpi_max:,}{step}{sensor}.")
        self.presets.setVisible(n == 5)

    def _fill_rates(self, caps):
        if self._rates == caps.polling_rates:
            return
        self._rates = list(caps.polling_rates)
        if self.seg is not None:
            self.seg_row.removeWidget(self.seg)
            self.seg.deleteLater()
        self.seg = Segmented([(None, "Keep")] + [(r, f"{r} Hz") for r in caps.polling_rates])
        self.seg.changed.connect(lambda v: self.ctx.edit_device(lambda s: setattr(s, "polling_hz", v), self))
        self.seg_row.addWidget(self.seg)

    def _poll_info(self):
        dev, caps = self.ctx.current(), self.ctx.caps()
        if dev is None or not caps.polling_rates:
            return
        while self.poll_state.count():
            w = self.poll_state.takeAt(0).widget()
            if w:
                w.deleteLater()
        allow = self.ctx.allow()
        gated = "polling" in caps.unverified
        verified = "*" not in allow and "polling" in allow
        unlocked = not gated or "*" in allow or "polling" in allow
        rate = self._device_rate()
        if rate:
            self.poll_state.addWidget(chip(f"Mouse reports {rate} Hz"))
        if gated:
            self.poll_state.addWidget(chip("Verified on your mouse", "ChipAccent") if verified else
                                      chip("Experimental" if unlocked else "Not yet verified", "ChipWarn"))
        self.poll_state.addStretch(1)
        note = self.ctx.status_of(dev).get("note", "")
        if not unlocked:
            note = (f"Wyrm hasn't confirmed how the {dev.short_name} encodes the polling rate, so it won't change "
                    "it yet. Run the test: if the measured rate matches what Wyrm decoded, polling-rate changes "
                    "unlock.")
        self.poll_note.setText(note)
        self.poll_note.setVisible(bool(note))

    def _device_rate(self):
        st = self.ctx.device_state()
        return st.polling_hz if st else None

    def edit_stage(self, idx: int, **kw):
        n = self.ctx.caps().dpi_stages

        def fn(s):
            while len(s.dpi_stages) < n:
                s.dpi_stages.append(DpiStage(800, True, STAGE_COLORS[len(s.dpi_stages) % 8]))
            st = s.dpi_stages[idx]
            for k, v in kw.items():
                setattr(st, k, tuple(v) if k == "color" else v)
        self.ctx.edit_device(fn, self)
        self.banner.refresh()

    def _preset(self, vals):
        caps = self.ctx.caps()

        def fn(s):
            for st, v in zip(s.dpi_stages, vals):
                st.dpi = caps.snap_dpi(v)
        self.ctx.edit_device(fn, self)
        self.refresh()

    def _test(self):
        dev = self.ctx.current()
        d = RateTestDialog(self._device_rate(), (dev.vid, dev.pid) if dev else None,
                           dev.short_name if dev else "mouse", self)
        d.exec()
        if d.matches() and dev and "polling" in dev.caps.unverified:
            cfg = self.ctx.store.config
            got = cfg.verified.setdefault(dev.key, [])
            if "polling" not in got:
                got.append("polling")
                self.ctx.save_config()
        self.refresh()
