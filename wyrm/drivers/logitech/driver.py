"""Logitech mice over HID++ 2.0: name, battery, DPI and polling rate.

A mouse plugged in directly answers at device index 0xFF. A receiver (Unifying, Lightspeed, Bolt)
holds up to six mice at indices 1-6, which come and go as they wake, sleep or get paired, so the
receiver is checked for new mice every few seconds.

Many G-series mice run from an on-board profile. In that mode their DPI and polling rate belong
to the profile, so Wyrm only reads them. With experimental writes on, Wyrm switches the mouse to
host mode, and switches it back when Wyrm quits.
"""
from __future__ import annotations

import json
import logging
import time

from ...core.model import DeviceSettings, DpiStage
from ..base import (ApplyRefused, Candidate, Capabilities, Connection, DeviceInfo, DeviceSession, DeviceState,
                    DeviceStatus, Driver, NotReady, entry_str, slug)
from ..generic import connection as path_connection
from .hidpp import (ADJUSTABLE_DPI, BATTERY_STATUS, DEVICE_NAME, DIRECT, HOST, ONBOARD, ONBOARD_PROFILES,
                    REPORT_RATE, UNIFIED_BATTERY, Hidpp, HidppError, HidppTransport, NoAnswer, parse_dpi_list,
                    rates_from_mask, read_battery, read_name)

log = logging.getLogger(__name__)

VID = 0x046D
RECEIVERS = {0xC52B, 0xC532, 0xC534, 0xC539, 0xC53A, 0xC53F, 0xC541, 0xC545, 0xC547, 0xC548}
MOUSE_TYPES = {3, 4, 5}          # 0x0005 device types: mouse, trackpad, trackball
CONFLICTS = {"lghub.exe": "Logitech G HUB", "lghub_agent.exe": "Logitech G HUB",
             "logioptionsplus.exe": "Logi Options+", "logioptionsplus_agent.exe": "Logi Options+"}
BATTERY_EVERY_S = 30
RESCAN_S = 5.0


def _hidpp_long(e: dict) -> bool:
    return (e["usage_page"], e["usage"]) == (0xFF00, 0x0002) or (e["usage_page"] == 0xFF43 and e["usage"] & 0xFF == 0x02)


def _hidpp_short(e: dict) -> bool:
    return (e["usage_page"], e["usage"]) == (0xFF00, 0x0001) or (e["usage_page"] == 0xFF43 and e["usage"] & 0xFF == 0x01)


class LogitechSession(DeviceSession):
    def __init__(self, h: Hidpp, uid: str, pid: int, connection: str, name: str, demo: bool = False):
        self.h = h
        self.battery_feature = next((f for f in (UNIFIED_BATTERY, BATTERY_STATUS) if h.has(f)), None)
        self.has_dpi = h.has(ADJUSTABLE_DPI)
        self.has_rate = h.has(REPORT_RATE)
        self.has_onboard = h.has(ONBOARD_PROFILES)
        caps = Capabilities(battery=self.battery_feature is not None)
        if self.has_dpi:
            values, step = parse_dpi_list(h.call(ADJUSTABLE_DPI, 1, 0))
            if values:
                caps.dpi_min, caps.dpi_max, caps.dpi_step = min(values), max(values), step
                caps.dpi_values = [] if step else sorted(values)
                caps.dpi_stages = 1
        if self.has_rate:
            caps.polling_rates = rates_from_mask(h.call(REPORT_RATE, 0)[0])
        self.info = DeviceInfo(
            uid=uid, key=f"logitech/{slug(name)}", name=name if name.lower().startswith("logitech") else f"Logitech {name}",
            vendor="Logitech", driver="logitech", vid=VID, pid=pid, connection=connection,
            support="basic" if caps.configurable else "detected", caps=caps, conflicts=dict(CONFLICTS), demo=demo)
        self._battery: tuple = (None, None, None)
        self._battery_at = 0.0
        self._switched_to_host = False      # Wyrm took the mouse out of on-board mode

    # --- reads ---------------------------------------------------------------------------
    def _dpi(self) -> int:
        r = self.h.call(ADJUSTABLE_DPI, 2, 0)
        return r[1] << 8 | r[2]

    def _rate_ms(self) -> int:
        return self.h.call(REPORT_RATE, 1, 0)[0]

    def _onboard(self) -> bool:
        return self.has_onboard and self.h.call(ONBOARD_PROFILES, 2)[0] == ONBOARD

    def poll(self) -> DeviceStatus:
        level, charging, full = self._battery
        if self.h.ping() is None:
            return DeviceStatus(link=False, battery=level, charging=charging, full=full)
        note = ""
        try:
            if self.battery_feature and time.monotonic() - self._battery_at > BATTERY_EVERY_S:
                self._battery = level, charging, full = read_battery(self.h, self.battery_feature)
                self._battery_at = time.monotonic()
            if self._onboard() and self.info.caps.configurable:
                note = ("Uses its on-board profile, so Wyrm only reads DPI and polling rate. "
                        "Turn on experimental writes to let Wyrm set them.")
        except (HidppError, NoAnswer) as e:
            log.debug("poll %s: %s", self.info.uid, e)
        return DeviceStatus(link=True, battery=level, charging=charging, full=full, note=note)

    def read_state(self) -> DeviceState | None:
        try:
            dpi = self._dpi() if self.has_dpi else None
            rate_ms = self._rate_ms() if self.has_rate else None
            mode = self.h.call(ONBOARD_PROFILES, 2)[0] if self.has_onboard else None
        except (HidppError, NoAnswer) as e:
            log.info("read %s: %s", self.info.uid, e)
            return None
        settings = DeviceSettings(polling_hz=1000 // rate_ms if rate_ms else None,
                                  dpi_stages=[DpiStage(dpi, True, (255, 255, 255))] if dpi else [])
        snap = {"state.json": json.dumps({"dpi": dpi, "rate_ms": rate_ms, "onboard_mode": mode}).encode()}
        return DeviceState(settings, snap)

    # --- writes ---------------------------------------------------------------------------
    def apply(self, settings: DeviceSettings, macros: dict, opts: dict) -> dict:
        info = {"changed": [], "skipped": [], "dry_run": bool(opts.get("dry_run"))}
        caps = self.info.caps
        want_dpi = want_ms = None
        if settings.dpi_stages and self.has_dpi and caps.dpi_stages:
            st = settings.dpi_stages[min(max(settings.active_stage, 0), len(settings.dpi_stages) - 1)]
            want_dpi = caps.snap_dpi(st.dpi)
        if settings.polling_hz in caps.polling_rates and self.has_rate:
            want_ms = 1000 // settings.polling_hz
        if want_dpi is None and want_ms is None:
            return info
        if self.h.ping() is None:
            raise NotReady()
        try:
            todo = []
            if want_dpi is not None and self._dpi() != want_dpi:
                todo.append("DPI")
            if want_ms is not None and self._rate_ms() != want_ms:
                todo.append("polling rate")
            if not todo:
                return info
            if self._onboard():
                if not opts.get("experimental"):
                    info["skipped"].append(f"{' and '.join(todo)}: the {self.info.short_name} is using its "
                                           "on-board profile")
                    return info
                todo.insert(0, "host mode")
            if info["dry_run"]:
                info["changed"] = todo
                return info
            if "host mode" in todo:
                self.h.call(ONBOARD_PROFILES, 1, HOST)
                self._switched_to_host = True
            if "DPI" in todo:
                self.h.call(ADJUSTABLE_DPI, 3, 0, want_dpi >> 8, want_dpi & 0xFF)
                if self._dpi() != want_dpi:
                    raise ApplyRefused(f"The {self.info.short_name} didn't keep {want_dpi} DPI.")
            if "polling rate" in todo:
                self.h.call(REPORT_RATE, 2, want_ms)
                if self._rate_ms() != want_ms:
                    raise ApplyRefused(f"The {self.info.short_name} didn't keep the {1000 // want_ms} Hz polling rate.")
        except HidppError as e:
            raise ApplyRefused(f"The {self.info.short_name} refused the change ({e}).") from e
        except NoAnswer as e:
            raise NotReady() from e
        info["changed"] = todo
        return info

    def restore(self, snapshot: dict[str, bytes]) -> bool:
        d = json.loads(snapshot.get("state.json") or b"{}")
        if self.h.ping() is None:
            raise NotReady()
        try:
            if d.get("onboard_mode") == ONBOARD and self.has_onboard:
                self.h.call(ONBOARD_PROFILES, 1, ONBOARD)    # the on-board profile sets DPI and rate again
                self._switched_to_host = False
                return self._onboard()
            ok = True
            if d.get("dpi") and self.has_dpi:
                self.h.call(ADJUSTABLE_DPI, 3, 0, d["dpi"] >> 8, d["dpi"] & 0xFF)
                ok = ok and self._dpi() == d["dpi"]
            if d.get("rate_ms") and self.has_rate:
                self.h.call(REPORT_RATE, 2, d["rate_ms"])
                ok = ok and self._rate_ms() == d["rate_ms"]
            return ok
        except HidppError as e:
            raise ApplyRefused(f"Restore failed: {e}") from e

    def shutdown(self) -> None:
        if self._switched_to_host:
            try:
                self.h.call(ONBOARD_PROFILES, 1, ONBOARD)
            except Exception as e:  # best effort while quitting
                log.info("couldn't put %s back on its on-board profile: %s", self.info.name, e)


def probe_session(h: Hidpp, uid: str, pid: int, connection: str, demo: bool = False) -> LogitechSession | None:
    """A session for the HID++ 2.0 mouse at this index, or None (nothing there, or not a mouse)."""
    version = h.ping()
    if version is None or version[0] < 2:
        return None
    try:
        name = read_name(h) if h.has(DEVICE_NAME) else ""
        try:
            kind = h.call(DEVICE_NAME, 2)[0] if h.has(DEVICE_NAME) else None
        except HidppError:
            kind = None          # older devices don't report a type
        if kind is not None and kind not in MOUSE_TYPES:
            return None
        return LogitechSession(h, uid, pid, connection, name or f"mouse {pid:04x}", demo)
    except (HidppError, NoAnswer) as e:
        log.info("HID++ probe of %s failed: %s", uid, e)
        return None


class LogitechConnection(Connection):
    def __init__(self, t, key: str, pid: int, receiver: bool, connection: str = "usb", demo: bool = False):
        self.t, self.key, self.pid, self.receiver, self.demo = t, key, pid, receiver, demo
        self.connection = "receiver" if receiver else connection
        self._sessions: dict[int, LogitechSession] = {}
        self._next_scan = 0.0

    def refresh(self) -> None:
        if time.monotonic() < self._next_scan:
            return
        self._next_scan = time.monotonic() + RESCAN_S
        for index in (range(1, 7) if self.receiver else (DIRECT,)):
            if index not in self._sessions:
                s = probe_session(Hidpp(self.t, index), f"{self.key}#{index}", self.pid, self.connection, self.demo)
                if s:
                    log.info("found %s on %s", s.info.name, self.key)
                    self._sessions[index] = s

    def sessions(self) -> list[DeviceSession]:
        return list(self._sessions.values())

    def close(self) -> None:
        self.t.close()


class LogitechDriver(Driver):
    name = "logitech"

    def discover(self, entries: list[dict]) -> list[Candidate]:
        groups: dict[tuple, list[dict]] = {}
        for e in entries:
            if e["vendor_id"] == VID:
                groups.setdefault((e["product_id"], entry_str(e, "serial_number")), []).append(e)
        return [Candidate(f"logitech:{pid:04x}:{serial or '-'}", self, es)
                for (pid, serial), es in groups.items() if any(_hidpp_long(e) for e in es)]

    def open(self, cand: Candidate):
        long_e = next(e for e in cand.entries if _hidpp_long(e))
        short_e = next((e for e in cand.entries if _hidpp_short(e)
                        and e["interface_number"] == long_e["interface_number"]), None)
        pid = long_e["product_id"]
        receiver = pid in RECEIVERS or "receiver" in entry_str(long_e, "product_string").lower()
        t = HidppTransport(long_e["path"], short_e["path"] if short_e else None)
        conn = LogitechConnection(t, cand.key, pid, receiver, path_connection(cand.entries))
        conn.refresh()
        if not receiver and not conn.sessions():
            conn.close()
            return None            # no HID++ 2.0 mouse here; the generic driver can still show it
        return conn
