"""Render every page against the simulated mice and save PNGs (no window shown).

Usage: python tools/screenshot.py [out_dir]
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["WYRM_DATA"] = tempfile.mkdtemp(prefix="wyrm-shot-")

from PySide6.QtCore import QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from wyrm.core.device_service import DeviceService  # noqa: E402
from wyrm.core.model import AppRule, DeviceSettings, DpiStage, Macro, MacroEvent, Profile  # noqa: E402
from wyrm.core.profile_manager import ProfileManager  # noqa: E402
from wyrm.core.store import Store  # noqa: E402
from wyrm.paths import data_dir, sub  # noqa: E402


def pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    from wyrm.ui import theme
    from wyrm.ui.context import AppContext
    from wyrm.ui.main_window import PAGES, MainWindow

    store = Store(data_dir())
    p = Profile(name="Default")
    store.save_profile(p)
    store.config.active_profile_id = store.config.default_profile_id = p.id
    store.save_config()
    theme.set_accent(store.config.accent)
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.stylesheet())
    dev = DeviceService(sub("snapshots"), demo=True)
    pm = ProfileManager(store, dev)
    dev.devices_changed.connect(pm.set_devices)
    dev.device_state.connect(pm.on_device_state)
    ctx = AppContext(store, pm, dev, demo=True)
    win = MainWindow(ctx)
    pm.confirm_first_write = lambda info: True
    dev.start()
    pump(1500)
    # some content so pages aren't empty
    g = pm.create("Gaming")
    g.accent = "#e0263a"
    g.rules = [AppRule("cs2.exe"), AppRule("*valorant*.exe", priority=1)]
    g.devices["logitech/demo-mouse"] = DeviceSettings(dpi_stages=[DpiStage(800, True, (255, 255, 255))],
                                                      polling_hz=1000)
    pm.update_profile(g, apply=False)
    w = pm.create("Work")
    w.accent = "#2fa8ff"
    w.rules = [AppRule("code.exe"), AppRule("chrome.exe", "Figma")]
    pm.update_profile(w, apply=False)
    store.save_macro(Macro(name="GG", events=[MacroEvent("key_down", 0x28, 30), MacroEvent("key_up", 0x28, 40),
                                              MacroEvent("key_down", 0x0A, 20), MacroEvent("key_up", 0x0A, 20)]))
    pm.on_foreground("cs2.exe", "Counter-Strike 2", "", 4242)
    pm._resolve_foreground()
    pump(800)
    ctx.set_current("sinowealth/redragon-m811-pro")
    ctx.on_activity(0x258A, 0x002F)        # show the "In use" badge on the simulated M811
    ctx._decay.stop()

    win.setAttribute(Qt.WA_DontShowOnScreen)
    win.resize(1360, 900)
    win.show()
    for key, _ in PAGES:
        win.go(key)
        pump(500)
        win.grab().save(str(out / f"{key}.png"))
        print("saved", out / f"{key}.png")
    ctx.set_current("logitech/demo-mouse")
    win.go("performance")
    pump(500)
    win.grab().save(str(out / "performance_hidpp.png"))
    # dialogs and the toast
    from wyrm.ui.action_picker import ActionPicker
    from wyrm.ui.shell import Osd
    ctx.set_current("sinowealth/redragon-m811-pro")
    acts = ctx.effective_buttons(ctx.device_settings()[0])
    dlg = ActionPicker("Side 1", acts[8], store.macros, win)
    dlg.setAttribute(Qt.WA_DontShowOnScreen)
    dlg.show()
    pump(200)
    dlg.grab().save(str(out / "action_picker.png"))
    dlg.close()
    osd = Osd()
    osd.setAttribute(Qt.WA_DontShowOnScreen)
    osd.show_profile("Gaming", "#e0263a", "Switched for cs2.exe")
    pump(250)
    osd.grab().save(str(out / "osd.png"))
    print("saved dialogs")
    dev.shutdown()


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "captures" / "screens")
