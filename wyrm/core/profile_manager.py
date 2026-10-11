"""Which profile is active, and why. Owns auto-switching and debounced applies to every mouse."""
from __future__ import annotations

import copy
import logging
import os
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from ..drivers.base import DeviceInfo
from .model import DeviceSettings, Profile, effective_settings
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

    def __init__(self, store: Store, device, parent=None):
        super().__init__(parent)
        self.store = store
        self.device = device
        self.confirm_first_write: Callable[[DeviceInfo], bool] | None = None
        self.devices: dict[str, DeviceInfo] = {}     # connected mice, by uid
        self._own_pid = os.getpid()
        self._last_exe = ""
        self._last_title = ""
        self._hold_exe: str | None = None
        self._apply_timer = QTimer(self, singleShot=True, interval=APPLY_DEBOUNCE_MS)
        self._apply_timer.timeout.connect(lambda: self.apply_active(user=True))
        self._declined: set[str] = set()             # models the user said "Not now" to this session
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

    def effective(self, p: Profile | None, key: str) -> DeviceSettings | None:
        return effective_settings(p, self.default(), key)

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
        self.apply_active(user=reason in ("manual", "hotkey"))

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
        default = self.default()
        # The active profile, or the Default profile it may follow for some mice.
        if apply and p.id in (self.store.config.active_profile_id, default.id if default else None):
            self._apply_timer.start()

    def create(self, name: str, base: Profile | None = None) -> Profile:
        """A new profile follows the Default profile for every mouse until it's changed;
        with `base` it starts as a copy instead."""
        p = copy.deepcopy(base) if base else Profile()
        p.id = Profile().id
        p.name = name
        p.rules = []
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

    # --- mice --------------------------------------------------------------
    def set_devices(self, infos: list[DeviceInfo]) -> None:
        self.devices = {i.uid: i for i in infos}

    def on_device_state(self, uid: str, d: dict) -> None:
        """A mouse was read. The first time its model connects, its own settings seed the Default
        profile; every time it (re)connects it gets the active profile. Connect this bound method (not
        a lambda) so Qt runs it on the main thread, after set_devices."""
        info = self.devices.get(uid)
        if info is None or "error" in d or d.get("reason") != "connect":
            return
        if "seed" in d:
            self.seed(info, d["seed"])
        self.apply_active(only_uid=uid)

    def seed(self, info: DeviceInfo, settings: DeviceSettings) -> bool:
        """The first time Wyrm sees a mouse model, its own setup becomes the Default profile's."""
        cfg = self.store.config
        if info.key in cfg.seeded_models or not info.caps.configurable:
            return False
        d = self.default()
        if d is not None and info.key not in d.devices:
            d.devices[info.key] = copy.deepcopy(settings)
            self.store.save_profile(d)
            log.info("%s now holds the %s's own settings", d.name, info.name)
        cfg.seeded_models.append(info.key)
        self.store.save_config()
        self.profiles_changed.emit()
        return True

    def apply_active(self, user: bool = False, only_uid: str | None = None) -> None:
        """Write the active profile to every connected mouse it covers. `user` marks applies the
        user caused (edits, picks): only those may ask for write permission again after "Not now"."""
        self._apply_timer.stop()
        p = self.active()
        if not p:
            return
        cfg = self.store.config
        for uid, info in list(self.devices.items()):
            if (only_uid and uid != only_uid) or not info.caps.configurable:
                continue
            s = self.effective(p, info.key)
            if s is None or not self._may_write(info, user):
                continue
            self.device.apply(uid, copy.deepcopy(s), dict(self.store.macros),
                              {"allow": cfg.allow(info.key), "experimental": cfg.experimental,
                               "dry_run": cfg.dry_run}, p.id)

    def _may_write(self, info: DeviceInfo, user: bool) -> bool:
        cfg = self.store.config
        if cfg.dry_run or info.demo or info.key in cfg.write_ok_models:
            return True
        if info.key in self._declined and not user:
            return False
        ok = self.confirm_first_write(info) if self.confirm_first_write else False
        if not ok:
            self._declined.add(info.key)
            self.write_blocked.emit(f"Writing to the {info.name} is paused until you allow it.")
            return False
        self._declined.discard(info.key)
        cfg.write_ok_models.append(info.key)
        self.store.save_config()
        return True
