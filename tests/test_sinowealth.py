import pytest

from wyrm.core.device_service import DeviceWorker, read_snapshot
from wyrm.core.model import M811_KEY, ButtonAction, DeviceSettings, DpiStage, Macro, MacroEvent
from wyrm.drivers.base import ApplyRefused, NotReady, SingleConnection
from wyrm.drivers.registry import StaticRegistry
from wyrm.drivers.sinowealth import protocol as P
from wyrm.drivers.sinowealth.codec import buttons as BC
from wyrm.drivers.sinowealth.codec import settings as SC
from wyrm.drivers.sinowealth.driver import SinoWealthSession
from wyrm.drivers.sinowealth.fake import FakeMouse, FakeTransport


def _session(mouse=None):
    s = SinoWealthSession(FakeTransport(mouse or FakeMouse()), "sinowealth:258a:002f")
    s.poll()
    return s


def _device_settings(mouse: FakeMouse) -> DeviceSettings:
    d = SC.decode(mouse.settings)
    return DeviceSettings(dpi_stages=d["stages"], active_stage=d["active_stage"],
                          buttons=BC.decode_block(mouse.buttons), lighting=d["lighting"])


# --- identification ---------------------------------------------------------
def test_identifies_the_m811_pro_from_its_settings_block():
    s = _session()
    i = s.info
    assert (i.key, i.name, i.vendor, i.support, i.fw) == (M811_KEY, "Redragon M811 PRO", "Redragon", "full", "2911")
    assert i.connection == "receiver" and i.caps.dpi_max == 26000 and len(i.caps.buttons) == 16
    assert "polling" in i.caps.unverified and i.caps.effects[0] == "streaming"


def test_a_known_sibling_is_named_but_not_configured():
    m = FakeMouse()
    b = bytearray(m.settings)
    b[9] = 0x13
    m.settings = bytes(b)
    s = _session(m)
    assert s.info.name == "Redragon M690 PRO" and s.info.support == "detected"
    assert not s.info.caps.configurable and s.info.caps.battery
    with pytest.raises(ApplyRefused):
        s.apply(DeviceSettings(dpi_stages=[DpiStage(800)]), {}, {})
    assert m.writes == []


def test_an_unknown_model_is_shown_and_never_written():
    m = FakeMouse()
    b = bytearray(m.settings)
    b[9] = 0x42
    m.settings = bytes(b)
    s = _session(m)
    assert s.info.key == "sinowealth/model-42" and "0x42" in s.info.name and s.info.support == "detected"
    assert s.read_state().snapshot["settings.bin"] == m.settings      # a dump to help add it
    with pytest.raises(ApplyRefused):
        s.apply(DeviceSettings(dpi_stages=[DpiStage(800)]), {}, {})
    assert m.writes == []


def test_asleep_at_start_is_identified_when_it_wakes():
    m = FakeMouse(link=False)
    s = _session(m)
    assert s.info.key == "sinowealth/unknown" and not s.poll().link
    m.link = True
    assert s.poll().link and s.info.key == M811_KEY


# --- writes ------------------------------------------------------------------
def test_apply_identical_settings_writes_nothing():
    m = FakeMouse()
    s = _session(m)
    assert s.apply(_device_settings(m), {}, {"allow": set()}) == {"changed": [], "skipped": [], "dry_run": False}
    assert m.writes == []


def test_apply_dpi_and_button_change():
    m = FakeMouse()
    s = _session(m)
    want = _device_settings(m)
    want.dpi_stages[0] = DpiStage(1600, True, (255, 0, 0))
    want.buttons[7] = ButtonAction("profile_next")
    info = s.apply(want, {}, {"allow": set()})
    assert info["changed"] == ["settings", "buttons"]
    assert SC.decode(m.settings)["stages"][0].dpi == 1600
    assert BC.decode_block(m.buttons)[7].kind == "profile_next"
    assert len(m.writes) == 2


def test_apply_writes_macro_to_button_slot():
    m = FakeMouse()
    s = _session(m)
    mac = Macro(name="gg", events=[MacroEvent("key_down", 0x0A, 20), MacroEvent("key_up", 0x0A, 20)])
    want = _device_settings(m)
    want.buttons[9] = ButtonAction("macro", macro_id=mac.id, macro_mode=1, count=1)
    info = s.apply(want, {mac.id: mac}, {"allow": set()})
    assert m.macros[10] == [(0x50, 20, 0x0A), (0xD0, 20, 0x0A)]
    assert BC.decode_block(m.buttons)[9].kind == "macro"
    assert "macro 10" in info["changed"]
    m.writes.clear()
    s.apply(want, {mac.id: mac}, {"allow": set()})        # already on the device: nothing rewritten
    assert m.writes == []


def test_dry_run_writes_nothing():
    m = FakeMouse()
    s = _session(m)
    want = _device_settings(m)
    want.dpi_stages[0].dpi = 3000
    info = s.apply(want, {}, {"allow": set(), "dry_run": True})
    assert m.writes == [] and info["dry_run"] and info["changed"] == ["settings"]


def test_a_sleeping_mouse_is_not_ready():
    m = FakeMouse()
    s = _session(m)
    m.link = False
    with pytest.raises(NotReady):
        s.apply(DeviceSettings(dpi_stages=[DpiStage(3000)]), {}, {})


def test_a_write_that_does_not_stick_is_reported():
    m = FakeMouse(drop_writes=True)
    s = _session(m)
    want = _device_settings(m)
    want.dpi_stages[0].dpi = 3000
    with pytest.raises(ApplyRefused):
        s.apply(want, {}, {"allow": set()})
    assert len(m.writes) == 2      # one write + one retry, then give up


def test_restore_refuses_a_snapshot_from_another_model():
    m = FakeMouse()
    s = _session(m)
    other = bytearray(m.settings)
    other[9] = 0x13
    with pytest.raises(ApplyRefused):
        s.restore({"settings.bin": bytes(other), "buttons.bin": m.buttons})
    assert m.writes == []


def test_seed_hands_the_profile_button_to_wyrm():
    s = _session()
    seed = s.seed_settings(s.read_state())
    assert seed.buttons[7].kind == "profile_next" and seed.polling_hz is None


def test_protocol_reads_on_fake():
    t = FakeTransport()
    assert P.identify(t) == "2911"
    assert P.battery(t).level == 43
    assert P.link_ok(t)


# --- the hub -------------------------------------------------------------------
def _hub(tmp_path, mouse=None):
    session = SinoWealthSession(FakeTransport(mouse or FakeMouse()), "sinowealth:258a:002f")
    w = DeviceWorker(tmp_path / "snap", registry=StaticRegistry({"m": SingleConnection(session)}))
    ev = {"devices": [], "states": [], "applied": [], "failed": [], "status": []}
    w.devices_changed.connect(lambda infos: ev["devices"].append(infos))
    w.device_state.connect(lambda uid, d: ev["states"].append(d))
    w.applied.connect(lambda uid, pid, info: ev["applied"].append(info))
    w.apply_failed.connect(lambda uid, pid, msg: ev["failed"].append(msg))
    w.status.connect(lambda uid, st: ev["status"].append(st))
    return w, ev


def test_hub_reports_a_new_mouse_and_reads_it(qapp, tmp_path):
    w, ev = _hub(tmp_path)
    w.poll()
    assert ev["devices"][-1][0].name == "Redragon M811 PRO"
    st = ev["states"][-1]
    assert st["reason"] == "connect" and st["seed"].buttons[7].kind == "profile_next"
    assert read_snapshot(tmp_path / "snap", M811_KEY)["settings.bin"] == st["snapshot"]["settings.bin"]
    assert ev["status"][-1]["battery"] == 43
    w.poll()
    assert len(ev["devices"]) == 1 and len(ev["states"]) == 1     # nothing new, nothing re-sent


def test_hub_queues_writes_for_a_sleeping_mouse(qapp, tmp_path):
    m = FakeMouse()
    w, ev = _hub(tmp_path, m)
    w.poll()
    m.link = False
    w.poll()
    want = _device_settings(m)
    want.dpi_stages[0].dpi = 3000
    w.apply("sinowealth:258a:002f", want, {}, {"allow": set()}, "p1")
    assert m.writes == [] and ev["status"][-1]["pending"]
    m.link = True
    w.poll()
    assert SC.decode(m.settings)["stages"][0].dpi == 3000 and ev["applied"][-1]["changed"] == ["settings"]
    assert (tmp_path / "snap" / "sinowealth-redragon-m811-pro" / "last_good_2911.settings.bin").exists()
    assert not ev["status"][-1]["pending"]


def test_hub_reports_refused_writes(qapp, tmp_path):
    m = FakeMouse(drop_writes=True)
    w, ev = _hub(tmp_path, m)
    w.poll()
    want = _device_settings(m)
    want.dpi_stages[0].dpi = 3000
    w.apply("sinowealth:258a:002f", want, {}, {"allow": set()}, "p1")
    assert ev["failed"] and "did not keep" in ev["failed"][0]


def test_hub_restores_the_original_snapshot(qapp, tmp_path):
    m = FakeMouse()
    w, ev = _hub(tmp_path, m)
    w.poll()
    original = m.settings
    want = _device_settings(m)
    want.dpi_stages[0].dpi = 3000
    w.apply("sinowealth:258a:002f", want, {}, {"allow": set()}, "p1")
    assert m.settings != original
    w.restore("sinowealth:258a:002f")
    assert m.settings == original and ev["applied"][-1]["restored"] is True


def test_v01_snapshots_move_into_the_m811_folder(tmp_path):
    root = tmp_path / "snap"
    root.mkdir()
    (root / "factory_2911.settings.bin").write_bytes(b"s")
    (root / "factory_2911.buttons.bin").write_bytes(b"b")
    DeviceWorker(root, registry=StaticRegistry({}))
    assert read_snapshot(root, M811_KEY) == {"settings.bin": b"s", "buttons.bin": b"b"}
