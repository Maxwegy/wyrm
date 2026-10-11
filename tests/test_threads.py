"""The device hub on its own thread, wired the way app.py wires it."""
import time

from wyrm.core.device_service import DeviceService
from wyrm.core.model import M811_KEY, Profile
from wyrm.core.profile_manager import ProfileManager
from wyrm.core.store import Store
from wyrm.drivers import demo_registry


def test_new_mice_seed_the_default_profile_even_when_the_ui_is_busy(qapp, tmp_path):
    store = Store(tmp_path)
    p = Profile(name="Default")
    store.save_profile(p)
    store.config.active_profile_id = store.config.default_profile_id = p.id
    dev = DeviceService(tmp_path / "snap", registry=demo_registry())
    pm = ProfileManager(store, dev)
    dev.devices_changed.connect(pm.set_devices)
    dev.device_state.connect(pm.on_device_state)
    applied = []
    dev.applied.connect(lambda uid, pid, info: applied.append(uid))
    dev.start()
    time.sleep(0.5)      # the main thread is busy (building the window) while the hub reports both mice
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and len(set(applied)) < 2:
        qapp.processEvents()
        time.sleep(0.01)
    dev.shutdown()
    assert set(store.config.seeded_models) == {M811_KEY, "logitech/demo-mouse"}
    assert set(store.profiles[p.id].devices) == {M811_KEY, "logitech/demo-mouse"}
    assert set(applied) == {"demo:sinowealth", "demo:logitech#255"}
