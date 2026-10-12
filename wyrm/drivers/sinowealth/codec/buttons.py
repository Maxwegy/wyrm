"""4-byte button slot codec for the 88-byte button block."""
from __future__ import annotations

from ....core.keys import HOTKEY_NEXT_PROFILE, HOTKEY_PREV_PROFILE
from ....core.model import ButtonAction
from .layout import load_layout

T_MOUSE, T_WHEEL, T_KEY, T_CONSUMER = 0x11, 0x12, 0x21, 0x22
T_FIRE, T_DPI, T_DPI_LOCK, T_SPECIAL, T_MACRO = 0x31, 0x41, 0x42, 0x50, 0x70
SP_DISABLED, SP_LIGHT, SP_PROFILE = 0x01, 0x02, 0x06


def consumer_usages(layout: dict | None = None) -> list[int]:
    return [int(x, 16) for x in (layout or load_layout())["consumer_bits"]]


def encode_action(a: ButtonAction, macro_index: int = 0, layout: dict | None = None) -> bytes:
    k = a.kind
    if k == "mouse":
        return bytes([T_MOUSE, a.mouse_mask & 0xFF, 0, 0])
    if k == "wheel":
        return bytes([T_WHEEL, 0x01 if a.usage >= 0 else 0xFF, 0, 0])
    if k == "key":
        return bytes([T_KEY, a.modifiers & 0xFF, a.usage & 0xFF, 0])
    if k == "profile_next":
        return bytes([T_KEY, 0, HOTKEY_NEXT_PROFILE, 0])
    if k == "profile_prev":
        return bytes([T_KEY, 0, HOTKEY_PREV_PROFILE, 0])
    if k == "consumer":
        bit = consumer_usages(layout).index(a.usage)
        mask = (1 << bit).to_bytes(3, "little")
        return bytes([T_CONSUMER]) + mask
    if k == "dpi_cycle":
        return bytes([T_DPI, 0x00, 0, 0])
    if k == "dpi_up":
        return bytes([T_DPI, 0x01, 0, 0])
    if k == "dpi_down":
        return bytes([T_DPI, 0x02, 0, 0])
    if k == "dpi_lock":
        raw = max(1, min(255, a.usage // 100))
        return bytes([T_DPI_LOCK, raw, 0, 0])
    if k == "fire":
        return bytes([T_FIRE, a.mouse_mask or 0x01, max(1, min(255, a.delay)), max(1, min(255, a.count))])
    if k == "disabled":
        return bytes([T_SPECIAL, SP_DISABLED, 0, 0])
    if k == "light_toggle":
        return bytes([T_SPECIAL, SP_LIGHT, 0, 0])
    if k == "profile_cycle":
        return bytes([T_SPECIAL, SP_PROFILE, 0, 0])
    if k == "macro":
        if macro_index < 1:
            raise ValueError("macro needs a device macro index")
        return bytes([T_MACRO, macro_index, a.macro_mode & 0xFF, max(1, min(255, a.count))])
    if k == "raw":
        b = bytes.fromhex(a.raw)
        if len(b) != 4:
            raise ValueError("raw action must be 4 bytes")
        return b
    raise ValueError(f"unknown action kind {k!r}")


def decode_action(b: bytes, layout: dict | None = None) -> ButtonAction:
    t = b[0]
    if t == T_MOUSE:
        return ButtonAction.mouse(b[1])
    if t == T_WHEEL:
        return ButtonAction("wheel", usage=1 if b[1] == 0x01 else -1)
    if t == T_KEY:
        if b[1] == 0 and b[2] == HOTKEY_NEXT_PROFILE:
            return ButtonAction("profile_next")
        if b[1] == 0 and b[2] == HOTKEY_PREV_PROFILE:
            return ButtonAction("profile_prev")
        return ButtonAction.key(b[2], b[1])
    if t == T_CONSUMER:
        mask = int.from_bytes(b[1:4], "little")
        if mask and mask & (mask - 1) == 0:
            us = consumer_usages(layout)
            bit = mask.bit_length() - 1
            if bit < len(us):
                return ButtonAction("consumer", usage=us[bit])
    if t == T_DPI and b[1] in (0, 1, 2):
        return ButtonAction(("dpi_cycle", "dpi_up", "dpi_down")[b[1]])
    if t == T_DPI_LOCK:
        return ButtonAction("dpi_lock", usage=b[1] * 100)
    if t == T_FIRE:
        return ButtonAction("fire", mouse_mask=b[1], delay=b[2], count=b[3])
    if t == T_SPECIAL and b[1] in (SP_DISABLED, SP_LIGHT, SP_PROFILE):
        return ButtonAction({SP_DISABLED: "disabled", SP_LIGHT: "light_toggle",
                             SP_PROFILE: "profile_cycle"}[b[1]])
    if t == T_MACRO:
        return ButtonAction("macro", macro_mode=b[2], count=b[3], raw=bytes(b).hex())
    return ButtonAction("raw", raw=bytes(b).hex())


def decode_block(block: bytes, layout: dict | None = None) -> list[ButtonAction]:
    L = layout or load_layout()
    bl = L["buttons"]
    n = len(bl["names"])
    o, s = bl["slot_offset"], bl["slot_size"]
    return [decode_action(block[o + i * s: o + (i + 1) * s], L) for i in range(n)]


def encode_block(block: bytes, actions: list[ButtonAction], macro_indices: dict[int, int] | None = None,
                 layout: dict | None = None) -> bytes:
    """Patch slots 0..len(actions)-1; slots beyond stay as read from the device."""
    L = layout or load_layout()
    bl = L["buttons"]
    if len(block) != L["buttons_len"]:
        raise ValueError("button block has wrong length")
    out = bytearray(block)
    o, s = bl["slot_offset"], bl["slot_size"]
    acts = actions[:len(bl["names"])]
    if acts and not any(a.kind == "mouse" and a.mouse_mask & 1 for a in acts):
        raise ValueError("at least one button must stay Left click")
    for i, a in enumerate(acts):
        mi = (macro_indices or {}).get(i, 0)
        out[o + i * s: o + (i + 1) * s] = encode_action(a, mi, L)
    return bytes(out)
