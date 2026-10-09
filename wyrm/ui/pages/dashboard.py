from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...core.model import EFFECT_LABELS
from ..theme import PAL, logo_svg, render_svg
from ..widgets import BatteryRing, Card, ToggleRow, accent_bar, button, chip, hrow, label
from .base import Page

REASONS = {"auto": "Switched automatically", "manual": "Picked by you", "hotkey": "Picked with the mouse button",
           "startup": "Restored at startup"}


class DashboardPage(Page):
    title = "Home"
    subtitle = "Your mouse at a glance"
    icon = "dashboard"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        grid = QGridLayout()
        grid.setSpacing(16)
        self.lay.addLayout(grid)

        # --- device card ---------------------------------------------------
        dev = Card()
        top = QHBoxLayout()
        top.setSpacing(16)
        self.logo = QLabel()
        self.logo.setFixedSize(64, 64)
        top.addWidget(self.logo, 0, Qt.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(6)
        info.addWidget(label("Redragon M811 PRO", "Big"))
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        info.addLayout(self.chips)
        self.dev_note = label("", "Muted", wrap=True)
        info.addWidget(self.dev_note)
        info.addStretch(1)
        top.addLayout(info, 1)
        self.battery = BatteryRing()
        top.addWidget(self.battery)
        dev.add(top)
        grid.addWidget(dev, 0, 0)

        # --- active profile card ------------------------------------------
        prof = Card()
        row = QHBoxLayout()
        row.setSpacing(14)
        self.bar = accent_bar(PAL.accent, 5, 64)
        row.addWidget(self.bar)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(label("ACTIVE PROFILE", "Dim"))
        self.prof_name = label("—", "Huge")
        col.addWidget(self.prof_name)
        self.prof_reason = label("", "Muted")
        col.addWidget(self.prof_reason)
        row.addLayout(col, 1)
        prof.add(row)
        self.auto = ToggleRow("Auto-switch by app", "Changes profile when a game or app you've linked comes to the front.")
        self.auto.toggled.connect(lambda v: (ctx.manager.set_auto(v), ctx.config_changed.emit()))
        prof.add(self.auto)
        self.front = label("", "Dim", wrap=True)
        prof.add(self.front)
        self.quick = QHBoxLayout()
        self.quick.setSpacing(6)
        prof.add(self.quick)
        grid.addWidget(prof, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # --- summaries --------------------------------------------------------
        self.dpi_card = Card("DPI stages")
        self.dpi_row = QHBoxLayout()
        self.dpi_row.setSpacing(8)
        self.dpi_card.add(self.dpi_row)
        grid.addWidget(self.dpi_card, 1, 0)

        self.light_card = Card("Lighting")
        self.light_lbl = label("", "Muted")
        self.light_card.add(self.light_lbl)
        grid.addWidget(self.light_card, 1, 1)

        self.tip = Card("Make it yours", "Create a profile per activity (Gaming, Work, Editing), link the apps that "
                                         "belong to it, and Wyrm switches for you. The Profile button on top of the "
                                         "mouse cycles through them too.")
        go = button("Set up profiles", "Primary", "profiles")
        go.clicked.connect(lambda: self.window().go("profiles"))
        self.tip.add(hrow(go, None))
        grid.addWidget(self.tip, 2, 0, 1, 2)

        apply = button("Re-apply to mouse", "Ghost", "bolt", "Write the active profile to the mouse again")
        apply.clicked.connect(ctx.manager.apply_active)
        self.lay.addLayout(hrow(None, apply))
        self.lay.addStretch(1)

        ctx.status_changed.connect(lambda _: self.refresh_status())
        ctx.manager.active_changed.connect(lambda p, r: self.refresh_profile(r))
        ctx.manager.profiles_changed.connect(lambda: self.refresh_profile())
        ctx.manager.foreground_changed.connect(lambda e, t: self.refresh_front())
        ctx.config_changed.connect(self.refresh)
        self._reason = "startup"

    # ---------------------------------------------------------------------------
    def refresh(self):
        self.logo.setPixmap(render_svg(logo_svg(mono=not self.ctx.status.get("connected")), 64))
        self.refresh_status()
        self.refresh_profile()
        self.refresh_front()

    def _clear(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def refresh_status(self):
        s = self.ctx.status
        self._clear(self.chips)
        self.logo.setPixmap(render_svg(logo_svg(mono=not s.get("connected")), 64))
        if not s.get("connected"):
            self.chips.addWidget(chip("Not found", "ChipWarn"))
            self.dev_note.setText("Plug in the receiver or the USB-C cable. Wyrm keeps looking.")
            self.battery.set(None)
        else:
            self.chips.addWidget(chip("2.4 GHz" if s.get("wireless") else "Cable", "ChipAccent"))
            if s.get("wireless"):
                self.chips.addWidget(chip("Awake" if s.get("link") else "Asleep", "Chip" if s.get("link") else "ChipWarn"))
            self.chips.addWidget(chip(f"fw {s.get('fw', '?')}"))
            if self.ctx.demo:
                self.chips.addWidget(chip("Demo", "ChipWarn"))
            note = ""
            if s.get("pending"):
                note = "Changes are waiting. Move the mouse to wake it and they'll be written."
            elif s.get("wireless") and not s.get("link"):
                note = "The mouse is asleep. Move it to wake it up."
            if s.get("error"):
                note = s["error"]
            self.dev_note.setText(note)
            self.battery.set(s.get("battery"), bool(s.get("charging")))
        self.chips.addStretch(1)

    def refresh_profile(self, reason: str | None = None):
        if reason:
            self._reason = reason
        m = self.ctx.manager
        p = m.active()
        if not p:
            return
        self.prof_name.setText(p.name)
        self.bar.setStyleSheet(f"background: {p.accent}; border-radius: 2px;")
        self.prof_reason.setText(REASONS.get(self._reason, ""))
        self.auto.setChecked(self.ctx.store.config.auto_switch)
        self._clear(self.quick)
        for q in m.profiles():
            b = QPushButton(q.name)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setChecked(q.id == p.id)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, pid=q.id: m.switch(pid, "manual"))
            self.quick.addWidget(b)
        self.quick.addStretch(1)
        self._clear(self.dpi_row)
        for i, st in enumerate(p.dpi_stages):
            c = "#%02x%02x%02x" % tuple(st.color)
            lb = QLabel(f"{st.dpi}")
            lb.setAlignment(Qt.AlignCenter)
            lb.setMinimumSize(QSize(70, 46))
            active = i == p.active_stage
            lb.setStyleSheet(
                f"background: {PAL.surface2}; border-radius: 10px; font-weight: 700; font-size: 12pt;"
                f"border: 2px solid {c if active else PAL.border}; color: {PAL.text if st.enabled else PAL.dim};")
            lb.setToolTip("Default stage" if active else f"Stage {i + 1}")
            self.dpi_row.addWidget(lb)
        self.dpi_row.addStretch(1)
        lt = p.lighting
        self.light_lbl.setText(EFFECT_LABELS.get(lt.effect, lt.effect) + f" · brightness {lt.brightness}/4"
                               if lt else "Left as it is on the mouse")
        self.tip.setVisible(len(m.profiles()) < 2 or not any(q.rules for q in m.profiles()))

    def refresh_front(self):
        m = self.ctx.manager
        exe = m._last_exe
        if not exe:
            self.front.setText("")
            return
        hit = m.matched_profile()
        tail = f"→ linked to {hit.name}" if hit else "→ no link, uses the default profile"
        self.front.setText(f"In front now: {exe}  {tail}")
