"""Wyrm entry point."""
from __future__ import annotations

import argparse
import copy
import getpass
import logging
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import __version__, log as wlog
from .core import winapi
from .core.device_service import DeviceService
from .core.model import Profile
from .core.profile_manager import ProfileManager
from .core.store import Store
from .paths import data_dir, sub

log = logging.getLogger("wyrm")
REASON_TEXT = {"auto": "Switched for {exe}", "manual": "Profile selected", "hotkey": "Mouse button",
               "startup": "Restored"}


def parse(argv):
    ap = argparse.ArgumentParser(prog="wyrm", description="Wyrm: Redragon M811 PRO control")
    ap.add_argument("--minimized", action="store_true", help="start in the tray")
    ap.add_argument("--demo", action="store_true", help="run against a simulated mouse")
    ap.add_argument("--cwd", help=argparse.SUPPRESS)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"Wyrm {__version__}")
    return ap.parse_args(argv)


def seed_from_device(store: Store, state: dict) -> None:
    """Fill the first profile from what's on the mouse, once."""
    from .core.model import ButtonAction
    if store.config.seeded or "settings" not in state:
        return
    p = store.ordered()[0]
    dec = state["settings"]
    p.dpi_stages = copy.deepcopy(dec["stages"])
    p.active_stage = dec["active_stage"]
    p.lighting = copy.deepcopy(dec["lighting"])
    buttons = copy.deepcopy(state["buttons"][:16])
    # The vendor "profile" action only worked with the vendor app; make it drive Wyrm instead.
    buttons = [ButtonAction("profile_next") if a.kind == "profile_cycle" else a for a in buttons]
    p.buttons = buttons
    store.save_profile(p)
    store.config.seeded = True
    store.save_config()
    log.info("seeded profile %s from the mouse", p.name)


def main(argv=None) -> int:
    # A windowed (no console) build has no stdout/stderr; give argparse somewhere to write.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    args = parse(sys.argv[1:] if argv is None else argv)
    if args.cwd:
        os.chdir(args.cwd)
    if args.demo:
        os.environ.setdefault("WYRM_DATA", str(data_dir() / "demo"))
    wlog.setup(args.verbose)
    log.info("Wyrm %s starting (demo=%s)", __version__, args.demo)

    app = QApplication(sys.argv)
    app.setApplicationName("Wyrm")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)

    # --- one instance per user ---------------------------------------------------------
    name = f"wyrm-{getpass.getuser()}" + ("-demo" if args.demo else "")
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)

    from .ui import theme
    from .ui.context import AppContext
    from .ui.main_window import MainWindow
    from .ui.shell import HotkeyWindow, Osd, Tray

    store = Store(data_dir())
    if not store.profiles:
        p = Profile(name="Default")
        store.save_profile(p)
        store.config.active_profile_id = store.config.default_profile_id = p.id
        store.save_config()

    theme.set_accent(store.config.accent)
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.stylesheet())
    app.setWindowIcon(theme.logo_icon())

    device = DeviceService(sub("snapshots"), demo=args.demo)
    manager = ProfileManager(store, device)
    ctx = AppContext(store, manager, device, demo=args.demo)
    win = MainWindow(ctx)
    manager.confirm_first_write = win.confirm_first_write
    tray = Tray(ctx, win)
    win.tray = tray
    tray.show()
    osd = Osd()
    hot = HotkeyWindow()
    hot.next.connect(lambda: manager.cycle(+1, "hotkey"))
    hot.prev.connect(lambda: manager.cycle(-1, "hotkey"))

    def on_active(p, reason):
        if store.config.osd and reason in ("auto", "hotkey", "manual") and not win.isActiveWindow():
            osd.show_profile(p.name, p.accent, REASON_TEXT.get(reason, "").format(exe=manager._last_exe))
    manager.active_changed.connect(on_active)

    def on_state(d: dict):
        if "error" in d:
            win.toast.pop(f"Unexpected mouse data, writes paused: {d['error']}", "bad")
            return
        if d.get("reason") != "connect":
            return
        seed_from_device(store, d)
        ctx.editing_changed.emit(ctx.editing(), None)
        manager.apply_active()
    device.device_state.connect(on_state)

    def on_conn():
        c = server.nextPendingConnection()
        c.readyRead.connect(lambda: (c.readAll(), win.show_and_raise()))
    server.newConnection.connect(on_conn)

    fg = QTimer(interval=400)
    fg.timeout.connect(lambda: manager.on_foreground(*winapi.foreground()))
    fg.start()
    device.start()
    if not (args.minimized and store.config.start_minimized):
        win.show()
    rc = app.exec()
    fg.stop()
    hot.unregister()
    device.shutdown()
    server.close()
    log.info("bye")
    return rc


if __name__ == "__main__":
    sys.exit(main())
