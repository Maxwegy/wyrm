# Adding a mouse

There are three ways in, from least to most work:

1. **Report it.** Run `python tools/list_devices.py --probe` (read-only) and open a
   [New mouse issue](https://github.com/Maxwegy/wyrm/issues/new?template=new-mouse.yml) with the output. That
   alone tells us which chip and protocol the mouse uses.
2. **A sibling of a supported mouse.** Many budget mice share a chip and only differ in their byte map. For those,
   new support is a model file. See [SinoWealth model files](#sinowealth-model-files).
3. **A new family.** A new driver package under `wyrm/drivers/`. See [Writing a driver](#writing-a-driver).

Whatever you add has to follow [the safety rules](#safety-rules).

## SinoWealth model files

Mice that answer on `258a:002e` / `258a:002f` with the SinoWealth wireless framing (commands on report 5, blocks on
report 8) are matched by a **model marker** in their settings block. Each known model is one JSON file in
`wyrm/drivers/sinowealth/models/`:

- `key`, `name`, `vendor`: how the mouse is stored in profiles and shown in the UI.
- `support`: `full`, `basic` or `detected`. A `detected` file only names the mouse.
- `identity`: where the model marker lives and its value. Wyrm refuses to write any block that doesn't carry it.
- `settings_len`, `buttons_len`, `trailer`: the block shapes.
- The byte map: `polling`, `stages`, `dpi`, `stage_color`, `effect`, `effect_params`, `buttons`,
  `consumer_bits`, `default_buttons`. Fields with `"verified": false` are only written with experimental writes on.

To build one:

1. Dump the blocks with `python tools/sinowealth/dump_blocks.py baseline`. It's read-only.
2. Change one setting in the vendor app, dump again, and diff. Repeat for each setting.
3. The vendor app's `Cfg.ini` (in its install folder) lists the sensor, DPI range and default stages, and how many
   buttons there are. That's a good start for `dpi` and `buttons`.
4. Copy `m811pro.json`, adjust it, and add a test that decodes your dump.
5. Check write framing on your mouse with `python tools/sinowealth/write_selftest.py`. It makes one reversible
   change and restores the block.

## Writing a driver

A driver lives in `wyrm/drivers/<family>/` and implements three small types from
[`wyrm/drivers/base.py`](../wyrm/drivers/base.py):

- **`Driver`**: `discover(entries)` picks its devices out of one `hid.enumerate()` listing **without any I/O**, and
  `open(candidate)` probes and opens one. Return `None` from `open` if the device doesn't answer: the generic
  driver then shows it, and the registry probes again later, waiting longer each time.
- **`Connection`**: what `open` returns. `sessions()` lists the mice behind it. A receiver can gain and lose mice,
  and `refresh()` is called every poll so it can look.
- **`DeviceSession`**: one mouse.
  - `info`: a `DeviceInfo`, with name, model key, connection, support level and `Capabilities`. The capabilities
    say what the UI may offer: DPI range and stage count, polling rates, button names, effects, macro slots,
    battery.
  - `poll()`: cheap status (awake, battery).
  - `read_state()`: decode the current settings into a `DeviceSettings`, plus raw snapshot bytes for the backup.
  - `apply(settings, macros, opts)`: read, change only what you understand, write, read back, and return
    `{"changed": [...], "skipped": [...], "dry_run": bool}`. Raise `NotReady` when the mouse is asleep, so the
    write waits. Raise `ApplyRefused` with a readable message when a write is refused or didn't stick.
  - `restore(snapshot)`, `seed_settings(state)`, `shutdown()`.

Register the driver in `wyrm/drivers/__init__.py`, before `GenericDriver`. Everything else is shared: profiles,
auto-switch, the UI pages (they follow the capabilities), snapshots, the first-write prompt and the tray.

### Simulated devices

Every driver ships a fake (`sinowealth/fake.py`, `logitech/fake.py`). It answers like the hardware and fails loudly
on anything the real device would reject, or anything off the allow-list. Tests run against it, and so does
`python -m wyrm --demo`. Add yours to `demo_registry()` so others can try the UI without your mouse.

## Safety rules

- **Allow-list every command.** Write down the exact commands or features the driver may send. Firmware update,
  bootloader and reset commands must be impossible to send (see `FORBIDDEN_CMDS` and `hidpp.ALLOWED`).
- **Read before you write**, and change only the bytes you understand. Leave everything else exactly as read.
- **Check identity.** Never write a block or profile that doesn't match the model you think you're talking to.
- **Verify** every write by reading it back, and report failure.
- **Unverified means opt-in.** Anything not confirmed on real hardware goes in `Capabilities.unverified`, or is
  gated on `opts["experimental"]`.
- **No network.** Wyrm is offline by design.
