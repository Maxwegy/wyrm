<p align="center">
  <img src="docs/img/home.png" alt="Wyrm home screen with two mice" width="860">
</p>

# Wyrm

🥚 Just want it working? [Wyrm.exe ↓](https://github.com/Maxwegy/wyrm/releases/latest/download/Wyrm.exe). Save it, run it, done. (Windows may say “unrecognized app”: click More info → Run anyway.)

**One open-source, offline app for all your mice.**

Every mouse brand ships its own app, and most of them are heavy, online and awkward. Wyrm talks to your mice
directly over USB HID instead. It gives you **one set of profiles for every mouse you own**: Gaming, Work,
Editing, each with its own DPI, buttons, lighting and macros. It switches all your mice together when a game or
app comes to the front.

Plug in a mouse and Wyrm shows it by name, with its battery and how it's connected. Move it and its card lights up
**In use**. Wyrm configures the mice it has a driver for, and still lists every other mouse.

> Not affiliated with or endorsed by any mouse maker. Brand and model names only say which hardware Wyrm works with.

## Supported mice

| Mouse | Support | What Wyrm can do |
|---|---|---|
| **Redragon M811 PRO** (receiver or USB-C cable) | ✅ Full | DPI stages and colours, buttons, macros, lighting, battery, polling rate (after a quick test) |
| **Logitech mice with HID++ 2.0** (Lightspeed, Unifying, Bolt receiver or cable) | 🔷 Basic | Name, battery, DPI and polling rate. Not yet tested on real hardware: [reports welcome](../../issues/new?template=new-mouse.yml) |
| **Redragon M690 PRO** | 👀 Detected | Name, battery and connection. Help wanted to map its DPI table |
| Other SinoWealth wireless mice (`258a:002e` / `002f`) | 👀 Detected | Shown with their model marker, never written |
| **Any other mouse** | 👀 Detected | Shown by name so you can see it's there |

Details and what each level means: [docs/devices.md](docs/devices.md). Your mouse isn't on the list?
[Add it](docs/adding-a-device.md). Many budget mice share a chip with one already supported, so a new model can be
a single JSON file.

## Features

- **Profiles per activity that cover all your mice.** A profile sets each mouse it cares about. Any mouse it
  doesn't set follows the default profile, so adding a second mouse never breaks the profiles you already have.
- **Auto-switch by app.** Link `cs2.exe`, `*valorant*.exe` or `chrome.exe` (only when the title contains
  "Figma"), and Wyrm switches the moment that window is in front. Priorities break ties.
- **Switch from the mouse.** Put "next/previous profile" on any button, and a toast shows which profile is on.
- **See every mouse.** Name, connection, battery, asleep/awake and a live **In use** badge for the one you're
  moving. Wyrm warns when another vendor app is running that could overwrite the same settings.
- **DPI:** stages, colours and the default stage, within each mouse's real range and step.
- **Buttons:** mouse clicks, key combos, media keys, DPI controls, rapid fire, macros or profile switching,
  picked from a clickable diagram.
- **Lighting:** effects with a live animated preview, plus brightness, speed and colours.
- **Macros:** record keys and clicks with real timing, or edit the steps by hand. They're stored on the mouse and
  work everywhere.
- **Tray app** with a quick profile menu and every mouse's battery. Starts with Windows if you like.
- **Polling-rate tester** that measures any mouse's real report rate with Windows Raw Input.
- **Offline by design.** Wyrm makes no network calls: no telemetry, no update checks, no account.

| | |
|---|---|
| ![Profiles](docs/img/profiles.png) | ![Buttons](docs/img/buttons.png) |
| ![Performance](docs/img/performance.png) | ![Lighting](docs/img/lighting.png) |

## Install

**Download:** grab `Wyrm.exe` from [Releases](../../releases) and run it. It's a single file, so put it
anywhere. `Wyrm-windows.zip` is the same app unpacked into a folder, which starts a little faster.

**Build it yourself:** `powershell -File packaging\build.ps1` puts a fresh `Wyrm.exe` in the project folder.

**From source** (Python 3.10+):

```bash
git clone https://github.com/Maxwegy/wyrm.git
cd wyrm
python -m pip install -e .
python -m wyrm
```

`python -m wyrm --demo` runs the whole app against two simulated mice (a Redragon M811 PRO and a HID++ mouse),
which is handy for poking around or developing without the hardware.

You don't need to uninstall your mouse's own app, but don't run both at the same time. Each one rewrites the
mouse when it switches profiles. Wyrm shows a hint on the mouse's card when it spots one running.

## First run

1. Wyrm finds your mice. For each mouse it can configure, it saves a **snapshot of the current settings**.
   **Settings → Restore original settings** writes it back.
2. Each mouse's current setup goes into the **Default** profile, so nothing changes until you change it.
3. Before the first write to each mouse, Wyrm asks for permission.
4. Create profiles on the **Profiles** page and link apps to them. Pick which mouse to edit at the top of the
   Performance, Buttons and Lighting pages. Turn on **Start with Windows** in Settings so auto-switch always works.

Upgrading from 0.1? Your profiles move over automatically (they become the M811 PRO's settings), and the
originals are copied to `%LOCALAPPDATA%\Wyrm\backup-v1`.

## How safe is it?

Wyrm writes to a mouse the same way its vendor app does, but more defensively:

- **Allow-lists, not block-lists.** Each driver can only send the commands it knows. SinoWealth firmware-update
  (DFU) commands and Logitech firmware-update and reset features can't be sent at all.
- **Refuses unknown hardware.** A SinoWealth mouse is only written when its settings block carries a model marker
  Wyrm knows. Unknown models are shown and never written.
- **Check before write.** It reads the current settings first, changes only what it understands, and leaves
  everything else exactly as it was.
- **Verifies every write** by reading it back, and tells you if it didn't stick.
- **Skips no-op writes** and **waits for sleeping mice**: changes are queued until the mouse wakes.
- **Experimental is opt-in.** Anything not yet confirmed on real hardware is off until you enable "Experimental
  writes".
- **Dry run.** Settings has a mode that logs what Wyrm would write without sending it.

### What's verified

**Redragon M811 PRO** (firmware 2911, receiver), including write and read-back: DPI stages, stage colours and the
default stage; button blocks (mouse buttons, keys and combos, DPI ±, the Profile button); macro storage; battery
and sleep detection. Encoded per the SinoWealth protocol but not yet confirmed by pressing the button: macro
playback, media keys, rapid fire, sniper DPI, lighting on/off. Behind "Experimental writes": polling-rate changes
(the **Test polling rate** button unlocks them when the measurement matches), lighting effects other than
Colorful Streaming, Steady and Breathing, and disabling DPI stages.

**Logitech HID++ 2.0**: implemented from the public HID++ 2.0 feature descriptions and libratbag's notes, and
tested against a simulated device. Nobody has run it on real Logitech hardware yet. Many G-series mice run from
an **on-board profile**. While they do, Wyrm only reads their DPI and polling rate. With experimental writes on,
Wyrm switches the mouse to host mode and puts it back on its on-board profile when Wyrm quits.

Byte-level notes: [SinoWealth wireless](docs/protocols/sinowealth-wireless.md) ·
[Logitech HID++](docs/protocols/logitech-hidpp.md). Dumps and reports for the open questions are very welcome.

## Add your mouse

1. Run `python tools/list_devices.py --probe` (read-only) and open a
   [New mouse issue](../../issues/new?template=new-mouse.yml) with the output.
2. If you'd like to write the support yourself, [docs/adding-a-device.md](docs/adding-a-device.md) walks through
   the driver interface, model files, safety rules and the simulated devices the tests use.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest                       # codecs, drivers, migration, profiles, the device hub, against simulated mice
python tools/screenshot.py             # render every page to captures/screens/
powershell -File packaging/build.ps1   # build Wyrm.exe into the project folder
```

Layout:

- `wyrm/drivers`: one package per mouse family behind a small interface (`base.py`), plus a registry that finds
  mice and a generic fallback that shows any other mouse.
  - `sinowealth/`: the SinoWealth wireless protocol, with each model's byte map as data in `models/*.json`.
  - `logitech/`: HID++ 2.0 framing, feature calls and a simulated device.
- `wyrm/core`: profiles (one per activity, settings per mouse model), auto-switch rules, the device thread,
  Windows helpers.
- `wyrm/ui`: the PySide6 app.
- `tools`: `list_devices.py`, and per-family discovery and debugging scripts.

## Credits

Protocol knowledge builds on [libratbag](https://github.com/libratbag/libratbag) (MIT) and the public
[OpenMouse M690 PRO notes](https://github.com/OpenMouse-Project/mouse-protocol). Wyrm uses no code from either
project.

## License

[MIT](LICENSE)
