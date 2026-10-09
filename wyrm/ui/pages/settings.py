from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QMessageBox

from ... import __version__
from ...core import winapi
from ...paths import data_dir, sub
from ..theme import ACCENTS
from ..widgets import Card, ColorSwatch, ToggleRow, button, hrow, label
from .base import Page


class SettingsPage(Page):
    title = "Settings"
    subtitle = "How Wyrm behaves"
    icon = "settings"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        cfg = ctx.store.config

        gen = Card("General")
        self.autostart = ToggleRow("Start with Windows", "Runs quietly in the tray so profiles and auto-switch work "
                                                         "from boot.")
        self.autostart.toggled.connect(self._autostart)
        gen.add(self.autostart)
        self.minimized = ToggleRow("Start in the tray", "Don't open the window when Wyrm starts with Windows.")
        self.minimized.toggled.connect(lambda v: self._set("start_minimized", v))
        gen.add(self.minimized)
        self.auto = ToggleRow("Auto-switch profiles by app", "Follow the foreground window.")
        self.auto.toggled.connect(lambda v: (ctx.manager.set_auto(v), ctx.config_changed.emit()))
        gen.add(self.auto)
        self.osd = ToggleRow("Show a toast when the profile changes", "A small on-screen badge with the profile name.")
        self.osd.toggled.connect(lambda v: self._set("osd", v))
        gen.add(self.osd)
        self.lay.addWidget(gen)

        look = Card("Accent", "Pick Wyrm's colour.")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.accents = {}
        for key, (a, b, name) in ACCENTS.items():
            q = QColor(a)
            sw = ColorSwatch((q.red(), q.green(), q.blue()), 34, editable=False)
            sw.setCheckable(True)
            sw.setToolTip(name)
            sw.clicked.connect(lambda _=False, k=key: self._accent(k))
            self.accents[key] = sw
            row.addWidget(sw)
        row.addStretch(1)
        look.add(row)
        self.lay.addWidget(look)

        adv = Card("Mouse writes")
        self.experimental = ToggleRow(
            "Experimental writes",
            "Lets Wyrm change settings whose encoding hasn't been confirmed on the M811 PRO yet: polling rate, "
            "disabling DPI stages, and the beta lighting effects. If one is wrong, the setting looks or feels off "
            "until you change it back. Wyrm never sends firmware or bootloader commands.")
        self.experimental.toggled.connect(lambda v: self._set("experimental", v))
        adv.add(self.experimental)
        self.dry = ToggleRow("Dry run", "Log what Wyrm would write, but don't send anything to the mouse.")
        self.dry.toggled.connect(lambda v: self._set("dry_run", v))
        adv.add(self.dry)
        snap = button("Save a snapshot now", None, "folder")
        snap.clicked.connect(self._snapshot)
        restore = button("Restore original settings", "Danger")
        restore.setToolTip("Writes back the settings Wyrm saved the first time it saw your mouse")
        restore.clicked.connect(self._restore)
        adv.add(hrow(snap, restore, None))
        self.lay.addWidget(adv)

        about = Card("About")
        about.add(label(f"Wyrm {__version__}. An open-source replacement for the Redragon M811 PRO software.",
                        wrap=True))
        about.add(label("Wyrm never connects to the internet: no telemetry, no update checks, no accounts. "
                        "Everything lives in your user folder.", "Muted", wrap=True))
        about.add(label("Not affiliated with or endorsed by Redragon.", "Dim"))
        opn = button("Open data folder", "Ghost", "folder")
        opn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))
        logs = button("Open log", "Ghost")
        logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(sub("logs") / "wyrm.log"))))
        about.add(hrow(opn, logs, None))
        self.lay.addWidget(about)
        self.lay.addStretch(1)
        ctx.config_changed.connect(lambda: self.isVisible() and self.refresh())

    def refresh(self):
        cfg = self.ctx.store.config
        self.autostart.setChecked(winapi.autostart_enabled())
        self.minimized.setChecked(cfg.start_minimized)
        self.auto.setChecked(cfg.auto_switch)
        self.osd.setChecked(cfg.osd)
        self.experimental.setChecked(cfg.experimental)
        self.dry.setChecked(cfg.dry_run)
        for k, sw in self.accents.items():
            sw.setChecked(k == cfg.accent)
            sw.update()

    def _set(self, key, v):
        setattr(self.ctx.store.config, key, v)
        self.ctx.save_config()
        if key in ("experimental", "dry_run"):
            self.ctx.manager.apply_active()

    def _autostart(self, v):
        try:
            winapi.set_autostart(v)
        except OSError as e:
            QMessageBox.warning(self, "Start with Windows", f"Couldn't change the startup entry: {e}")
        self.refresh()

    def _accent(self, k):
        self._set("accent", k)
        self.window().apply_theme()

    def _snapshot(self):
        st = self.ctx.state
        if not st:
            QMessageBox.information(self, "Snapshot", "The mouse isn't connected.")
            return
        from datetime import datetime
        stem = sub("snapshots") / f"manual_{datetime.now():%Y%m%d-%H%M%S}"
        Path(f"{stem}.settings.bin").write_bytes(st["raw_settings"])
        Path(f"{stem}.buttons.bin").write_bytes(st["raw_buttons"])
        self.ctx.toast.emit("Snapshot saved", "ok")

    def _restore(self):
        snaps = sorted(sub("snapshots").glob("factory_*.settings.bin"))
        if not snaps:
            QMessageBox.information(self, "Restore", "No original snapshot yet. Connect the mouse first.")
            return
        s = snaps[0]
        b = Path(str(s).replace(".settings.bin", ".buttons.bin"))
        if QMessageBox.question(
                self, "Restore original settings",
                "Write back the settings your mouse had when Wyrm first saw it?\n\n"
                "Tip: switch auto-switch off first, or Wyrm will re-apply your profile on the next switch.") \
                != QMessageBox.Yes:
            return
        self.ctx.device.restore(s.read_bytes(), b.read_bytes())


__all__ = ["SettingsPage", "os"]
