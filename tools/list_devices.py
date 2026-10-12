"""List every mouse Wyrm can see and which driver would handle it. Read-only.

Usage: python tools/list_devices.py [--probe]

Without --probe nothing is opened: it only lists what Windows reports. With --probe, Wyrm's
drivers open the mice they know and ask read-only questions (model, firmware, HID++ name and
feature list). Paste the output into a "New mouse" issue on GitHub.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hid  # noqa: E402

from wyrm.drivers.base import entry_str  # noqa: E402
from wyrm.drivers.generic import GenericDriver  # noqa: E402
from wyrm.drivers.logitech.driver import LogitechDriver  # noqa: E402
from wyrm.drivers.logitech.hidpp import DIRECT, FEATURE_SET, Hidpp, HidppError, NoAnswer  # noqa: E402
from wyrm.drivers.sinowealth.driver import SinoWealthDriver  # noqa: E402


def collections(entries):
    return ", ".join(f"if{e['interface_number']} {e['usage_page']:04x}/{e['usage']:04x}" for e in entries)


def hidpp_features(t, index):
    h = Hidpp(t, index)
    if h.ping() is None:
        return None
    try:
        n = h.call(FEATURE_SET, 0)[0]
        return [f"{r[0] << 8 | r[1]:04x}" for r in (h.call(FEATURE_SET, 1, i) for i in range(1, n + 1))]
    except (HidppError, NoAnswer) as e:
        return [f"error: {e}"]


def probe(cand):
    conn = cand.driver.open(cand)
    if conn is None:
        print("    probe: no answer (Wyrm would show it as a plain mouse)")
        return
    try:
        for s in conn.sessions():
            s.poll()
            i = s.info
            print(f"    -> {i.name}  [{i.key}]  support={i.support}  fw={i.fw or '-'}  via {i.connection}")
        if isinstance(cand.driver, LogitechDriver):
            for index in ((DIRECT,) if not conn.receiver else range(1, 7)):
                feats = hidpp_features(conn.t, index)
                if feats:
                    print(f"    HID++ features at {index:#04x}: {' '.join(feats)}")
    finally:
        conn.close()


def main():
    do_probe = "--probe" in sys.argv
    entries = hid.enumerate()
    claimed = set()
    found = 0
    for drv in (SinoWealthDriver(), LogitechDriver(), GenericDriver()):
        for cand in drv.discover([e for e in entries if e["path"] not in claimed]):
            claimed.update(e["path"] for e in cand.entries)
            e = cand.entries[0]
            found += 1
            print(f"{drv.name:<10} {e['vendor_id']:04x}:{e['product_id']:04x}  "
                  f"{entry_str(e, 'manufacturer_string')!r} {entry_str(e, 'product_string')!r}")
            print(f"    collections: {collections(cand.entries)}")
            if do_probe and drv.name != "generic":
                try:
                    probe(cand)
                except Exception as ex:  # report, don't crash: this output goes into bug reports
                    print(f"    probe failed: {ex}")
    others = [e for e in entries if e["path"] not in claimed]
    print(f"\n{found} mouse device(s). {len(others)} other HID collection(s) ignored "
          "(keyboards, touchpads, controllers...).")
    if not do_probe:
        print("Run with --probe to ask the mice Wyrm knows for their model and features (read-only).")


if __name__ == "__main__":
    main()
