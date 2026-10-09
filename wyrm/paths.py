"""Where Wyrm keeps its files: %LOCALAPPDATA%\\Wyrm (override with WYRM_DATA)."""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("WYRM_DATA") or os.path.join(
        os.environ.get("LOCALAPPDATA", str(Path.home())), "Wyrm")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p
