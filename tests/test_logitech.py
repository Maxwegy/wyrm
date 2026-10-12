import json

import pytest

from wyrm.core.model import DeviceSettings, DpiStage
from wyrm.drivers.base import ApplyRefused, NotReady
from wyrm.drivers.logitech.driver import LogitechConnection, probe_session
from wyrm.drivers.logitech.fake import FakeHidppMouse, FakeHidppTransport
from wyrm.drivers.logitech.hidpp import (ADJUSTABLE_DPI, BATTERY_STATUS, DEVICE_NAME, DIRECT, FEATURE_SET, HOST,
                                         ONBOARD, ONBOARD_PROFILES, REPORT_RATE, ROOT, Hidpp, HidppError,
                                         parse_dpi_list, rates_from_mask)


def _direct(mouse: FakeHidppMouse | None = None):
    m = mouse or FakeHidppMouse()
    s = probe_session(Hidpp(FakeHidppTransport({DIRECT: m}), DIRECT), "logitech:c08b:-#255", 0xC08B, "usb")
    return s, m


def test_probe_reads_name_battery_dpi_and_rates():
    s, m = _direct(FakeHidppMouse(name="G502 HERO Gaming Mouse"))
    i = s.info
    assert i.name == "Logitech G502 HERO Gaming Mouse" and i.key == "logitech/g502-hero-gaming-mouse"
    assert i.support == "basic" and i.vendor == "Logitech" and i.short_name == "G502 HERO Gaming Mouse"
    assert (i.caps.dpi_min, i.caps.dpi_max, i.caps.dpi_step, i.caps.dpi_stages) == (100, 25600, 50, 1)
    assert i.caps.polling_rates == [125, 250, 500, 1000]
    st = s.poll()
    assert st.link and st.battery == 80 and st.note == ""
    state = s.read_state()
    assert state.settings.dpi_stages[0].dpi == 1600 and state.settings.polling_hz == 1000
    assert json.loads(state.snapshot["state.json"]) == {"dpi": 1600, "rate_ms": 1, "onboard_mode": HOST}


def test_long_names_arrive_in_chunks():
    s, m = _direct(FakeHidppMouse(name="PRO X SUPERLIGHT Wireless Gaming Mouse"))
    assert s.info.name == "Logitech PRO X SUPERLIGHT Wireless Gaming Mouse"
    chunks = [c for c in m.calls if c[:2] == (DEVICE_NAME, 1)]
    assert [c[2][0] for c in chunks] == [0, 16, 32]


def test_older_battery_feature_and_no_onboard_profiles():
    m = FakeHidppMouse(features=[ROOT, FEATURE_SET, DEVICE_NAME, BATTERY_STATUS, ADJUSTABLE_DPI], battery=50, charging=1)
    s, _ = _direct(m)
    st = s.poll()
    assert st.battery == 50 and st.charging is True
    assert s.info.caps.polling_rates == [] and s.info.caps.dpi_stages == 1


def test_keyboards_are_not_mice():
    s, _ = _direct(FakeHidppMouse(kind=0))
    assert s is None


def test_receiver_finds_awake_mice_and_skips_empty_slots():
    asleep = FakeHidppMouse(name="M720 Triathlon", asleep=True)
    t = FakeHidppTransport({1: FakeHidppMouse(name="MX Master 3S"), 2: asleep}, receiver=True)
    conn = LogitechConnection(t, "logitech:c548:-", 0xC548, receiver=True)
    conn.refresh()
    assert [s.info.name for s in conn.sessions()] == ["Logitech MX Master 3S"]
    assert conn.sessions()[0].info.connection == "receiver"
    asleep.asleep = False
    conn._next_scan = 0
    conn.refresh()
    assert sorted(s.info.short_name for s in conn.sessions()) == ["M720 Triathlon", "MX Master 3S"]
    asleep.asleep = True
    assert not [s for s in conn.sessions() if s.info.short_name == "M720 Triathlon"][0].poll().link


def test_apply_sets_dpi_and_rate_and_reads_back():
    s, m = _direct()
    info = s.apply(DeviceSettings(dpi_stages=[DpiStage(3210)], polling_hz=500), {}, {})
    assert info["changed"] == ["DPI", "polling rate"]
    assert m.dpi == 3200 and m.rate_ms == 2          # snapped to the 50-DPI grid
    assert s.apply(DeviceSettings(dpi_stages=[DpiStage(3200)], polling_hz=500), {}, {})["changed"] == []


def test_on_board_profile_is_left_alone_unless_experimental():
    s, m = _direct(FakeHidppMouse(onboard_mode=ONBOARD))
    assert "on-board profile" in s.poll().note
    want = DeviceSettings(dpi_stages=[DpiStage(800)], polling_hz=125)
    info = s.apply(want, {}, {})
    assert info["changed"] == [] and "on-board profile" in info["skipped"][0]
    assert m.dpi == 1600 and m.onboard_mode == ONBOARD and not [c for c in m.calls if c[1] == 3]
    info = s.apply(want, {}, {"experimental": True})
    assert info["changed"] == ["host mode", "DPI", "polling rate"]
    assert (m.onboard_mode, m.dpi, m.rate_ms) == (HOST, 800, 8)
    s.shutdown()                                     # Wyrm quits: back to the on-board profile
    assert m.onboard_mode == ONBOARD


def test_dry_run_sends_nothing():
    s, m = _direct()
    before = len(m.calls)
    info = s.apply(DeviceSettings(dpi_stages=[DpiStage(800)]), {}, {"dry_run": True})
    assert info["changed"] == ["DPI"] and info["dry_run"]
    assert all(fn != 3 for f, fn, p in m.calls[before:]) and m.dpi == 1600


def test_errors_and_sleep():
    s, m = _direct()
    with pytest.raises(HidppError):
        s.h.call(ADJUSTABLE_DPI, 3, 0, 0x00, 0x07)    # 7 DPI is out of range: the device says so
    m.asleep = True
    assert not s.poll().link
    with pytest.raises(NotReady):
        s.apply(DeviceSettings(dpi_stages=[DpiStage(800)]), {}, {})


def test_only_allow_listed_functions_can_be_sent():
    s, m = _direct()
    with pytest.raises(PermissionError):
        s.h.call(ONBOARD_PROFILES, 5)                 # memory read/write isn't on the list
    with pytest.raises(PermissionError):
        s.h.call(0x00D0, 0)                           # DFU: never


def test_restore_puts_the_on_board_profile_back():
    s, m = _direct(FakeHidppMouse(onboard_mode=ONBOARD))
    snap = s.read_state().snapshot
    s.apply(DeviceSettings(dpi_stages=[DpiStage(800)]), {}, {"experimental": True})
    assert m.onboard_mode == HOST
    assert s.restore(snap) and m.onboard_mode == ONBOARD


def test_restore_refused_by_device_is_reported():
    s, m = _direct()
    with pytest.raises(ApplyRefused):
        s.restore({"state.json": json.dumps({"dpi": 7, "rate_ms": 1, "onboard_mode": HOST}).encode()})


def test_dpi_list_and_rate_parsing():
    assert parse_dpi_list(bytes([0, 0x00, 0x64, 0xE0, 0x32, 0x64, 0x00, 0, 0])) == ([100, 25600], 50)
    assert parse_dpi_list(bytes([0, 0x01, 0x90, 0x03, 0x20, 0x06, 0x40, 0, 0])) == ([400, 800, 1600], 0)
    assert rates_from_mask(0b10001011) == [125, 250, 500, 1000]
    assert rates_from_mask(0b1) == [1000]


def test_discrete_dpi_lists_snap_to_the_list():
    m = FakeHidppMouse(dpi_list=[400, 800, 1600, 3200], dpi=800)
    m.dpi_ok = lambda v: v in (400, 800, 1600, 3200)
    s, _ = _direct(m)
    assert s.info.caps.dpi_values == [400, 800, 1600, 3200] and s.info.caps.snap_dpi(1500) == 1600
    s.apply(DeviceSettings(dpi_stages=[DpiStage(1500)]), {}, {})
    assert m.dpi == 1600


def test_report_rate_only_offers_supported_rates():
    s, m = _direct(FakeHidppMouse(rate_mask=0b1001))       # 1 ms and 4 ms
    assert s.info.caps.polling_rates == [250, 1000]
    assert s.apply(DeviceSettings(polling_hz=500), {}, {})["changed"] == []
    assert m.rate_ms == 1 and REPORT_RATE in {c[0] for c in m.calls}
