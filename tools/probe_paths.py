"""Find which vendor HID collection answers the SinoWealth command channel.

Read-only: sends only identify (0x01), link (0x80) and battery (0x90) queries.
"""
import sys
import hid

VID = 0x258A
PIDS = {0x002E: "cable", 0x002F: "receiver"}
QUERIES = {0x01: "identify", 0x80: "link", 0x90: "battery"}


def query(dev, cmd):
    dev.send_feature_report(bytes([0x05, cmd, 0, 0, 0, 0, 0, 0]))
    return bytes(dev.get_feature_report(0x05, 8))


def main():
    found = False
    for d in hid.enumerate(VID):
        if d["product_id"] not in PIDS:
            continue
        tag = f"pid={d['product_id']:#06x}({PIDS[d['product_id']]}) if={d['interface_number']} " \
              f"usage={d['usage_page']:#06x}/{d['usage']:#04x}"
        print(tag)
        print("   path:", d["path"].decode(errors="replace"))
        if d["usage_page"] < 0xFF00:
            print("   skip (standard collection)")
            continue
        dev = hid.device()
        try:
            dev.open_path(d["path"])
        except OSError as e:
            print("   open failed:", e)
            continue
        try:
            for cmd, name in QUERIES.items():
                try:
                    r = query(dev, cmd)
                    print(f"   {name:<9} -> {r.hex(' ')}")
                    if cmd == 0x01 and len(r) >= 6 and r[1] == 0x01:
                        found = True
                        print("   >>> command channel; fw =", r[2:6].decode('ascii', 'replace'))
                except OSError as e:
                    print(f"   {name:<9} -> error: {e}")
        finally:
            dev.close()
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
