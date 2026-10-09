"""Dump the settings and button blocks to captures/<timestamp>_<label>.*

Read-only. Usage: python tools/dump_blocks.py [label]
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wyrm.hid import protocol as P  # noqa: E402
from wyrm.hid.enumerate import find_device  # noqa: E402
from wyrm.hid.transport import HidTransport  # noqa: E402

OUT = ROOT / "captures"


def hexdump(b: bytes) -> str:
    return "\n".join(f"{i:04x}: " + b[i:i + 16].hex(" ") for i in range(0, len(b), 16))


def read_all():
    paths = find_device()
    if not paths:
        raise SystemExit("mouse not found")
    t = HidTransport(paths)
    try:
        meta = dict(fw=P.identify(t), wireless=paths.wireless, link=P.link_ok(t), battery=P.battery(t))
        return meta, P.read_settings(t), P.read_buttons(t)
    finally:
        t.close()


def dump(label: str) -> Path:
    meta, s, b = read_all()
    OUT.mkdir(exist_ok=True)
    stem = OUT / f"{time.strftime('%Y%m%d-%H%M%S')}_{label}"
    Path(f"{stem}.settings.bin").write_bytes(s)
    Path(f"{stem}.buttons.bin").write_bytes(b)
    Path(f"{stem}.hex").write_text(
        f"{meta}\n\nsettings ({len(s)}):\n{hexdump(s)}\n\nbuttons ({len(b)}):\n{hexdump(b)}\n")
    return stem


if __name__ == "__main__":
    stem = dump(sys.argv[1] if len(sys.argv) > 1 else "dump")
    print(Path(f"{stem}.hex").read_text())
    print("saved", stem)
