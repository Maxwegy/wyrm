# Contributing to Wyrm

Thanks for helping. The most useful things right now:

- **Reports from real mice.** Run `python tools/list_devices.py --probe` (read-only) and open a
  [New mouse issue](https://github.com/Maxwegy/wyrm/issues/new?template=new-mouse.yml). Logitech owners: say
  whether DPI and polling-rate changes stick.
- **Model files** for SinoWealth siblings, and **new drivers.** See [docs/adding-a-device.md](docs/adding-a-device.md).
- **Answers to the open questions** in [docs/devices.md](docs/devices.md#help-wanted).

## Ground rules

- Wyrm stays offline: no network calls, no telemetry, no update checks.
- Device code follows [the safety rules](docs/adding-a-device.md#safety-rules): allow-listed commands, read before
  write, identity checks, read-back verification, and unverified writes behind "Experimental writes".
- Don't copy code from GPL or AGPL projects. Protocol facts are fine; credit the source in the docs.
- Every driver comes with a simulated device, and tests that run without hardware.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m wyrm --demo        # the whole app against simulated mice
python tools/screenshot.py   # render every page to captures/screens/
```

Keep pull requests focused, and include a dump or a log for anything that touches the device protocol.
