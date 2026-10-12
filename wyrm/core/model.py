"""Device-agnostic data model. Only the drivers know about bytes.

A profile is an activity (Gaming, Work, ...). It holds settings per mouse model, so one profile
can drive several mice at once. A mouse the profile doesn't mention follows the Default profile.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA = 2
M811_KEY = "sinowealth/redragon-m811-pro"   # the only mouse a schema-1 profile can describe

Color = tuple[int, int, int]

EFFECTS = ["streaming", "steady", "breathing", "tail", "neon",
           "colorful_steady", "flicker", "stars", "wave", "off"]
EFFECT_LABELS = {
    "streaming": "Colorful Streaming", "steady": "Steady", "breathing": "Breathing",
    "tail": "Colorful Tail", "neon": "Neon", "colorful_steady": "Colorful Steady",
    "flicker": "Flicker", "stars": "Stars Twinkle", "wave": "Wave", "off": "Off",
}

BUTTON_KINDS = ["mouse", "wheel", "key", "consumer", "dpi_up", "dpi_down", "dpi_cycle",
                "dpi_lock", "fire", "disabled", "light_toggle", "profile_cycle",
                "profile_next", "profile_prev", "macro", "raw"]


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class DpiStage:
    dpi: int = 1000
    enabled: bool = True
    color: Color = (255, 0, 0)


@dataclass
class ButtonAction:
    kind: str = "disabled"
    mouse_mask: int = 0          # mouse: 01 L, 02 R, 04 M, 08 Back, 10 Forward
    modifiers: int = 0           # key: HID modifier byte
    usage: int = 0               # key: HID usage; consumer: usage id; dpi_lock: dpi; wheel: +1/-1
    count: int = 1               # fire: repeat count; macro: repeat count
    delay: int = 50              # fire: ms between clicks
    macro_id: str | None = None
    macro_mode: int = 1          # 1 repeat N, 2 until any key, 4 while held
    raw: str = ""                # raw: 4 bytes hex, round-tripped untouched

    @staticmethod
    def mouse(mask: int) -> "ButtonAction":
        return ButtonAction("mouse", mouse_mask=mask)

    @staticmethod
    def key(usage: int, modifiers: int = 0) -> "ButtonAction":
        return ButtonAction("key", usage=usage, modifiers=modifiers)


@dataclass
class Lighting:
    effect: str = "streaming"
    brightness: int = 4          # 0..4
    speed: int = 2               # 0..4
    color: Color = (255, 0, 0)   # steady colour
    colors: list[Color] = field(default_factory=lambda: [
        (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
        (0, 255, 255), (255, 128, 0), (255, 0, 255)])  # breathing palette


@dataclass
class AppRule:
    exe_name: str = ""           # case-insensitive basename, e.g. "cs2.exe"
    title_contains: str = ""     # optional extra filter on window title
    priority: int = 0


@dataclass
class MacroEvent:
    type: str                    # key_down | key_up | btn_down | btn_up
    code: int                    # HID usage or mouse button bit
    delay_ms: int = 10           # delay after this event


@dataclass
class Macro:
    id: str = field(default_factory=_new_id)
    name: str = "New macro"
    events: list[MacroEvent] = field(default_factory=list)


@dataclass
class DeviceSettings:
    """What a profile wants for one mouse model. Empty or None fields leave the mouse as it is."""
    polling_hz: int | None = None
    active_stage: int = 0
    dpi_stages: list[DpiStage] = field(default_factory=list)
    buttons: list[ButtonAction] = field(default_factory=list)
    lighting: Lighting | None = None

    @staticmethod
    def from_json(d: dict[str, Any]) -> "DeviceSettings":
        stages = [DpiStage(s["dpi"], s.get("enabled", True), tuple(s.get("color", (255, 0, 0))))
                  for s in d.get("dpi_stages") or []]
        lighting = None
        if d.get("lighting"):
            lt = dict(d["lighting"])
            lt["color"] = tuple(lt.get("color", (255, 0, 0)))
            lt["colors"] = [tuple(c) for c in lt.get("colors", [])]
            lighting = Lighting(**lt)
        return DeviceSettings(polling_hz=d.get("polling_hz"), active_stage=int(d.get("active_stage", 0)),
                              dpi_stages=stages, buttons=[ButtonAction(**b) for b in d.get("buttons") or []],
                              lighting=lighting)


@dataclass
class Profile:
    id: str = field(default_factory=_new_id)
    name: str = "Default"
    accent: str = "#ff5a1f"
    devices: dict[str, DeviceSettings] = field(default_factory=dict)   # mouse model key -> settings
    rules: list[AppRule] = field(default_factory=list)
    schema: int = SCHEMA

    # --- JSON ---------------------------------------------------------
    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(d: dict[str, Any]) -> "Profile":
        devices = {k: DeviceSettings.from_json(v) for k, v in (d.get("devices") or {}).items()}
        if d.get("schema", 1) < 2 and M811_KEY not in devices:
            devices[M811_KEY] = DeviceSettings.from_json(d)   # schema 1 kept one mouse's settings at the top
        p = Profile(name=d.get("name", "Default"), accent=d.get("accent", "#ff5a1f"), devices=devices,
                    rules=[AppRule(**r) for r in d.get("rules", [])])
        if d.get("id"):
            p.id = d["id"]
        return p


def effective_settings(profile: Profile | None, default: Profile | None, key: str) -> DeviceSettings | None:
    """What `profile` wants for mouse model `key`: its own entry, else the Default profile's, else nothing
    (the mouse is left alone)."""
    for p in (profile, default):
        if p is not None and key in p.devices:
            return p.devices[key]
    return None


def macro_to_json(m: Macro) -> dict[str, Any]:
    return asdict(m)


def macro_from_json(d: dict[str, Any]) -> Macro:
    return Macro(id=d["id"], name=d["name"], events=[MacroEvent(**e) for e in d.get("events", [])])
