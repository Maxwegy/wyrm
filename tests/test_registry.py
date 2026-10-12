from wyrm.core.rawinput import parse_device_path
from wyrm.drivers.base import Candidate, DeviceInfo, Driver, SingleConnection
from wyrm.drivers.generic import GenericDriver, GenericSession
from wyrm.drivers.logitech.driver import LogitechDriver
from wyrm.drivers.registry import RETRY_S, Registry
from wyrm.drivers.sinowealth.driver import SinoWealthDriver


def _e(vid, pid, iface, page, usage, path, product="", maker="", serial=""):
    return {"vendor_id": vid, "product_id": pid, "interface_number": iface, "usage_page": page, "usage": usage,
            "path": path.encode(), "product_string": product, "manufacturer_string": maker, "serial_number": serial}


M811 = [_e(0x258A, 0x2F, 0, 0x01, 0x02, r"\\?\HID#VID_258A&PID_002F&MI_00#8&2cd1&0&0000", "2.4G Dual Mode Mouse",
           "SINO WEALTH")] + [
    _e(0x258A, 0x2F, 1, page, usage, rf"\\?\HID#VID_258A&PID_002F&MI_01&Col0{n}#8&8f9c&0&000{n}",
       "2.4G Dual Mode Mouse", "SINO WEALTH")
    for n, (page, usage) in enumerate([(0x01, 0x06), (0x0C, 0x01), (0xFF00, 0x01), (0xFF00, 0x01),
                                       (0xFF00, 0x01), (0xFF01, 0x01)], 1)]
TOUCHPAD = [_e(0x04F3, 0x307A, -1, page, usage, rf"\\?\HID#ELAN1203&Col0{n}#4&244b&0&000{n}", "HIDI2C Device",
               "Microsoft", "9999") for n, (page, usage) in enumerate([(0x01, 0x02), (0x0D, 0x05), (0x0D, 0x0E)], 1)]
LAPTOP_KEYS = [_e(0x0B05, 0x19B6, -1, 0x01, 0x0C, r"\\?\HID#ITE5570&Col01#4&2301&0&0000", "HIDI2C Device")]
OTHER = [_e(0x1234, 0x5678, 0, 0x01, 0x02, r"\\?\HID#VID_1234&PID_5678#7&abc&0&0000", "USB Optical Mouse", "")]
LOGI_RX = [_e(0x046D, 0xC539, 1, 0x01, 0x02, r"\\?\HID#VID_046D&PID_C539&MI_01#9&1&0&0000", "USB Receiver", "Logitech"),
           _e(0x046D, 0xC539, 2, 0xFF00, 0x01, r"\\?\HID#VID_046D&PID_C539&MI_02&Col01#9&2&0&0000", "USB Receiver",
              "Logitech"),
           _e(0x046D, 0xC539, 2, 0xFF00, 0x02, r"\\?\HID#VID_046D&PID_C539&MI_02&Col02#9&2&0&0001", "USB Receiver",
              "Logitech")]
BT_MOUSE = [_e(0x045E, 0x0916, -1, 0x01, 0x02,
               r"\\?\HID#{00001812-0000-1000-8000-00805f9b34fb}_Dev_VID&02045e_PID&0916#a&1&0&0000",
               "Surface Mobile Mouse", "")]


def test_each_driver_picks_its_own_devices():
    entries = M811 + TOUCHPAD + LAPTOP_KEYS + OTHER + LOGI_RX + BT_MOUSE
    sino = SinoWealthDriver().discover(entries)
    assert [c.key for c in sino] == ["sinowealth:258a:002f"] and len(sino[0].entries) == 7
    logi = LogitechDriver().discover(entries)
    assert [c.key for c in logi] == ["logitech:c539:-"]
    keys = [c.key.rsplit(":", 1)[0] for c in GenericDriver().discover(OTHER + TOUCHPAD + LAPTOP_KEYS + BT_MOUSE)]
    assert keys == ["generic:1234:5678", "generic:045e:0916"]       # no touchpad, no laptop keyboard


def test_cable_wins_when_cable_and_receiver_are_both_plugged_in():
    cable = [dict(e, product_id=0x2E, path=e["path"].replace(b"002F", b"002E")) for e in M811]
    cands = SinoWealthDriver().discover(M811 + cable)
    assert [c.key for c in cands] == ["sinowealth:258a:002e"] and len(cands[0].entries) == 14


def test_generic_mice_get_a_name_and_connection():
    conn = GenericDriver().open(GenericDriver().discover(BT_MOUSE)[0])
    info = conn.session.info
    assert (info.name, info.vendor, info.connection, info.support) == (
        "Microsoft Surface Mobile Mouse", "Microsoft", "bluetooth", "detected")
    assert not info.caps.configurable
    info = GenericDriver().open(GenericDriver().discover(OTHER)[0]).session.info
    assert info.name == "USB Optical Mouse" and info.vendor == "Unknown" and info.connection == "usb"


class _FlakyDriver(Driver):
    """Claims the M811's entries; opens only when told to."""
    name = "flaky"

    def __init__(self):
        self.ok, self.opened = False, 0

    def discover(self, entries):
        mine = [e for e in entries if e["vendor_id"] == 0x258A]
        return [Candidate("flaky:258a", self, mine)] if mine else []

    def open(self, cand):
        self.opened += 1
        if not self.ok:
            return None
        info = DeviceInfo(uid=cand.key, key="flaky/mouse", name="Flaky", vendor="Test", driver="flaky")
        return SingleConnection(GenericSession(info))


def test_registry_falls_back_to_generic_then_retries():
    entries = M811 + TOUCHPAD + OTHER
    flaky = _FlakyDriver()
    reg = Registry([flaky, GenericDriver()], lambda: entries)
    reg.scan()
    names = sorted(s.info.name for s in reg.sessions())
    assert names == ["SINO WEALTH 2.4G Dual Mode Mouse", "USB Optical Mouse"]   # shown by generic meanwhile
    reg.scan()
    assert flaky.opened == 1                                            # waits before probing again
    flaky.ok = True
    reg._retry["flaky:258a"] = (0.0, RETRY_S)
    reg.scan()
    assert sorted(s.info.name for s in reg.sessions()) == ["Flaky", "USB Optical Mouse"]
    entries[:] = OTHER                                                  # the receiver is unplugged
    reg.scan()
    assert [s.info.name for s in reg.sessions()] == ["USB Optical Mouse"]


def test_registry_backs_off_longer_each_time():
    flaky = _FlakyDriver()
    reg = Registry([flaky], lambda: M811)
    reg.scan()
    first = reg._retry["flaky:258a"][1]
    reg._retry["flaky:258a"] = (0.0, first)
    reg.scan()
    assert reg._retry["flaky:258a"][1] == first * 2


def test_device_paths_parse_to_vid_and_pid():
    assert parse_device_path(r"\\?\HID#VID_258A&PID_002F&MI_00#8&2cd10463&0&0000#{378de44c}") == (0x258A, 0x2F)
    assert parse_device_path(r"\\?\HID#{00001812-0000-1000-8000-00805f9b34fb}_Dev_VID&02046d_PID&b023_REV&0007"
                             r"#a&1&0000#{378de44c}") == (0x046D, 0xB023)
    assert parse_device_path(r"\\?\HID#{00001124-0000-1000-8000-00805f9b34fb}_VID&0002046d_PID&b01e&Col01#8&1"
                             ) == (0x046D, 0xB01E)
    assert parse_device_path(r"\\?\HID#ELAN1203&Col01#4&244b297f&0&0000#{x}") is None
