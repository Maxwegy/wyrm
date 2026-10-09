"""Human-readable labels for button actions."""
from __future__ import annotations

from .keys import CONSUMER_NAMES, MOUSE_BUTTONS, key_name
from .model import ButtonAction

MACRO_MODES = {1: "times", 2: "until any key", 4: "while held"}


def describe(a: ButtonAction, macros: dict | None = None) -> str:
    k = a.kind
    if k == "mouse":
        names = [n for bit, n in MOUSE_BUTTONS if a.mouse_mask & bit]
        return " + ".join(names) if names else "Mouse (none)"
    if k == "wheel":
        return "Scroll up" if a.usage >= 0 else "Scroll down"
    if k == "key":
        return key_name(a.usage, a.modifiers)
    if k == "consumer":
        return CONSUMER_NAMES.get(a.usage, f"Media {a.usage:#05x}")
    if k == "dpi_up":
        return "DPI +"
    if k == "dpi_down":
        return "DPI −"
    if k == "dpi_cycle":
        return "DPI cycle"
    if k == "dpi_lock":
        return f"DPI lock {a.usage}"
    if k == "fire":
        return f"Rapid fire ×{a.count}"
    if k == "disabled":
        return "Disabled"
    if k == "light_toggle":
        return "Lighting on/off"
    if k == "profile_cycle":
        return "Profile (vendor)"
    if k == "profile_next":
        return "Next profile"
    if k == "profile_prev":
        return "Previous profile"
    if k == "macro":
        name = (macros or {}).get(a.macro_id)
        label = name.name if name else "Macro (unsaved)"
        mode = MACRO_MODES.get(a.macro_mode, "")
        return f"▶ {label}" + (f" ×{a.count}" if a.macro_mode == 1 and a.count > 1 else
                                (f" · {mode}" if a.macro_mode != 1 else ""))
    if k == "raw":
        return f"Raw {a.raw}"
    return k
