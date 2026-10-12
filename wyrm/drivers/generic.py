"""Any other mouse: shown by name so you can see it's there, never opened or written."""
from __future__ import annotations

import hashlib

from .base import (Candidate, Capabilities, DeviceInfo, DeviceSession, DeviceStatus, Driver, SingleConnection,
                   entry_str, slug)

# A few well-known vendor IDs, for mice whose manufacturer string is empty.
VENDORS = {
    0x03F0: "HP", 0x045E: "Microsoft", 0x046D: "Logitech", 0x0458: "Genius", 0x04D9: "Holtek", 0x05AC: "Apple",
    0x093A: "PixArt", 0x0951: "HyperX", 0x0B05: "ASUS", 0x1038: "SteelSeries", 0x1532: "Razer", 0x17EF: "Lenovo",
    0x1B1C: "Corsair", 0x1E7D: "ROCCAT", 0x258A: "SinoWealth", 0x413C: "Dell",
}
BLUETOOTH_GUIDS = ("{00001124-0000-1000-8000-00805f9b34fb}", "{00001812-0000-1000-8000-00805f9b34fb}")


def is_mouse(entries: list[dict]) -> bool:
    """Has a Generic Desktop Mouse collection and isn't a touchpad or touch screen."""
    pages = {(e["usage_page"], e["usage"]) for e in entries}
    return (0x01, 0x02) in pages and not pages & {(0x0D, 0x04), (0x0D, 0x05)}


def connection(entries: list[dict]) -> str:
    paths = " ".join(entry_str(e, "path").lower() for e in entries)
    return "bluetooth" if any(g in paths for g in BLUETOOTH_GUIDS) else "usb"


def is_builtin(entries: list[dict]) -> bool:
    """Laptop pointing devices on I2C (no USB VID in the path), e.g. a pointing stick."""
    paths = " ".join(entry_str(e, "path").lower() for e in entries)
    return "vid_" not in paths and connection(entries) != "bluetooth"


class GenericSession(DeviceSession):
    def __init__(self, info: DeviceInfo):
        self.info = info

    def poll(self) -> DeviceStatus:
        return DeviceStatus(link=True)


class GenericDriver(Driver):
    name = "generic"

    def discover(self, entries: list[dict]) -> list[Candidate]:
        groups: dict[tuple, list[dict]] = {}
        for e in entries:
            groups.setdefault((e["vendor_id"], e["product_id"], entry_str(e, "serial_number")), []).append(e)
        out = []
        for (vid, pid, _serial), es in groups.items():
            if not is_mouse(es) or is_builtin(es):
                continue
            mouse_path = next(entry_str(e, "path") for e in es if (e["usage_page"], e["usage"]) == (0x01, 0x02))
            tag = hashlib.sha1(mouse_path.lower().encode()).hexdigest()[:8]
            out.append(Candidate(f"generic:{vid:04x}:{pid:04x}:{tag}", self, es))
        return out

    def open(self, cand: Candidate):
        e = cand.entries[0]
        vid, pid = e["vendor_id"], e["product_id"]
        vendor = entry_str(e, "manufacturer_string").strip() or VENDORS.get(vid, "")
        product = entry_str(e, "product_string").strip() or f"Mouse {vid:04x}:{pid:04x}"
        name = product if not vendor or product.lower().startswith(vendor.lower()) else f"{vendor} {product}"
        info = DeviceInfo(uid=cand.key, key=f"generic/{vid:04x}-{pid:04x}-{slug(product)}", name=name,
                          vendor=vendor or "Unknown", driver=self.name, vid=vid, pid=pid,
                          connection=connection(cand.entries), caps=Capabilities())
        return SingleConnection(GenericSession(info))
