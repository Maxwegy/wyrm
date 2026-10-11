import copy
import shutil
from pathlib import Path

import pytest

from wyrm.core.model import (M811_KEY, AppRule, ButtonAction, DeviceSettings, DpiStage, Macro, MacroEvent, Profile,
                             effective_settings)
from wyrm.core.rules import resolve
from wyrm.core.store import Store
from wyrm.drivers.base import Capabilities, DeviceInfo

V1 = Path(__file__).parent / "fixtures" / "v1"
LOGI = "logitech/demo-mouse"


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
    p = Profile(name="Gaming", rules=[AppRule("game.exe")],
                devices={M811_KEY: DeviceSettings(polling_hz=500, dpi_stages=[DpiStage(1600)])})
    s.save_profile(p)
    s.save_macro(Macro(name="hi", events=[MacroEvent("key_down", 4, 10)]))
    s.config.auto_switch = False
    s.config.verified[M811_KEY] = ["polling"]
    s.save_config()
    s2 = Store(tmp_path)
    assert s2.profiles[p.id] == p
    assert list(s2.macros.values())[0].name == "hi"
    assert s2.config.auto_switch is False
    assert s2.config.profile_order == [p.id]
    assert s2.config.allow(M811_KEY) == {"polling"} and s2.config.allow(LOGI) == set()


def test_store_keeps_last_profile(tmp_path):
    s = Store(tmp_path)
    p = Profile()
    s.save_profile(p)
    with pytest.raises(ValueError):
        s.delete_profile(p.id)


def test_v1_data_migrates_to_per_mouse_settings(tmp_path):
    shutil.copytree(V1, tmp_path, dirs_exist_ok=True)
    s = Store(tmp_path)
    default = s.profiles["11111111111111111111111111111111"]
    gaming = s.profiles["22222222222222222222222222222222"]
    m = default.devices[M811_KEY]
    assert [st.dpi for st in m.dpi_stages] == [800, 1600, 3200, 6400, 26000] and m.active_stage == 1
    assert m.lighting.effect == "steady" and m.lighting.color == (0, 128, 255)
    assert m.buttons[7].kind == "profile_next" and len(m.buttons) == 16
    assert gaming.devices[M811_KEY].polling_hz == 1000 and gaming.devices[M811_KEY].lighting is None
    assert gaming.rules == [AppRule("cs2.exe", "", 1)]
    cfg = s.config
    assert cfg.write_ok_models == [M811_KEY] and cfg.seeded_models == [M811_KEY]
    assert cfg.verified == {M811_KEY: ["polling"]} and cfg.accent == "frost" and cfg.schema == 2
    # the originals are kept, and the files on disk are schema 2 now
    assert (tmp_path / "backup-v1" / "config.json").exists()
    assert (tmp_path / "backup-v1" / "profiles" / f"{gaming.id}.json").exists()
    again = Store(tmp_path)
    assert again.profiles[gaming.id] == gaming and again.config.write_ok_models == [M811_KEY]


def test_effective_settings_follow_the_default_profile():
    mine = DeviceSettings(dpi_stages=[DpiStage(800)])
    theirs = DeviceSettings(dpi_stages=[DpiStage(3200)])
    default = Profile(name="Default", devices={M811_KEY: theirs, LOGI: theirs})
    gaming = Profile(name="Gaming", devices={M811_KEY: mine})
    assert effective_settings(gaming, default, M811_KEY) is mine
    assert effective_settings(gaming, default, LOGI) is theirs
    assert effective_settings(gaming, default, "generic/1234-5678-mouse") is None


def test_known_mice_are_remembered(tmp_path):
    s = Store(tmp_path)
    info = _info("logitech:c539:-#1", LOGI, "Logitech Demo Mouse", dpi=1)
    s.remember(info)
    s.remember(_info("generic:1:2:x", "generic/x", "Some mouse", dpi=0))   # unconfigurable mice aren't kept
    back = Store(tmp_path).known_info(LOGI)
    assert back.name == "Logitech Demo Mouse" and back.caps.dpi_stages == 1 and back.uid == ""
    assert "generic/x" not in s.known


# --- profile manager ---------------------------------------------------------
def _info(uid, key, name, dpi=5, demo=False, driver="logitech"):
    caps = Capabilities(dpi_min=50, dpi_max=26000, dpi_step=50, dpi_stages=dpi) if dpi else Capabilities()
    return DeviceInfo(uid=uid, key=key, name=name, vendor=name.split()[0], driver=driver if dpi else "generic",
                      support="full" if dpi else "detected", caps=caps, demo=demo)


class _StubDevice:
    def __init__(self):
        self.calls = []

    def apply(self, uid, settings, macros, opts, profile_id=""):
        self.calls.append((uid, copy.deepcopy(settings), opts, profile_id))


def _manager(tmp_path):
    from wyrm.core.profile_manager import ProfileManager
    s = Store(tmp_path)
    work = Profile(name="Work", devices={M811_KEY: DeviceSettings(dpi_stages=[DpiStage(800)])})
    game = Profile(name="Game", rules=[AppRule("game.exe")],
                   devices={M811_KEY: DeviceSettings(dpi_stages=[DpiStage(3200)])})
    for p in (work, game):
        s.save_profile(p)
    s.config.active_profile_id = work.id
    s.config.default_profile_id = work.id
    s.config.write_ok_models = [M811_KEY, LOGI]
    dev = _StubDevice()
    pm = ProfileManager(s, dev)
    pm.set_devices([_info("sino", M811_KEY, "Redragon M811 PRO", driver="sinowealth")])
    return pm, dev, work, game


def test_auto_switch_follows_foreground(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    pm.on_foreground("game.exe", "Game", "C:/g/game.exe", 1234)
    pm._resolve_foreground()
    assert pm.active().id == game.id
    pm.on_foreground("notepad.exe", "Untitled", "C:/n.exe", 99)
    pm._resolve_foreground()
    assert pm.active().id == work.id
    assert [c[1].dpi_stages[0].dpi for c in dev.calls] == [3200, 800]


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


def test_one_profile_drives_every_mouse(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    work.devices[LOGI] = DeviceSettings(dpi_stages=[DpiStage(1200)], polling_hz=500)
    pm.store.save_profile(work)
    pm.set_devices([_info("sino", M811_KEY, "Redragon M811 PRO", driver="sinowealth"),
                    _info("logi", LOGI, "Logitech Demo Mouse", dpi=1),
                    _info("other", "generic/x", "Some mouse", dpi=0)])
    pm.switch(game.id, "manual")
    calls = {uid: (s, pid) for uid, s, opts, pid in dev.calls}
    assert calls["sino"][0].dpi_stages[0].dpi == 3200          # Game's own settings
    assert calls["logi"][0].dpi_stages[0].dpi == 1200          # Game doesn't set it: follows Work (default)
    assert "other" not in calls                                 # nothing to write to an unsupported mouse
    assert calls["sino"][1] == game.id
    dev.calls.clear()
    pm.apply_active(only_uid="logi")
    assert [c[0] for c in dev.calls] == ["logi"]


def test_seed_fills_the_default_profile_once(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    logi = _info("logi", LOGI, "Logitech Demo Mouse", dpi=1)
    assert pm.seed(logi, DeviceSettings(dpi_stages=[DpiStage(1600)]))
    assert pm.store.profiles[work.id].devices[LOGI].dpi_stages[0].dpi == 1600
    assert LOGI not in game.devices
    assert not pm.seed(logi, DeviceSettings(dpi_stages=[DpiStage(400)]))         # only the first time
    assert pm.store.profiles[work.id].devices[LOGI].dpi_stages[0].dpi == 1600
    assert not pm.seed(_info("x", "generic/x", "Some mouse", dpi=0), DeviceSettings())


def test_new_profiles_follow_default_and_duplicates_copy(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    fresh = pm.create("Editing")
    assert fresh.devices == {} and fresh.rules == []
    dup = pm.create("Game copy", game)
    assert dup.devices == game.devices and dup.rules == [] and dup.id != game.id


def test_first_write_needs_confirmation_per_mouse(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    pm.store.config.write_ok_models = []
    blocked = []
    pm.write_blocked.connect(blocked.append)
    pm.apply_active()
    assert dev.calls == [] and blocked and "M811 PRO" in blocked[0]
    asked = []
    pm.confirm_first_write = lambda info: asked.append(info.key) or True
    pm.apply_active()                      # background apply (e.g. mouse woke): don't nag again
    assert asked == [] and dev.calls == []
    pm.apply_active(user=True)             # the user changed something: ask again
    assert asked == [M811_KEY] and len(dev.calls) == 1
    assert pm.store.config.write_ok_models == [M811_KEY]
    # a second, different mouse asks for itself
    work.devices[LOGI] = DeviceSettings(dpi_stages=[DpiStage(1200)])
    pm.set_devices(list(pm.devices.values()) + [_info("logi", LOGI, "Logitech Demo Mouse", dpi=1)])
    pm.apply_active()
    assert asked == [M811_KEY, LOGI]


def test_dry_run_and_demo_mice_never_ask(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    pm.store.config.write_ok_models = []
    pm.confirm_first_write = lambda info: pytest.fail("asked")
    pm.set_devices([_info("demo", M811_KEY, "Redragon M811 PRO", demo=True, driver="sinowealth")])
    pm.apply_active()
    assert len(dev.calls) == 1
    pm.store.config.dry_run = True
    pm.set_devices([_info("sino", M811_KEY, "Redragon M811 PRO", driver="sinowealth")])
    pm.apply_active()
    assert dev.calls[-1][2]["dry_run"] is True


def test_cycle_wraps(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    pm.cycle(+1)
    assert pm.active().id == game.id
    pm.cycle(+1)
    assert pm.active().id == work.id


def test_editing_the_default_profile_reapplies(qapp, tmp_path):
    pm, dev, work, game = _manager(tmp_path)
    pm.switch(game.id, "manual")
    dev.calls.clear()
    work.devices[M811_KEY] = DeviceSettings(buttons=[ButtonAction.mouse(1)])
    pm.update_profile(work)                 # Work is the default: Game may follow it for some mice
    assert pm._apply_timer.isActive()
