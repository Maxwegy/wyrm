from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ...core.model import EFFECT_LABELS
from ..devices import DeviceCard
from ..theme import PAL
from ..widgets import Card, ToggleRow, accent_bar, button, hrow, label
from .base import Page

REASONS = {"auto": "Switched automatically", "manual": "Picked by you", "hotkey": "Picked with a mouse button",
           "startup": "Restored at startup"}
SUPPORTED_MICE = "https://github.com/Maxwegy/wyrm/blob/main/docs/devices.md"


class DashboardPage(Page):
    title = "Home"
    subtitle = "Your mice at a glance"
    icon = "dashboard"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.lay.addWidget(label("YOUR MICE", "SideHead"))
        self.mice = QGridLayout()
        self.mice.setSpacing(16)
        self.lay.addLayout(self.mice)
        self.cards: list[DeviceCard] = []
        self.empty = Card("No mouse found yet", "Plug in a mouse, its receiver or its cable. Wyrm keeps looking, "
                                                "and any mouse it can see shows up here.")
        link = button("Supported mice", "Ghost", "link")
        link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SUPPORTED_MICE)))
        self.empty.add(hrow(link, None))
        self.lay.addWidget(self.empty)

        grid = QGridLayout()
        grid.setSpacing(16)
        self.lay.addLayout(grid)
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
        grid.addWidget(prof, 0, 0)

        # --- what the active profile does to the selected mouse ----------------------------
        self.summary = Card()
        self.sum_title = label("", "CardTitle")
        self.summary.add(self.sum_title)
        self.sum_src = label("", "Dim", wrap=True)
        self.summary.add(self.sum_src)
        self.dpi_row = QHBoxLayout()
        self.dpi_row.setSpacing(8)
        self.summary.add(self.dpi_row)
        self.light_lbl = label("", "Muted")
        self.summary.add(self.light_lbl)
        self.summary.body.addStretch(1)
        grid.addWidget(self.summary, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.tip = Card("Make it yours", "Create a profile per activity (Gaming, Work, Editing), link the apps that "
                                         "belong to it, and Wyrm switches every mouse for you. A mouse button set to "
                                         "\"Next profile\" cycles through them too.")
        go = button("Set up profiles", "Primary", "profiles")
        go.clicked.connect(lambda: self.window().go("profiles"))
        self.tip.add(hrow(go, None))
        self.lay.addWidget(self.tip)

        apply = button("Re-apply to mice", "Ghost", "bolt", "Write the active profile to every mouse again")
        apply.clicked.connect(lambda: ctx.manager.apply_active(user=True))
        self.lay.addLayout(hrow(None, apply))
        self.lay.addStretch(1)

        for s in (ctx.devices_changed, ctx.current_changed, ctx.in_use_changed, ctx.conflicts_changed):
            s.connect(self.refresh_mice)
        ctx.status_changed.connect(lambda _: self.refresh_mice())
        ctx.state_changed.connect(lambda _: self.refresh_profile())
        ctx.current_changed.connect(self.refresh_profile)
        ctx.manager.active_changed.connect(lambda p, r: self.refresh_profile(r))
        ctx.manager.profiles_changed.connect(lambda: self.refresh_profile())
        ctx.manager.foreground_changed.connect(lambda e, t: self.refresh_front())
        ctx.config_changed.connect(self.refresh)
        self._reason = "startup"
        self._sig = None

    # ---------------------------------------------------------------------------
    def refresh(self):
        self._sig = None
        self.refresh_mice()
        self.refresh_profile()
        self.refresh_front()

    def _clear(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def refresh_mice(self):
        ctx = self.ctx
        cur = ctx.current()
        rows = [(i, ctx.status_of(i), True) for i in ctx.mice()]
        rows += [(i, {}, False) for i in ctx.offline_mice() if i.caps.configurable]
        sig = [(repr(i), repr(st), here, i.uid in ctx.in_use, ctx.conflict_for(i), bool(cur and cur.key == i.key))
               for i, st, here in rows]
        if sig == self._sig:
            return
        self._sig = sig
        while len(self.cards) < len(rows):
            card = DeviceCard()
            card.picked.connect(ctx.set_current)
            self.cards.append(card)
        for card in self.cards:
            self.mice.removeWidget(card)
            card.hide()
        for n, (info, st, here) in enumerate(rows):
            card = self.cards[n]
            card.set(info, st, connected=here, selected=bool(cur and cur.key == info.key),
                     in_use=info.uid in ctx.in_use, conflict=ctx.conflict_for(info) if here else "",
                     last_seen=ctx.store.known.get(info.key, {}).get("last_seen", ""))
            self.mice.addWidget(card, n, 0)
            card.show()
        self.empty.setVisible(not rows)

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

        dev = self.ctx.current()
        self.summary.setVisible(dev is not None)
        self._clear(self.dpi_row)
        if dev is not None:
            s, src = self.ctx.device_settings(p)
            self.sum_title.setText(f"{dev.short_name} in {p.name}")
            self.sum_src.setText({"own": f"Set by {p.name}.", "default": "Follows the default profile.",
                                  "mouse": "Not set by any profile yet: shown as it is on the mouse."}.get(src, ""))
            for i, st in enumerate(s.dpi_stages if s else []):
                c = "#%02x%02x%02x" % tuple(st.color)
                lb = QLabel(f"{st.dpi}")
                lb.setAlignment(Qt.AlignCenter)
                lb.setMinimumSize(QSize(70, 46))
                active = i == s.active_stage
                ring = c if dev.caps.stage_colors else PAL.accent
                lb.setStyleSheet(
                    f"background: {PAL.surface2}; border-radius: 10px; font-weight: 700; font-size: 12pt;"
                    f"border: 2px solid {ring if active else PAL.border}; color: {PAL.text if st.enabled else PAL.dim};")
                lb.setToolTip("Default stage" if active else f"Stage {i + 1}")
                self.dpi_row.addWidget(lb)
            self.dpi_row.addStretch(1)
            lt = s.lighting if s else None
            parts = []
            if s and s.polling_hz and dev.caps.polling_rates:
                parts.append(f"{s.polling_hz} Hz")
            if dev.caps.effects:
                parts.append(EFFECT_LABELS.get(lt.effect, lt.effect) + f" · brightness {lt.brightness}/4" if lt else
                             "Lighting left as it is")
            self.light_lbl.setText("  ·  ".join(parts))
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
