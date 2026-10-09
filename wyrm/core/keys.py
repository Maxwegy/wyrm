"""Windows virtual-key codes <-> USB HID keyboard usages, plus display names."""
from __future__ import annotations

# (vk, hid usage, name)
_TABLE: list[tuple[int, int, str]] = []

for i in range(26):
    _TABLE.append((0x41 + i, 0x04 + i, chr(0x41 + i)))
for i in range(1, 10):
    _TABLE.append((0x30 + i, 0x1D + i, str(i)))
_TABLE.append((0x30, 0x27, "0"))
for i in range(12):
    _TABLE.append((0x70 + i, 0x3A + i, f"F{i + 1}"))
for i in range(12):
    _TABLE.append((0x7C + i, 0x68 + i, f"F{i + 13}"))
for i in range(1, 10):
    _TABLE.append((0x60 + i, 0x58 + i, f"Num {i}"))
_TABLE += [
    (0x0D, 0x28, "Enter"), (0x1B, 0x29, "Esc"), (0x08, 0x2A, "Backspace"), (0x09, 0x2B, "Tab"),
    (0x20, 0x2C, "Space"), (0xBD, 0x2D, "-"), (0xBB, 0x2E, "="), (0xDB, 0x2F, "["), (0xDD, 0x30, "]"),
    (0xDC, 0x31, "\\"), (0xBA, 0x33, ";"), (0xDE, 0x34, "'"), (0xC0, 0x35, "`"), (0xBC, 0x36, ","),
    (0xBE, 0x37, "."), (0xBF, 0x38, "/"), (0x14, 0x39, "Caps Lock"), (0x2C, 0x46, "Print Screen"),
    (0x91, 0x47, "Scroll Lock"), (0x13, 0x48, "Pause"), (0x2D, 0x49, "Insert"), (0x24, 0x4A, "Home"),
    (0x21, 0x4B, "Page Up"), (0x2E, 0x4C, "Delete"), (0x23, 0x4D, "End"), (0x22, 0x4E, "Page Down"),
    (0x27, 0x4F, "Right"), (0x25, 0x50, "Left"), (0x28, 0x51, "Down"), (0x26, 0x52, "Up"),
    (0x90, 0x53, "Num Lock"), (0x6F, 0x54, "Num /"), (0x6A, 0x55, "Num *"), (0x6D, 0x56, "Num -"),
    (0x6B, 0x57, "Num +"), (0x60, 0x62, "Num 0"), (0x6E, 0x63, "Num ."), (0x5D, 0x65, "Menu"),
    (0xA2, 0xE0, "Left Ctrl"), (0xA0, 0xE1, "Left Shift"), (0xA4, 0xE2, "Left Alt"), (0x5B, 0xE3, "Left Win"),
    (0xA3, 0xE4, "Right Ctrl"), (0xA1, 0xE5, "Right Shift"), (0xA5, 0xE6, "Right Alt"), (0x5C, 0xE7, "Right Win"),
]

VK_TO_HID = {vk: u for vk, u, _ in _TABLE}
# Generic modifier VKs (what Qt usually reports) map to the left-hand key.
VK_TO_HID.update({0x11: 0xE0, 0x10: 0xE1, 0x12: 0xE2})
HID_NAMES = {u: n for _, u, n in _TABLE}
HID_TO_VK = {u: vk for vk, u, _ in _TABLE}

MOD_CTRL, MOD_SHIFT, MOD_ALT, MOD_WIN = 0x01, 0x02, 0x04, 0x08
MOD_NAMES = [(MOD_CTRL, "Ctrl"), (MOD_SHIFT, "Shift"), (MOD_ALT, "Alt"), (MOD_WIN, "Win"),
             (0x10, "RCtrl"), (0x20, "RShift"), (0x40, "RAlt"), (0x80, "RWin")]
MODIFIER_USAGES = {0xE0: 0x01, 0xE1: 0x02, 0xE2: 0x04, 0xE3: 0x08,
                   0xE4: 0x10, 0xE5: 0x20, 0xE6: 0x40, 0xE7: 0x80}

# Keys Wyrm listens for globally so mouse buttons can drive profile switching.
HOTKEY_NEXT_PROFILE = 0x73   # F24
HOTKEY_PREV_PROFILE = 0x72   # F23

MOUSE_BUTTONS = [(0x01, "Left click"), (0x02, "Right click"), (0x04, "Middle click"),
                 (0x08, "Back"), (0x10, "Forward")]

CONSUMER_NAMES = {
    0xB5: "Next track", 0xB6: "Previous track", 0xB7: "Stop", 0xCD: "Play / Pause",
    0xE2: "Mute", 0xE9: "Volume up", 0xEA: "Volume down", 0x183: "Media player",
    0x194: "File explorer", 0x18A: "Email", 0x192: "Calculator", 0x221: "Search",
    0x223: "Browser home", 0x224: "Browser back", 0x225: "Browser forward",
    0x226: "Browser stop", 0x227: "Browser refresh", 0x22A: "Favorites",
}


def key_name(usage: int, modifiers: int = 0) -> str:
    parts = [n for bit, n in MOD_NAMES if modifiers & bit]
    parts.append(HID_NAMES.get(usage, f"Key {usage:#04x}"))
    return " + ".join(parts)
