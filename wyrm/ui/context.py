"""Shared state for the pages: the mice, which one is being edited, which profile is being edited."""
from __future__ import annotations

import copy
import time

from PySide6.QtCore import QObject, QTimer, Signal

from ..core import winapi
from ..core.device_service import DeviceService, write_snapshot
from ..core.model import ButtonAction, DeviceSettings, Profile
from ..core.profile_manager import ProfileManager
from ..core.store import Store
from ..drivers.base import Capabilities, DeviceInfo

IN_USE_S = 1.5              # "In use" stays this long after the last movement
CONFLICT_CHECK_MS = 10_000
SUPPORT_ORDER = {"full": 0, "basic": 1, "detected": 2}


class AppContext(QObject):
    editing_changed = Signal(object, object)   # Profile, source widget (or None)
    devices_changed = Signal()                 # a mouse was plugged in, pulled out or identified
    status_changed = Signal(str)               # uid
    state_changed = Signal(str)                # uid
    current_changed = Signal()                 # a different mouse is being edited
    in_use_changed = Signal()
    conflicts_changed = Signal()
    config_changed = Signal()
    toast = Signal(str, str)                   # text, kind ("ok" | "warn" | "bad" | "info")

    def __init__(self, store: Store, manager: ProfileManager, device: DeviceService, demo: bool = False):
        super().__init__()
        self.store = store
        self.manager = manager
        self.device = device
        self.demo = demo
        self.devices: dict[str, DeviceInfo] = {}   # connected mice, by uid
        self.status: dict[str, dict] = {}
        self.states: dict[str, dict] = {}
        self.editing_id: str | None = None
        self.in_use: dict[str, float] = {}         # uid -> last movement
        self.running: set[str] = set()             # exe names that conflict with a connected mouse
        device.devices_changed.connect(self._on_devices)
        device.status.connect(self._on_status)
        device.device_state.connect(self._on_state)
        manager.active_changed.connect(self._on_active)
        manager.profiles_changed.connect(self._on_profiles)
        self._decay = QTimer(self, interval=300)
        self._decay.timeout.connect(self._expire_in_use)
        self._procs = QTimer(self, interval=CONFLICT_CHECK_MS)
        self._procs.timeout.connect(self._check_conflicts)
        self._procs.start()

    # --- mice ----------------------------------------------------------------------
    def _on_devices(self, infos: list[DeviceInfo]):
        before = self.current()
        self.devices = {i.uid: i for i in infos}
        for d in (self.status, self.states, self.in_use):
            for uid in [u for u in d if u not in self.devices]:
                del d[uid]
        for i in infos:
            self.store.remember(i)
        self._check_conflicts()
        self.devices_changed.emit()
        after = self.current()
        if (before and before.key) != (after and after.key):
            self.current_changed.emit()

    def _on_status(self, uid: str, s: dict):
        self.status[uid] = s
        self.status_changed.emit(uid)

    def _on_state(self, uid: str, d: dict):
        if "error" in d:
            info = self.devices.get(uid)
            self.toast.emit(f"Unexpected data from the {info.name if info else 'mouse'}, writes paused: "
                            f"{d['error']}", "bad")
        else:
            self.states[uid] = d
        self.state_changed.emit(uid)

    def mice(self) -> list[DeviceInfo]:
        """Connected mice, the configurable ones first."""
        return sorted(self.devices.values(), key=lambda i: (SUPPORT_ORDER.get(i.support, 3), i.demo, i.name.lower()))

    def offline_mice(self) -> list[DeviceInfo]:
        """Mice Wyrm has seen before that aren't plugged in now."""
        here = {i.key for i in self.devices.values()}
        return [i for i in (self.store.known_info(k) for k in self.store.known if k not in here) if i]

    def editable_mice(self) -> list[DeviceInfo]:
        out, keys = [], set()
        for i in self.mice() + self.offline_mice():
            if i.caps.configurable and i.key not in keys:
                keys.add(i.key)
                out.append(i)
        return out

    def current(self) -> DeviceInfo | None:
        """The mouse the editing pages show."""
        mice = self.editable_mice()
        key = self.store.config.current_device
        return next((i for i in mice if i.key == key), mice[0] if mice else None)

    def set_current(self, key: str):
        if key != self.store.config.current_device:
            self.store.config.current_device = key
            self.store.save_config()
            self.current_changed.emit()

    def caps(self) -> Capabilities:
        cur = self.current()
        return cur.caps if cur else Capabilities()

    def status_of(self, info: DeviceInfo | None) -> dict:
        return self.status.get(info.uid, {}) if info and info.uid else {}

    def connected(self, info: DeviceInfo | None) -> bool:
        return bool(info and info.uid in self.devices)

    def device_state(self, info: DeviceInfo | None = None) -> DeviceSettings | None:
        """What's on the mouse right now, as last read."""
        info = info or self.current()
        st = self.states.get(info.uid) if info and info.uid else None
        return st.get("settings") if st else None

    # --- "in use" and conflicting apps ------------------------------------------------------
    def on_activity(self, vid: int, pid: int):
        now, new = time.monotonic(), False
        for uid, i in self.devices.items():
            if (i.vid, i.pid) == (vid, pid):
                new |= uid not in self.in_use
                self.in_use[uid] = now
        if new:
            self.in_use_changed.emit()
            self._decay.start()

    def _expire_in_use(self):
        now = time.monotonic()
        gone = [u for u, t in self.in_use.items() if now - t > IN_USE_S]
        for u in gone:
            del self.in_use[u]
        if gone:
            self.in_use_changed.emit()
        if not self.in_use:
            self._decay.stop()

    def _check_conflicts(self):
        watch = {exe for i in self.devices.values() for exe in i.conflicts}
        try:
            running = winapi.running_exes() & watch if watch else set()
        except OSError:
            return
        if running != self.running:
            self.running = running
            self.conflicts_changed.emit()

    def conflict_for(self, info: DeviceInfo) -> str:
        return next((app for exe, app in info.conflicts.items() if exe in self.running), "")

    # --- editing ----------------------------------------------------------------------
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

    def device_settings(self, p: Profile | None = None) -> tuple[DeviceSettings | None, str]:
        """What profile `p` does to the current mouse, and where that comes from: "own" (the profile
        sets it), "default" (it follows the default profile), "mouse" (nothing sets it yet, so this is
        what's on the mouse) or "" (nothing known)."""
        p, dev = p or self.editing(), self.current()
        if p is None or dev is None:
            return None, ""
        if dev.key in p.devices:
            return p.devices[dev.key], "own"
        d = self.manager.default()
        if d is not None and dev.key in d.devices:
            return d.devices[dev.key], "default"
        st = self.device_state(dev)
        return (st, "mouse") if st is not None else (None, "")

    def edit_device(self, fn, source=None):
        """Change the current mouse's settings in the edited profile. A profile that followed the
        default profile for this mouse gets its own copy first."""
        p, dev = self.editing(), self.current()
        s, _ = self.device_settings(p)
        if p is None or dev is None or s is None:
            return
        p, s = copy.deepcopy(p), copy.deepcopy(s)
        fn(s)
        p.devices[dev.key] = s
        self.commit(p, source)

    def follow_default(self):
        p, dev = self.editing(), self.current()
        if p and dev and dev.key in p.devices:
            p = copy.deepcopy(p)
            del p.devices[dev.key]
            self.commit(p)

    # --- helpers ----------------------------------------------------------------
    def device_buttons(self) -> list[ButtonAction]:
        n = len(self.caps().buttons)
        st = self.device_state()
        base = copy.deepcopy(st.buttons[:n]) if st and st.buttons else []
        return base + [ButtonAction("disabled") for _ in range(n - len(base))]

    def effective_buttons(self, s: DeviceSettings | None) -> list[ButtonAction]:
        base = self.device_buttons()
        acts = copy.deepcopy(s.buttons[:len(base)]) if s and s.buttons else base
        return acts + base[len(acts):]

    def is_active(self, p: Profile) -> bool:
        a = self.manager.active()
        return bool(a and a.id == p.id)

    def allow(self, info: DeviceInfo | None = None) -> set[str]:
        info = info or self.current()
        return self.store.config.allow(info.key) if info else set()

    def save_snapshot(self, info: DeviceInfo, name: str = "manual") -> bool:
        st = self.states.get(info.uid)
        if not st or not st.get("snapshot"):
            return False
        write_snapshot(self.device.snapshot_dir, info.key, f"{name}_{time.strftime('%Y%m%d-%H%M%S')}",
                       st.get("fw", ""), st["snapshot"])
        return True

    def save_config(self):
        self.store.save_config()
        self.config_changed.emit()
