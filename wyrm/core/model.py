"""Device-agnostic data model. Only wyrm.hid.codec knows about bytes."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA = 1

Color = tuple[int, int, int]

EFFECTS = ["streaming", "steady", "breathing", "tail", "neon",
           "colorful_steady", "flicker", "stars", "wave", "off"]
EFFECT_LABELS = {
    "streaming": "Colorful Streaming", "steady": "Steady", "breathing": "Breathing",
    "tail": "Colorful Tail", "neon": "Neon", "colorful_steady": "Colorful Steady",
    "flicker": "Flicker", "stars": "Stars Twinkle", "wave": "Wave", "off": "Off",
}
POLLING_RATES = [125, 250, 500, 1000]

BUTTON_KINDS = ["mouse", "wheel", "key", "consumer", "dpi_up", "dpi_down", "dpi_cycle",
                "dpi_lock", "fire", "disabled", "light_toggle", "profile_cycle", "macro", "raw"]


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
class Profile:
    id: str = field(default_factory=_new_id)
    name: str = "Default"
    accent: str = "#ff5a1f"
    polling_hz: int | None = None        # None = leave device value
    active_stage: int = 0
    dpi_stages: list[DpiStage] = field(default_factory=lambda: [
        DpiStage(1000, True, (255, 0, 0)), DpiStage(2000, True, (0, 0, 255)),
        DpiStage(4000, True, (0, 255, 255)), DpiStage(8000, True, (255, 0, 255)),
        DpiStage(26000, True, (255, 255, 0))])
    buttons: list[ButtonAction] = field(default_factory=list)  # empty = leave device buttons
    lighting: Lighting | None = None     # None = leave device lighting
    rules: list[AppRule] = field(default_factory=list)
    schema: int = SCHEMA

    # --- JSON ---------------------------------------------------------
    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(d: dict[str, Any]) -> "Profile":
        d = dict(d)
        d["dpi_stages"] = [DpiStage(s["dpi"], s.get("enabled", True), tuple(s.get("color", (255, 0, 0))))
                           for s in d.get("dpi_stages", [])]
        d["buttons"] = [ButtonAction(**b) for b in d.get("buttons", [])]
        if d.get("lighting"):
            lt = dict(d["lighting"])
            lt["color"] = tuple(lt.get("color", (255, 0, 0)))
            lt["colors"] = [tuple(c) for c in lt.get("colors", [])]
            d["lighting"] = Lighting(**lt)
        d["rules"] = [AppRule(**r) for r in d.get("rules", [])]
        known = Profile.__dataclass_fields__.keys()
        return Profile(**{k: v for k, v in d.items() if k in known})


def macro_to_json(m: Macro) -> dict[str, Any]:
    return asdict(m)


def macro_from_json(d: dict[str, Any]) -> Macro:
    return Macro(id=d["id"], name=d["name"], events=[MacroEvent(**e) for e in d.get("events", [])])
