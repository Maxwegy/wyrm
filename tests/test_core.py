import copy

from wyrm.core.device_service import DeviceWorker
from wyrm.core.model import AppRule, ButtonAction, DpiStage, Macro, MacroEvent, Profile
from wyrm.core.rules import resolve
from wyrm.core.store import Store
from wyrm.hid import protocol as P
from wyrm.hid.codec import buttons as BC
from wyrm.hid.codec import settings as SC
from wyrm.hid.fake import FakeMouse, FakeTransport


# --- rules -------------------------------------------------------------------
def test_rules_match_case_insensitive_and_wildcards():
    game = Profile(name="Game", rules=[AppRule("CS2.exe")])
    web = Profile(name="Web", rules=[AppRule("*chrome*")])
    ps = [game, web]
    assert resolve(ps, "cs2.exe", "") is game
    assert resolve(ps, "chrome.exe", "YouTube") is web
    assert resolve(ps, "notepad.exe", "") is None


def test_rules_priority_and_title_specificity():
    a = Profile(name="A", rules=[AppRule("chrome.exe")])
    b = Profile(name="B", rules=[AppRule("chrome.exe", title_contains="figma")])
    c = Profile(name="C", rules=[AppRule("chrome.exe", priority=5)])
    assert resolve([a, b], "chrome.exe", "Figma - design") is b
    assert resolve([a, b], "chrome.exe", "Mail") is a
    assert resolve([a, b, c], "chrome.exe", "Figma") is c


# --- store -------------------------------------------------------------------
def test_store_roundtrip(tmp_path):
    s = Store(tmp_path)
    p = Profile(name="Gaming", rules=[AppRule("game.exe")])
    s.save_profile(p)
    s.save_macro(Macro(name="hi", events=[MacroEvent("key_down", 4, 10)]))
    s.config.auto_switch = False
    s.save_config()
    s2 = Store(tmp_path)
    assert s2.profiles[p.id] == p
    assert list(s2.macros.values())[0].name == "hi"
    assert s2.config.auto_switch is False
    assert s2.config.profile_order == [p.id]


def test_store_keeps_last_profile(tmp_path):
    import pytest
    s = Store(tmp_path)
    p = Profile()
    s.save_profile(p)
    with pytest.raises(ValueError):
        s.delete_profile(p.id)


# --- device worker against the fake mouse -----------------------------------
def _worker(tmp_path, mouse=None):
    w = DeviceWorker(tmp_path / "snap")
    w.t = FakeTransport(mouse or FakeMouse())
    w.link = True
    w.fw = "2911"
    events = {"applied": [], "failed": [], "state": []}
    w.applied.connect(lambda pid, info: events["applied"].append(info))
    w.apply_failed.connect(lambda pid, msg: events["failed"].append(msg))
    w.device_state.connect(lambda d: events["state"].append(d))
    return w, events


def _device_profile(mouse: FakeMouse) -> Profile:
    d = SC.decode(mouse.settings)
    return Profile(dpi_stages=d["stages"], active_stage=d["active_stage"],
                   buttons=BC.decode_block(mouse.buttons), lighting=d["lighting"])


def test_apply_identical_profile_writes_nothing(qapp, tmp_path):
    m = FakeMouse()
    w, ev = _worker(tmp_path, m)
    w.apply(_device_profile(m), {}, {"allow": set()})
    assert m.writes == []
    assert ev["applied"][0] == {"settings": False, "buttons": False, "macros": 0, "dry_run": False}


def test_apply_dpi_and_button_change(qapp, tmp_path):
    m = FakeMouse()
    w, ev = _worker(tmp_path, m)
    p = _device_profile(m)
    p.dpi_stages[0] = DpiStage(1600, True, (255, 0, 0))
    p.buttons[7] = ButtonAction("profile_next")
    w.apply(p, {}, {"allow": set()})
    assert not ev["failed"]
    assert SC.decode(m.settings)["stages"][0].dpi == 1600
    assert BC.decode_block(m.buttons)[7].kind == "profile_next"
    assert len(m.writes) == 2
    assert (tmp_path / "snap" / "last_good_2911.settings.bin").exists()


def test_apply_writes_macro_to_button_slot(qapp, tmp_path):
    m = FakeMouse()
    w, ev = _worker(tmp_path, m)
    mac = Macro(name="gg", events=[MacroEvent("key_down", 0x0A, 20), MacroEvent("key_up", 0x0A, 20)])
    p = _device_profile(m)
    p.buttons[9] = ButtonAction("macro", macro_id=mac.id, macro_mode=1, count=1)
    w.apply(p, {mac.id: mac}, {"allow": set()})
    assert m.macros[10] == [(0x50, 20, 0x0A), (0xD0, 20, 0x0A)]
    assert BC.decode_block(m.buttons)[9].kind == "macro"
    assert ev["applied"][0]["macros"] == 1
    # second apply: macro already on the device, nothing rewritten
    m.writes.clear()
    w.apply(p, {mac.id: mac}, {"allow": set()})
    assert m.writes == []


def test_dry_run_writes_nothing(qapp, tmp_path):
    m = FakeMouse()
    w, ev = _worker(tmp_path, m)
    p = _device_profile(m)
    p.dpi_stages[0].dpi = 3000
    w.apply(p, {}, {"allow": set(), "dry_run": True})
    assert m.writes == []
    assert ev["applied"][0]["dry_run"] is True


def test_sleeping_mouse_queues_apply(qapp, tmp_path):
    m = FakeMouse(link=False)
    w, ev = _worker(tmp_path, m)
    p = _device_profile(m)
    p.dpi_stages[0].dpi = 3000
    w.apply(p, {}, {"allow": set()})
    assert m.writes == [] and w._pending is not None
    m.link = True
    w.poll()
    assert SC.decode(m.settings)["stages"][0].dpi == 3000
    assert w._pending is None


def test_wrong_identity_refuses_without_writing(qapp, tmp_path):
    m = FakeMouse()
    bad = bytearray(m.settings)
    bad[9] = 0x13
    m.settings = bytes(bad)
    w, ev = _worker(tmp_path, m)
    p = Profile()
    p.dpi_stages[0].dpi = 3000
    w.apply(p, {}, {"allow": set()})
    assert m.writes == [] and ev["failed"]


def test_write_that_does_not_stick_is_reported(qapp, tmp_path):
    m = FakeMouse(drop_writes=True)
    w, ev = _worker(tmp_path, m)
    p = _device_profile(m)
    p.dpi_stages[0].dpi = 3000
    w.apply(p, {}, {"allow": set()})
    assert ev["failed"] and len(m.writes) == 2   # one write + one retry, then give up


def test_protocol_reads_on_fake():
    t = FakeTransport()
    assert P.identify(t) == "2911"
    assert P.battery(t).level == 43
    assert P.link_ok(t)


# --- profile manager ---------------------------------------------------------
class _StubDevice:
    def __init__(self):
        self.calls = []

    def apply(self, p, macros, opts):
        self.calls.append(copy.deepcopy(p))


def _manager(tmp_path):
    from wyrm.core.profile_manager import ProfileManager
    s = Store(tmp_path)
    work = Profile(name="Work")
    game = Profile(name="Game", rules=[AppRule("game.exe")])
    for p in (work, game):
        s.save_profile(p)
    s.config.active_profile_id = work.id
    s.config.default_profile_id = work.id
    s.config.first_write_ok = True
    dev = _StubDevice()
    pm = ProfileManager(s, dev)
    return pm, dev, work, game


def test_auto_switch_follows_foreground(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    pm.on_foreground("game.exe", "Game", "C:/g/game.exe", 1234)
    pm._resolve_foreground()
    assert pm.active().id == game.id
    pm.on_foreground("notepad.exe", "Untitled", "C:/n.exe", 99)
    pm._resolve_foreground()
    assert pm.active().id == work.id
    assert [c.name for c in dev.calls] == ["Game", "Work"]


def test_manual_switch_holds_until_app_changes(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    pm.on_foreground("game.exe", "Game", "", 1234)
    pm._resolve_foreground()
    pm.switch(work.id, "hotkey")            # user overrides inside the game
    pm._resolve_foreground()
    assert pm.active().id == work.id        # held
    pm.on_foreground("chrome.exe", "Mail", "", 5)
    pm._resolve_foreground()
    pm.on_foreground("game.exe", "Game", "", 1234)
    pm._resolve_foreground()
    assert pm.active().id == game.id        # hold released once the app changed


def test_own_window_and_desktop_are_ignored(qapp, tmp_path):
    import os
    pm, dev, work, game = _manager(tmp_path)
    pm.on_foreground("game.exe", "Game", "", 1234)
    pm._resolve_foreground()
    pm.on_foreground("python.exe", "Wyrm", "", os.getpid())
    pm.on_foreground("explorer.exe", "Program Manager", "", 4)
    pm._resolve_foreground()
    assert pm.active().id == game.id


def test_first_write_needs_confirmation(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    pm.store.config.first_write_ok = False
    blocked = []
    pm.write_blocked.connect(blocked.append)
    pm.apply_active()
    assert dev.calls == [] and blocked
    asked = []
    pm.confirm_first_write = lambda: asked.append(1) or True
    pm.apply_active()                      # background apply (e.g. mouse woke): don't nag again
    assert asked == [] and dev.calls == []
    pm.apply_active(user=True)             # the user changed something: ask again
    assert asked == [1] and len(dev.calls) == 1 and pm.store.config.first_write_ok


def test_cycle_wraps(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    pm.cycle(+1)
    assert pm.active().id == game.id
    pm.cycle(+1)
    assert pm.active().id == work.id
