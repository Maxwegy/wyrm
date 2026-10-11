"""Validate write framing: no-op rewrite, one reversible DPI change, restore.

Usage: python tools/sinowealth/write_selftest.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from wyrm.drivers.sinowealth import protocol as P  # noqa: E402
from wyrm.drivers.sinowealth.enumerate import find_device  # noqa: E402
from wyrm.drivers.sinowealth.transport import HidTransport  # noqa: E402

t = HidTransport(find_device())
if not P.link_ok(t):
    t.close()
    raise SystemExit("mouse asleep: move it and retry (nothing written)")
s0, b0 = P.read_settings(t), P.read_buttons(t)
try:

    P.write_settings(t, s0)
    P.write_buttons(t, b0)
    time.sleep(0.2)
    s1, b1 = P.read_settings(t), P.read_buttons(t)
    print("no-op settings readback equal:", s1 == s0)
    print("no-op buttons  readback equal:", b1 == b0)

    s2 = bytearray(s0)
    s2[0x0D] += 1                        # stage 1: +50 dpi
    P.write_settings(t, bytes(s2))
    time.sleep(0.2)
    r = P.read_settings(t)
    print("stage1 dpi after change:", (r[0x0D] | r[0x0E] << 8) * 50 + 50,
          "| only that byte changed:", [i for i in range(len(r)) if r[i] != s0[i]] == [0x0D])
finally:
    P.write_settings(t, s0)
    time.sleep(0.2)
    print("restored:", P.read_settings(t) == s0)
    t.close()
