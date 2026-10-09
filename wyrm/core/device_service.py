"""All mouse I/O happens on one worker thread.

Write sequence for every apply:
  link check -> fresh read -> patch known bytes -> skip if unchanged ->
  write macros, settings, buttons -> read back -> compare.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot

from ..hid import protocol as P
from ..hid.codec import buttons as BC
from ..hid.codec import settings as SC
from ..hid.codec.layout import LayoutMismatch
from ..hid.codec.macro import encode_events
from ..hid.enumerate import find_device
from ..hid.transport import HidTransport
from .model import ButtonAction, Profile

log = logging.getLogger(__name__)

POLL_MS = 2500
BATTERY_EVERY_S = 30


class DeviceWorker(QObject):
    status = Signal(dict)
    device_state = Signal(dict)
    applied = Signal(str, dict)
    apply_failed = Signal(str, str)

    def __init__(self, snapshot_dir: Path):
        super().__init__()
        self.snapshot_dir = snapshot_dir
        self.t: HidTransport | None = None
        self.fw = ""
        self.link = False
        self.battery: P.Battery | None = None
        self._battery_at = 0.0
        self._pending: tuple | None = None
        self._timer: QTimer | None = None

    # --- lifecycle ------------------------------------------------------
    @Slot()
    def start(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.poll)
        self._timer.start()
        self.poll()

    @Slot()
    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
        self._disconnect(emit=False)

    def _emit_status(self, error: str = "") -> None:
        b = self.battery or P.Battery()
        self.status.emit({
            "connected": self.t is not None,
            "wireless": bool(self.t and self.t.paths.wireless),
            "fw": self.fw, "link": self.link,
            "battery": b.level, "charging": b.charging, "full": b.full,
            "pending": self._pending is not None, "error": error,
        })

    def _disconnect(self, emit: bool = True, error: str = "") -> None:
        if self.t:
            self.t.close()
        self.t = None
        self.link = False
        self.battery = None
        if emit:
            self._emit_status(error)

    def _connect(self) -> bool:
        paths = find_device()
        if not paths:
            return False
        self.t = HidTransport(paths)
        self.fw = P.identify(self.t)
        log.info("connected: fw=%s wireless=%s", self.fw, paths.wireless)
        return True

    # --- polling ----------------------------------------------------------
    @Slot()
    def poll(self) -> None:
        try:
            if self.t is None:
                if not self._connect():
                    self._emit_status()
                    return
                self.link = P.link_ok(self.t)
                self.battery = P.battery(self.t)
                self._battery_at = time.monotonic()
                if self.link:
                    self._read_and_emit(snapshot=True)
                self._emit_status()
            else:
                was = self.link
                self.link = P.link_ok(self.t)
                if self.link and (not was or time.monotonic() - self._battery_at > BATTERY_EVERY_S):
                    self.battery = P.battery(self.t)
                    self._battery_at = time.monotonic()
                    if not was:
                        self._read_and_emit(snapshot=True)
                self._emit_status()
            if self.link and self._pending:
                pending, self._pending = self._pending, None
                self._apply(*pending)
        except OSError as e:
            log.warning("device lost: %s", e)
            self._disconnect(error="")
        except Exception as e:  # protocol surprises: keep running, report
            log.exception("poll failed")
            self._emit_status(str(e))

    def _read_and_emit(self, snapshot: bool = False) -> None:
        s = P.read_settings(self.t)
        b = P.read_buttons(self.t)
        if snapshot:
            self._snapshot("factory", s, b, overwrite=False)
        try:
            decoded = SC.decode(s)
        except LayoutMismatch as e:
            self.device_state.emit({"error": str(e)})
            return
        self.device_state.emit({"settings": decoded, "buttons": BC.decode_block(b),
                                "raw_settings": s, "raw_buttons": b, "fw": self.fw})

    def _snapshot(self, name: str, s: bytes, b: bytes, overwrite: bool = True) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        stem = self.snapshot_dir / f"{name}_{self.fw or 'unknown'}"
        sp, bp = Path(f"{stem}.settings.bin"), Path(f"{stem}.buttons.bin")
        if overwrite or not sp.exists():
            sp.write_bytes(s)
            bp.write_bytes(b)
            log.info("saved %s snapshot", name)

    # --- apply ------------------------------------------------------------
    @Slot(object, object, object)
    def apply(self, profile: Profile, macros: dict, opts: dict) -> None:
        if self.t is None or not self.link:
            self._pending = (profile, macros, opts)
            self._emit_status()
            return
        try:
            self._apply(profile, macros, opts)
        except OSError as e:
            log.warning("device lost during apply: %s", e)
            self._pending = (profile, macros, opts)
            self._disconnect()

    def _apply(self, profile: Profile, macros: dict, opts: dict) -> None:
        t = self.t
        try:
            if not P.link_ok(t):
                self._pending = (profile, macros, opts)
                self.link = False
                self._emit_status()
                return
            s0, b0 = P.read_settings(t), P.read_buttons(t)
            s1 = SC.encode(s0, profile, allow=opts.get("allow"))
            b1, macro_writes = b0, []
            if profile.buttons:
                acts, idx = [], {}
                for i, a in enumerate(profile.buttons):
                    if a.kind == "macro":
                        m = macros.get(a.macro_id)
                        if m is None or not m.events:
                            acts.append(ButtonAction("disabled"))
                            continue
                        idx[i] = i + 1      # one device macro slot per button
                        macro_writes.append((i + 1, encode_events(m.events)))
                    acts.append(a)
                b1 = BC.encode_block(b0, acts, idx)
        except (LayoutMismatch, ValueError, P.ProtocolError) as e:
            log.warning("apply refused: %s", e)
            self.apply_failed.emit(profile.id, str(e))
            return

        info = {"settings": s1 != s0, "buttons": b1 != b0, "macros": 0,
                "dry_run": bool(opts.get("dry_run"))}
        if opts.get("dry_run"):
            log.info("dry run %s: settings diff %s, buttons diff %s", profile.name,
                     [i for i in range(len(s0)) if s0[i] != s1[i]],
                     [i for i in range(len(b0)) if b0[i] != b1[i]])
            self.applied.emit(profile.id, info)
            return

        for index, events in macro_writes:
            if P.read_macro(t, index) != events:
                P.write_macro(t, index, events)
                info["macros"] += 1
        need_s, need_b = info["settings"], info["buttons"]
        s2, b2 = s0, b0
        for _attempt in range(2):          # write, verify, retry once at most
            if need_s:
                P.write_settings(t, s1)
            if need_b:
                P.write_buttons(t, b1)
            if need_s or need_b:
                time.sleep(0.05)
            s2, b2 = P.read_settings(t), P.read_buttons(t)
            need_s, need_b = s2 != s1, b2 != b1
            if not (need_s or need_b):
                break
        else:
            self.apply_failed.emit(profile.id, "The mouse did not keep the new settings. "
                                               "Move it to wake it up and try again.")
            return
        if info["settings"] or info["buttons"] or info["macros"]:
            self._snapshot("last_good", s2, b2)
        log.info("applied %s: %s", profile.name, info)
        self.applied.emit(profile.id, info)
        self._read_and_emit()

    @Slot(bytes, bytes)
    def restore_blocks(self, settings: bytes, buttons: bytes) -> None:
        """Write raw blocks back (factory snapshot). Same identity checks as apply."""
        if self.t is None or not P.link_ok(self.t):
            self.apply_failed.emit("", "Mouse is not reachable. Move it and try again.")
            return
        try:
            from ..hid.codec.layout import check_block, load_layout
            check_block(settings, load_layout())
            P.write_settings(self.t, settings)
            P.write_buttons(self.t, buttons)
            ok = P.read_settings(self.t) == settings and P.read_buttons(self.t) == buttons
        except (OSError, ValueError, P.ProtocolError) as e:
            self.apply_failed.emit("", f"Restore failed: {e}")
            return
        self.applied.emit("", {"restored": ok})
        self._read_and_emit()

    @Slot()
    def refresh(self) -> None:
        if self.t is not None and self.link:
            try:
                self._read_and_emit()
            except OSError:
                self._disconnect()


class DeviceService(QObject):
    """Main-thread facade. Methods are safe to call from the UI."""
    _apply = Signal(object, object, object)
    _restore = Signal(bytes, bytes)
    _refresh = Signal()
    _stop = Signal()

    def __init__(self, snapshot_dir: Path, parent=None):
        super().__init__(parent)
        self.thread = QThread()
        self.thread.setObjectName("wyrm-device")
        self.worker = DeviceWorker(snapshot_dir)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self._apply.connect(self.worker.apply)
        self._restore.connect(self.worker.restore_blocks)
        self._refresh.connect(self.worker.refresh)
        self._stop.connect(self.worker.stop, Qt.BlockingQueuedConnection)
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

    def apply(self, profile: Profile, macros: dict, opts: dict) -> None:
        self._apply.emit(profile, macros, opts)

    def restore(self, settings: bytes, buttons: bytes) -> None:
        self._restore.emit(settings, buttons)

    def refresh(self) -> None:
        self._refresh.emit()
