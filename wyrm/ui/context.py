"""Shared state for the pages: which profile is being edited, device status."""
from __future__ import annotations

import copy

from PySide6.QtCore import QObject, Signal

from ..core.device_service import DeviceService
from ..core.model import ButtonAction, Profile
from ..core.profile_manager import ProfileManager
from ..core.store import Store

SLOTS = 16


class AppContext(QObject):
    editing_changed = Signal(object, object)   # Profile, source widget (or None)
    status_changed = Signal(dict)
    state_changed = Signal(dict)
    config_changed = Signal()
    toast = Signal(str, str)                   # text, kind ("ok" | "warn" | "bad" | "info")

    def __init__(self, store: Store, manager: ProfileManager, device: DeviceService, demo: bool = False):
        super().__init__()
        self.store = store
        self.manager = manager
        self.device = device
        self.demo = demo
        self.status: dict = {"connected": False}
        self.state: dict | None = None
        self.editing_id: str | None = None
        device.status.connect(self._on_status)
        device.device_state.connect(self._on_state)
        manager.active_changed.connect(self._on_active)
        manager.profiles_changed.connect(self._on_profiles)

    # --- device mirror ------------------------------------------------------
    def _on_status(self, s: dict):
        self.status = s
        self.status_changed.emit(s)

    def _on_state(self, d: dict):
        if "error" not in d:
            self.state = d
        self.state_changed.emit(d)

    # --- editing ----------------------------------------------------------------
    def editing(self) -> Profile | None:
        return self.manager.get(self.editing_id) or self.manager.active()

    def set_editing(self, pid: str):
        self.editing_id = pid
        self.editing_changed.emit(self.editing(), None)

    def _on_active(self, p: Profile, reason: str):
        prev_active_was_editing = self.editing_id in (None, getattr(self, "_last_active", None))
        self._last_active = p.id
        if prev_active_was_editing:
            self.editing_id = p.id
            self.editing_changed.emit(p, None)

    def _on_profiles(self):
        if self.editing_id and not self.manager.get(self.editing_id):
            self.editing_id = None
            self.editing_changed.emit(self.editing(), None)

    def commit(self, p: Profile, source=None, apply: bool = True):
        self.manager.update_profile(p, apply)
        self.editing_changed.emit(p, source)

    def edit(self, fn, source=None):
        p = self.editing()
        if p is None:
            return
        p = copy.deepcopy(p)
        fn(p)
        self.commit(p, source)

    # --- helpers ----------------------------------------------------------------
    def device_buttons(self) -> list[ButtonAction]:
        if self.state and "buttons" in self.state:
            return copy.deepcopy(self.state["buttons"][:SLOTS])
        return [ButtonAction("disabled") for _ in range(SLOTS)]

    def effective_buttons(self, p: Profile) -> list[ButtonAction]:
        base = self.device_buttons()
        acts = copy.deepcopy(p.buttons[:SLOTS]) if p.buttons else base
        return acts + base[len(acts):]

    def is_active(self, p: Profile) -> bool:
        a = self.manager.active()
        return bool(a and a.id == p.id)

    def allow(self) -> set[str]:
        return self.store.config.allow()

    def save_config(self):
        self.store.save_config()
        self.config_changed.emit()
