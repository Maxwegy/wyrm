"""All mouse I/O happens on one worker thread.

Every poll: look for mice that were plugged in or pulled out, check each one (awake? battery?),
read it when it connects or wakes, and run any write that was waiting for it. The drivers do the
byte work; this hub only sequences it, keeps snapshots and reports back to the UI.
"""
from __future__ import annotations

import copy
import logging
import shutil
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot

from ..drivers import default_registry, demo_registry
from ..drivers.base import ApplyRefused, DeviceInfo, DeviceSession, DeviceStatus, NotReady, slug
from .model import M811_KEY

log = logging.getLogger(__name__)

POLL_MS = 2500


def model_dir(root: Path, key: str) -> Path:
    return root / slug(key)


def _migrate_snapshots(root: Path) -> None:
    """v0.1 kept the M811 PRO's snapshots at the top of the folder."""
    old = [p for p in root.glob("*.bin") if p.is_file()]
    if old:
        dst = model_dir(root, M811_KEY)
        dst.mkdir(parents=True, exist_ok=True)
        for p in old:
            if not (dst / p.name).exists():
                shutil.move(str(p), dst / p.name)


def read_snapshot(root: Path, key: str, name: str = "factory") -> dict[str, bytes]:
    """The oldest snapshot called `name` for this model, as {suffix: bytes}."""
    files = sorted(model_dir(root, key).glob(f"{name}_*.*"))
    if not files:
        return {}
    stem = files[0].name.split(".", 1)[0]
    return {p.name.split(".", 1)[1]: p.read_bytes() for p in files if p.name.split(".", 1)[0] == stem}


def write_snapshot(root: Path, key: str, name: str, fw: str, snapshot: dict[str, bytes],
                   overwrite: bool = True) -> None:
    d = model_dir(root, key)
    d.mkdir(parents=True, exist_ok=True)
    files = {d / f"{name}_{fw or 'unknown'}.{suffix}": data for suffix, data in snapshot.items()}
    if files and (overwrite or not any(p.exists() for p in files)):
        for p, data in files.items():
            p.write_bytes(data)
        log.info("saved %s snapshot of %s", name, key)


class DeviceWorker(QObject):
    devices_changed = Signal(list)         # [DeviceInfo] of the connected mice
    status = Signal(str, dict)             # uid, {link, battery, charging, full, note, pending, error}
    device_state = Signal(str, dict)       # uid, {settings, snapshot, fw, reason[, seed]} or {error, reason}
    applied = Signal(str, str, dict)       # uid, profile id, {changed, skipped, dry_run[, restored]}
    apply_failed = Signal(str, str, str)   # uid, profile id, message

    def __init__(self, snapshot_dir: Path, demo: bool = False, registry=None):
        super().__init__()
        self.snapshot_dir = snapshot_dir
        self.demo = demo
        self.registry = registry
        self._sessions: dict[str, DeviceSession] = {}
        self._infos: list[dict] = []
        self._link: dict[str, bool] = {}
        self._status: dict[str, dict] = {}
        self._pending: dict[str, tuple] = {}    # uid -> (settings, macros, opts, profile id)
        self._timer: QTimer | None = None
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        _migrate_snapshots(snapshot_dir)

    # --- lifecycle ------------------------------------------------------
    @Slot()
    def start(self) -> None:
        if self.registry is None:
            self.registry = demo_registry() if self.demo else default_registry()
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.poll)
        self._timer.start()
        self.poll()

    @Slot()
    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
        for s in self._sessions.values():
            s.shutdown()
        if self.registry:
            self.registry.close()
        self._sessions.clear()

    # --- polling ----------------------------------------------------------
    @Slot()
    def poll(self) -> None:
        try:
            self.registry.scan()
            self.registry.refresh()
        except Exception:
            log.exception("device scan failed")
        current = {s.info.uid: s for s in self.registry.sessions()}
        polled: dict[str, DeviceStatus | None] = {}
        errors: dict[str, str] = {}
        for uid, s in current.items():
            try:
                polled[uid] = s.poll()
            except OSError as e:
                log.warning("lost %s: %s", uid, e)
                self.registry.drop(s)
                self._link.pop(uid, None)
            except Exception as e:   # protocol surprises: keep the mouse listed, report
                log.exception("poll %s failed", uid)
                polled[uid], errors[uid] = None, str(e)
        for uid in [u for u in self._sessions if u not in polled]:
            self._link.pop(uid, None)
            self._status.pop(uid, None)
        self._sessions = {uid: current[uid] for uid in polled}
        self._emit_devices()
        for uid, st in polled.items():
            if st is None:
                self._emit_status(uid, error=errors[uid])
                continue
            was = self._link.get(uid, False)
            self._link[uid] = st.link
            self._emit_status(uid, st)
            try:
                if st.link and not was:
                    self._read(uid, "connect")
                if st.link and uid in self._pending:
                    self._run(uid, *self._pending.pop(uid))
            except OSError as e:
                log.warning("lost %s: %s", uid, e)
                self._drop(uid)

    def _drop(self, uid: str) -> None:
        """An I/O error: close the connection so the next scan reopens it (and reads it again)."""
        self._link.pop(uid, None)
        if uid in self._sessions:
            self.registry.drop(self._sessions[uid])

    def _emit_devices(self) -> None:
        infos = [copy.deepcopy(s.info) for s in self._sessions.values()]
        flat = [asdict(i) for i in infos]
        if flat != self._infos:
            self._infos = flat
            self.devices_changed.emit(infos)

    def _emit_status(self, uid: str, st: DeviceStatus | None = None, error: str = "") -> None:
        d = self._status.get(uid, {})
        if st is not None:
            d = {"link": st.link, "battery": st.battery, "charging": st.charging, "full": st.full, "note": st.note}
        d = dict(d, pending=uid in self._pending, error=error)
        self._status[uid] = d
        self.status.emit(uid, d)

    def _read(self, uid: str, reason: str) -> None:
        s = self._sessions[uid]
        try:
            state = s.read_state()
        except (ValueError, RuntimeError) as e:     # a block that doesn't match the model: no writes
            log.warning("unexpected data from %s: %s", uid, e)
            self.device_state.emit(uid, {"error": str(e), "reason": reason})
            return
        if state is None:
            return
        if reason == "connect":
            write_snapshot(self.snapshot_dir, s.info.key, "factory", state.fw, state.snapshot, overwrite=False)
        d = {"settings": state.settings, "snapshot": state.snapshot, "fw": state.fw, "reason": reason}
        if reason == "connect" and s.info.caps.configurable:
            d["seed"] = s.seed_settings(state)
        self.device_state.emit(uid, d)

    # --- apply ------------------------------------------------------------
    @Slot(str, object, object, object, str)
    def apply(self, uid: str, settings, macros: dict, opts: dict, profile_id: str = "") -> None:
        if uid not in self._sessions or not self._link.get(uid):
            self._pending[uid] = (settings, macros, opts, profile_id)
            if uid in self._sessions:
                self._emit_status(uid)
            return
        self._run(uid, settings, macros, opts, profile_id)

    def _run(self, uid: str, settings, macros: dict, opts: dict, profile_id: str) -> None:
        s = self._sessions[uid]
        try:
            info = s.apply(settings, macros, opts)
        except NotReady:
            self._pending[uid] = (settings, macros, opts, profile_id)
            self._link[uid] = False
            self._emit_status(uid)
            return
        except ApplyRefused as e:
            log.warning("apply to %s refused: %s", uid, e)
            self.apply_failed.emit(uid, profile_id, str(e))
            return
        except OSError as e:
            log.warning("lost %s during apply: %s", uid, e)
            self._pending[uid] = (settings, macros, opts, profile_id)
            self._drop(uid)
            return
        log.info("applied %s to %s: %s", profile_id[:8], s.info.name, info)
        self.applied.emit(uid, profile_id, info)
        if info.get("changed") and not info.get("dry_run"):
            try:
                state = s.read_state()
            except OSError:
                self._drop(uid)
                return
            if state:
                write_snapshot(self.snapshot_dir, s.info.key, "last_good", state.fw, state.snapshot)
                self.device_state.emit(uid, {"settings": state.settings, "snapshot": state.snapshot,
                                             "fw": state.fw, "reason": "apply"})
        self._emit_status(uid)

    @Slot(str)
    def restore(self, uid: str) -> None:
        """Write back the snapshot taken the first time Wyrm saw this mouse."""
        s = self._sessions.get(uid)
        if s is None or not self._link.get(uid):
            self.apply_failed.emit(uid, "", "The mouse is not reachable. Move it and try again.")
            return
        snap = read_snapshot(self.snapshot_dir, s.info.key)
        if not snap:
            self.apply_failed.emit(uid, "", f"There's no original snapshot of the {s.info.name} yet.")
            return
        try:
            ok = s.restore(snap)
        except NotReady:
            self.apply_failed.emit(uid, "", "The mouse is asleep. Move it and try again.")
            return
        except ApplyRefused as e:
            self.apply_failed.emit(uid, "", str(e))
            return
        except OSError as e:
            self.apply_failed.emit(uid, "", f"Restore failed: {e}")
            self._drop(uid)
            return
        self.applied.emit(uid, "", {"restored": ok, "changed": [], "skipped": [], "dry_run": False})
        try:
            self._read(uid, "restore")
        except OSError:
            self._drop(uid)

    @Slot(str)
    def refresh(self, uid: str = "") -> None:
        for u in ([uid] if uid else list(self._sessions)):
            if u in self._sessions and self._link.get(u):
                try:
                    self._read(u, "refresh")
                except OSError:
                    self._drop(u)


class DeviceService(QObject):
    """Main-thread facade. Methods are safe to call from the UI."""
    _apply = Signal(str, object, object, object, str)
    _restore = Signal(str)
    _refresh = Signal(str)
    _stop = Signal()

    def __init__(self, snapshot_dir: Path, demo: bool = False, parent=None, registry=None):
        super().__init__(parent)
        self.demo = demo
        self.snapshot_dir = snapshot_dir
        self.thread = QThread()
        self.thread.setObjectName("wyrm-device")
        self.worker = DeviceWorker(snapshot_dir, demo, registry)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self._apply.connect(self.worker.apply)
        self._restore.connect(self.worker.restore)
        self._refresh.connect(self.worker.refresh)
        self._stop.connect(self.worker.stop, Qt.BlockingQueuedConnection)
        self.devices_changed = self.worker.devices_changed
        self.status = self.worker.status
        self.device_state = self.worker.device_state
        self.applied = self.worker.applied
        self.apply_failed = self.worker.apply_failed

    def start(self) -> None:
        self.thread.start()

    def shutdown(self) -> None:
        if self.thread.isRunning():
            self._stop.emit()
            self.thread.quit()
            self.thread.wait(3000)

    def apply(self, uid: str, settings, macros: dict, opts: dict, profile_id: str = "") -> None:
        self._apply.emit(uid, settings, macros, opts, profile_id)

    def restore(self, uid: str) -> None:
        self._restore.emit(uid)

    def refresh(self, uid: str = "") -> None:
        self._refresh.emit(uid)


__all__ = ["DeviceService", "DeviceWorker", "DeviceInfo", "read_snapshot", "write_snapshot", "model_dir"]
