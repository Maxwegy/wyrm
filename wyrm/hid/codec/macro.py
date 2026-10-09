"""Macro events <-> the mouse's 3-byte event format.

Event = (command, delay_ms_after, code). Commands: 0x50 key down, 0xD0 key up,
0x10 mouse button down, 0x90 mouse button up. The delay byte tops out at
255 ms, so longer pauses are stretched with harmless "release usage 0"
filler events, which decode back into a single delay.
"""
from __future__ import annotations

from ...core.model import MacroEvent
from ..protocol import MACRO_MAX_EVENTS

TO_CMD = {"key_down": 0x50, "key_up": 0xD0, "btn_down": 0x10, "btn_up": 0x90}
FROM_CMD = {v: k for k, v in TO_CMD.items()}
FILLER = (0xD0, 0x00)  # command, code


def encode_events(events: list[MacroEvent]) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    for e in events:
        if e.type not in TO_CMD:
            raise ValueError(f"unknown macro event {e.type!r}")
        remaining = max(1, int(e.delay_ms))
        step = min(remaining, 255)
        out.append((TO_CMD[e.type], step, e.code & 0xFF))
        remaining -= step
        while remaining > 0:
            step = min(remaining, 255)
            out.append((FILLER[0], step, FILLER[1]))
            remaining -= step
    if len(out) > MACRO_MAX_EVENTS:
        raise ValueError(f"macro needs {len(out)} device events; the mouse stores {MACRO_MAX_EVENTS}")
    return out


def decode_events(raw: list[tuple[int, int, int]]) -> list[MacroEvent]:
    out: list[MacroEvent] = []
    for cmd, delay, code in raw:
        if (cmd, code) == FILLER and out:
            out[-1].delay_ms += delay
            continue
        if cmd in FROM_CMD:
            out.append(MacroEvent(FROM_CMD[cmd], code, delay))
    return out


def device_event_count(events: list[MacroEvent]) -> int:
    return len(encode_events(events))
