from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parent.parent / "layouts"


@lru_cache(maxsize=None)
def load_layout(name: str = "m811pro") -> dict:
    return json.loads((LAYOUT_DIR / f"{name}.json").read_text(encoding="utf-8"))


class LayoutMismatch(ValueError):
    """The block read from the device does not look like the layout we know."""


def check_block(block: bytes, layout: dict) -> None:
    if len(block) != layout["settings_len"]:
        raise LayoutMismatch(f"settings block is {len(block)} bytes, expected {layout['settings_len']}")
    ident, trail = layout["identity"], layout["trailer"]
    if block[ident["offset"]] != ident["value"]:
        raise LayoutMismatch(f"identity byte {block[ident['offset']]:#04x} != {ident['value']:#04x}")
    if block[trail["offset"]] != trail["value"]:
        raise LayoutMismatch("settings block trailer missing")
