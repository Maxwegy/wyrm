# Supported mice

Wyrm shows every mouse plugged into your PC. How much it can do with one depends on its driver.

| Level | What it means |
|---|---|
| ✅ **Full** | Verified on real hardware: settings are read, written and read back. Anything not yet confirmed sits behind "Experimental writes". |
| 🔷 **Basic** | Wyrm can read and set the basics (DPI, polling rate, battery). The rest of the mouse is left alone. |
| 👀 **Detected** | Wyrm sees the mouse and shows it by name, but never writes to it. |

## Mice

| Mouse | IDs | Driver | Level | Notes |
|---|---|---|---|---|
| Redragon M811 PRO | `258a:002f` receiver, `258a:002e` cable | SinoWealth | ✅ Full | Model marker `0x17`. Verified on firmware 2911 through the receiver. Cable path and polling-rate map still to confirm. |
| Redragon M690 PRO | `258a:002f`, `258a:002e` | SinoWealth | 👀 Detected | Model marker `0x13`. Stage DPI is an index into a vendor table that hasn't been mapped yet. |
| Other SinoWealth wireless mice | `258a:002f`, `258a:002e` | SinoWealth | 👀 Detected | Shown as "SinoWealth wireless mouse (model 0xNN)". A model file makes them configurable. |
| Logitech mice with HID++ 2.0 | `046d:*` with a HID++ collection, directly or through a Unifying, Lightspeed or Bolt receiver | Logitech | 🔷 Basic | Name, battery, DPI and polling rate. Not yet tested on real hardware. Mice running from an on-board profile are only read unless you enable experimental writes. |
| Logitech mice without HID++ 2.0 | `046d:*` | Generic | 👀 Detected | Older HID++ 1.0 mice. |
| Everything else | any HID mouse | Generic | 👀 Detected | Touchpads and laptop pointing sticks are left out. |

## What "Basic" covers for Logitech

| Feature | HID++ feature | Read | Write |
|---|---|---|---|
| Name and type | `0x0005` | ✅ | — |
| Battery | `0x1004` unified, or `0x1000` | ✅ | — |
| DPI (one value) | `0x2201` adjustable DPI | ✅ | ✅ with read-back |
| Polling rate | `0x8060` adjustable report rate | ✅ | ✅ with read-back |
| On-board profile mode | `0x8100` | ✅ | Only with experimental writes, and undone when Wyrm quits |

Button remapping, lighting, on-board profile editing and 2–8 kHz polling (`0x8061`) aren't there yet.

## Running alongside vendor apps

Each vendor app rewrites its mouse when it switches profiles, so two apps managing the same mouse fight. Wyrm
spots the common ones (the SinoWealth OEM tool `OemDrv.exe`, Logitech G HUB, Logi Options+) and says so on the
mouse's card. Quit the other app to let Wyrm manage that mouse. Mice that only Wyrm manages aren't affected.

## Help wanted

- **M811 PRO:** confirm the polling-rate map, lighting effects 4–9, the disabled-stage mask and the USB-C cable
  path. See [the SinoWealth notes](protocols/sinowealth-wireless.md#open-questions-help-wanted).
- **M690 PRO:** dumps at each DPI value to map its DPI table.
- **Any Logitech HID++ mouse:** run `python tools/list_devices.py --probe` and say whether DPI and polling-rate
  changes stick.
- **Anything else:** see [adding a device](adding-a-device.md).
