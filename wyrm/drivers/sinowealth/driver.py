"""SinoWealth wireless mice (258a:002e cable, 258a:002f receiver), such as the Redragon M811 PRO.

The settings block carries a model marker, so the exact model is only known once the mouse
answers a block read. Until then, and for markers Wyrm doesn't know, the mouse is shown but never
written. Write sequence for every apply:
  link check -> fresh read -> patch known bytes -> skip if unchanged ->
  write macros, settings, buttons -> read back -> compare (one retry).
"""
from __future__ import annotations

import copy
import logging
import time
from dataclasses import replace

from ...core.model import EFFECTS, ButtonAction, DeviceSettings
from ..base import (ApplyRefused, Candidate, Capabilities, DeviceInfo, DeviceSession, DeviceState, DeviceStatus,
                    Driver, NotReady, SingleConnection)
from . import protocol as P
from .codec import buttons as BC
from .codec import settings as SC
from .codec.layout import LayoutMismatch, all_layouts, check_block, layout_for_block
from .codec.macro import encode_events
from .enumerate import PID_CABLE, PID_RECEIVER, VID, probe, vendor_paths
from .transport import HidTransport

log = logging.getLogger(__name__)

BATTERY_EVERY_S = 30
CONFLICTS = {"oemdrv.exe": "the mouse maker's app"}   # the OEM tool these mice ship with
UNKNOWN_KEY = "sinowealth/unknown"


def capabilities(L: dict) -> Capabilities:
    d = L["dpi"]
    unverified = [name for name, field in (("polling", "polling"), ("stage_enable", "disabled_mask"),
                                           ("effects", "effect")) if not L[field].get("verified")]
    return Capabilities(
        dpi_min=d["min"], dpi_max=d["max"], dpi_step=d["step"], dpi_stages=SC.MAX_STAGES, stage_colors=True,
        polling_rates=sorted(L["polling"]["map"].values()), buttons=list(L["buttons"]["names"]),
        effects=[e for e in EFFECTS if e in L["effect"]["values"]],
        verified_effects=list(L.get("verified_effects", SC.VERIFIED_EFFECTS)),
        macro_slots=L.get("macro_slots", 0), macro_max_events=P.MACRO_MAX_EVENTS, battery=True,
        sensor=L.get("sensor", ""), unverified=unverified)


def _fw(raw: str) -> str:
    return raw.strip("\x00 ")   # receivers answer zeros until the mouse links


def _diff(a: bytes, b: bytes) -> list[int]:
    return [i for i in range(min(len(a), len(b))) if a[i] != b[i]]


class SinoWealthSession(DeviceSession):
    def __init__(self, t, uid: str, demo: bool = False):
        self.t = t
        self.layout: dict | None = None          # set once the model is known and configurable
        self._identified = False
        self.fw = _fw(P.identify(t))
        self.info = DeviceInfo(
            uid=uid, key=UNKNOWN_KEY, name="SinoWealth wireless mouse", vendor="SinoWealth", driver="sinowealth",
            vid=VID, pid=t.paths.pid, connection="receiver" if t.paths.wireless else "cable",
            caps=Capabilities(battery=True), fw=self.fw, conflicts=dict(CONFLICTS), demo=demo)
        self._battery = P.Battery()
        self._battery_at = 0.0

    # --- status --------------------------------------------------------------------
    def poll(self) -> DeviceStatus:
        link = P.link_ok(self.t)
        if link and time.monotonic() - self._battery_at > BATTERY_EVERY_S:
            self._battery = P.battery(self.t)
            self._battery_at = time.monotonic()
        if link and not self._identified:
            self._identify_model()
        b = self._battery
        return DeviceStatus(link=link, battery=b.level, charging=b.charging, full=b.full)

    def _identify_model(self) -> None:
        self._identified = True
        if not self.fw:
            self.fw = _fw(P.identify(self.t))
        try:
            block = P.read_settings(self.t)
        except P.ProtocolError as e:
            log.warning("unreadable settings block: %s", e)
            self.info = replace(self.info, fw=self.fw)
            return
        L = layout_for_block(block)
        if L is None:
            marker = block[9]
            self.info = replace(self.info, key=f"sinowealth/model-{marker:02x}", fw=self.fw,
                                name=f"SinoWealth wireless mouse (model {marker:#04x})")
            log.info("unknown SinoWealth model marker %#04x", marker)
            return
        configurable = L.get("support") in ("full", "basic")
        self.layout = L if configurable else None
        self.info = replace(self.info, key=L["key"], name=L["name"], vendor=L["vendor"], support=L["support"],
                            diagram=L.get("diagram", "generic"), fw=self.fw,
                            caps=capabilities(L) if configurable else Capabilities(battery=True))
        log.info("identified %s (fw %s)", L["name"], self.fw)

    # --- read ---------------------------------------------------------------------------
    def read_state(self) -> DeviceState | None:
        try:
            s, b = P.read_settings(self.t), P.read_buttons(self.t)
        except P.ProtocolError as e:
            log.warning("block read failed: %s", e)
            return None
        snap = {"settings.bin": s, "buttons.bin": b}
        if self.layout is None:
            return DeviceState(DeviceSettings(), snap, self.fw)
        L = self.layout
        dec = SC.decode(s, L)
        settings = DeviceSettings(polling_hz=dec["polling_hz"], active_stage=dec["active_stage"],
                                  dpi_stages=dec["stages"], buttons=BC.decode_block(b, L), lighting=dec["lighting"])
        return DeviceState(settings, snap, self.fw)

    def seed_settings(self, state: DeviceState) -> DeviceSettings:
        s = copy.deepcopy(state.settings)
        s.polling_hz = None   # leave the polling rate alone until the user picks one
        # The vendor "profile" action only worked with the vendor app; make it drive Wyrm instead.
        s.buttons = [ButtonAction("profile_next") if a.kind == "profile_cycle" else a for a in s.buttons]
        return s

    # --- write --------------------------------------------------------------------------
    def apply(self, settings: DeviceSettings, macros: dict, opts: dict) -> dict:
        if self.layout is None:
            raise ApplyRefused(f"Wyrm doesn't know how to configure the {self.info.name} yet.")
        L, t = self.layout, self.t
        if not P.link_ok(t):
            raise NotReady()
        s0, b0 = P.read_settings(t), P.read_buttons(t)
        try:
            s1 = SC.encode(s0, settings, allow=opts.get("allow"), layout=L)
            b1, macro_writes = b0, []
            if settings.buttons:
                acts, idx = [], {}
                for i, a in enumerate(settings.buttons):
                    if a.kind == "macro":
                        m = macros.get(a.macro_id)
                        if m is None or not m.events:
                            acts.append(ButtonAction("disabled"))
                            continue
                        idx[i] = i + 1      # one device macro slot per button
                        macro_writes.append((i + 1, encode_events(m.events)))
                    acts.append(a)
                b1 = BC.encode_block(b0, acts, idx, L)
        except (LayoutMismatch, ValueError, P.ProtocolError) as e:
            raise ApplyRefused(str(e)) from e

        changed = [name for name, a, b in (("settings", s0, s1), ("buttons", b0, b1)) if a != b]
        info = {"changed": [], "skipped": [], "dry_run": bool(opts.get("dry_run"))}
        if info["dry_run"]:
            log.info("dry run on %s: settings diff %s, buttons diff %s", self.info.name, _diff(s0, s1), _diff(b0, b1))
            info["changed"] = changed
            return info

        for index, events in macro_writes:
            if P.read_macro(t, index) != events:
                P.write_macro(t, index, events)
                info["changed"].append(f"macro {index}")
        need_s, need_b = s1 != s0, b1 != b0
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
            raise ApplyRefused("The mouse did not keep the new settings. Move it to wake it up and try again.")
        info["changed"] = changed + info["changed"]
        return info

    def restore(self, snapshot: dict[str, bytes]) -> bool:
        """Write raw blocks back. The mouse must be the model the snapshot came from."""
        s, b = snapshot.get("settings.bin"), snapshot.get("buttons.bin")
        if self.layout is None or not s or not b:
            raise ApplyRefused(f"There's no snapshot Wyrm can restore on the {self.info.name}.")
        if not P.link_ok(self.t):
            raise NotReady()
        try:
            check_block(s, self.layout)
            check_block(P.read_settings(self.t), self.layout)
        except LayoutMismatch as e:
            raise ApplyRefused(f"Restore refused: {e}") from e
        P.write_settings(self.t, s)
        P.write_buttons(self.t, b)
        return P.read_settings(self.t) == s and P.read_buttons(self.t) == b

    def close(self) -> None:
        self.t.close()


class SinoWealthDriver(Driver):
    name = "sinowealth"

    def discover(self, entries: list[dict]) -> list[Candidate]:
        mine = [e for e in entries if e["vendor_id"] == VID and e["product_id"] in (PID_CABLE, PID_RECEIVER)]
        # Cable first when both are plugged in: it's the same mouse.
        pid = next((p for p in (PID_CABLE, PID_RECEIVER) if vendor_paths(mine, p)), None)
        if pid is None:
            return []
        return [Candidate(f"sinowealth:{VID:04x}:{pid:04x}", self, mine)]

    def open(self, cand: Candidate):
        pid = int(cand.key.rsplit(":", 1)[1], 16)
        paths = probe(pid, vendor_paths(cand.entries, pid))
        if paths is None:
            return None
        t = HidTransport(paths)
        try:
            return SingleConnection(SinoWealthSession(t, cand.key))
        except Exception:
            t.close()
            raise


def default_buttons(key: str) -> list[ButtonAction]:
    for L in all_layouts():
        if L["key"] == key and L.get("default_buttons"):
            return [BC.decode_action(bytes.fromhex(h), L) for h in L["default_buttons"]]
    return []
