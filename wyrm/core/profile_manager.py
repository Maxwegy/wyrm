"""Which profile is active, and why. Owns auto-switching and debounced applies."""
from __future__ import annotations

import copy
import logging
import os
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from .device_service import DeviceService
from .model import Profile
from .rules import resolve
from .store import Store

log = logging.getLogger(__name__)

APPLY_DEBOUNCE_MS = 450
AUTO_DEBOUNCE_MS = 250
NEUTRAL = {("explorer.exe", ""), ("explorer.exe", "Program Manager")}


class ProfileManager(QObject):
    active_changed = Signal(object, str)     # Profile, reason
    profiles_changed = Signal()
    foreground_changed = Signal(str, str)    # exe, title
    write_blocked = Signal(str)              # message for the UI

    def __init__(self, store: Store, device: DeviceService, parent=None):
        super().__init__(parent)
        self.store = store
        self.device = device
        self.confirm_first_write: Callable[[], bool] | None = None
        self._own_pid = os.getpid()
        self._last_exe = ""
        self._last_title = ""
        self._hold_exe: str | None = None
        self._apply_timer = QTimer(self, singleShot=True, interval=APPLY_DEBOUNCE_MS)
        self._apply_timer.timeout.connect(self.apply_active)
        self._auto_timer = QTimer(self, singleShot=True, interval=AUTO_DEBOUNCE_MS)
        self._auto_timer.timeout.connect(self._resolve_foreground)

    # --- queries ----------------------------------------------------------
    def profiles(self) -> list[Profile]:
        return self.store.ordered()

    def get(self, pid: str | None) -> Profile | None:
        return self.store.profiles.get(pid) if pid else None

    def active(self) -> Profile | None:
        cfg = self.store.config
        return self.get(cfg.active_profile_id) or (self.profiles()[0] if self.profiles() else None)

    def default(self) -> Profile | None:
        return self.get(self.store.config.default_profile_id) or (self.profiles()[0] if self.profiles() else None)

    # --- switching -------------------------------------------------------
    def switch(self, pid: str, reason: str = "manual") -> None:
        p = self.get(pid)
        if not p:
            return
        if reason in ("manual", "hotkey"):
            self._hold_exe = self._last_exe or None
        changed = self.store.config.active_profile_id != pid
        self.store.config.active_profile_id = pid
        self.store.save_config()
        if changed:
            log.info("profile -> %s (%s)", p.name, reason)
            self.active_changed.emit(p, reason)
        self.apply_active()

    def cycle(self, delta: int, reason: str = "hotkey") -> None:
        ps = self.profiles()
        if len(ps) < 2:
            return
        cur = self.active()
        i = next((n for n, p in enumerate(ps) if cur and p.id == cur.id), 0)
        self.switch(ps[(i + delta) % len(ps)].id, reason)

    def set_auto(self, enabled: bool) -> None:
        self.store.config.auto_switch = enabled
        self.store.save_config()
        self._hold_exe = None
        if enabled:
            self._resolve_foreground()

    # --- auto switch -----------------------------------------------------
    def on_foreground(self, exe: str, title: str, path: str, pid: int) -> None:
        if pid == self._own_pid or not exe or (exe.lower(), title) in NEUTRAL:
            return
        if exe != self._last_exe or title != self._last_title:
            self._last_exe, self._last_title = exe, title
            self.foreground_changed.emit(exe, title)
            self._auto_timer.start()

    def _resolve_foreground(self) -> None:
        if not self.store.config.auto_switch or not self._last_exe:
            return
        if self._hold_exe is not None:
            if self._last_exe == self._hold_exe:
                return
            self._hold_exe = None
        target = resolve(self.profiles(), self._last_exe, self._last_title) or self.default()
        if target and target.id != self.store.config.active_profile_id:
            self.switch(target.id, "auto")

    def matched_profile(self) -> Profile | None:
        return resolve(self.profiles(), self._last_exe, self._last_title)

    # --- editing ---------------------------------------------------------
    def update_profile(self, p: Profile, apply: bool = True) -> None:
        self.store.save_profile(p)
        self.profiles_changed.emit()
        if apply and p.id == self.store.config.active_profile_id:
            self._apply_timer.start()

    def create(self, name: str, base: Profile | None = None) -> Profile:
        p = copy.deepcopy(base) if base else Profile()
        p.id = Profile().id
        p.name = name
        p.rules = [] if base else p.rules
        self.store.save_profile(p)
        self.profiles_changed.emit()
        return p

    def delete(self, pid: str) -> None:
        was_active = pid == self.store.config.active_profile_id
        self.store.delete_profile(pid)
        self.profiles_changed.emit()
        if was_active:
            self.switch(self.store.config.active_profile_id, "manual")

    def set_default(self, pid: str) -> None:
        self.store.config.default_profile_id = pid
        self.store.save_config()
        self.profiles_changed.emit()

    def move(self, pid: str, delta: int) -> None:
        self.store.move_profile(pid, delta)
        self.profiles_changed.emit()

    # --- device ----------------------------------------------------------
    def apply_active(self) -> None:
        self._apply_timer.stop()
        p = self.active()
        if not p:
            return
        cfg = self.store.config
        if not cfg.first_write_ok and not cfg.dry_run:
            ok = self.confirm_first_write() if self.confirm_first_write else False
            if not ok:
                self.write_blocked.emit("Writing to the mouse is paused until you allow it.")
                return
            cfg.first_write_ok = True
            self.store.save_config()
        self.device.apply(copy.deepcopy(p), dict(self.store.macros),
                          {"allow": cfg.allow(), "dry_run": cfg.dry_run})
