# Logitech HID++ 2.0: what Wyrm uses

The subset of HID++ 2.0 that Wyrm's Logitech driver speaks, from the public feature descriptions and
[libratbag's `hidpp20`](https://github.com/libratbag/libratbag/blob/master/src/hidpp20.h) notes (MIT). **Status:
tested against a simulated device only.** Reports from real mice are very welcome.

## Transport

| Thing | Value |
|---|---|
| Vendor ID | `0x046D` |
| Collections | long HID++ (usage page `0xFF00`, usage `0x0002`, report `0x11`, 20 bytes); short (usage `0x0001`, report `0x10`, 7 bytes). `0xFF43` pages are accepted on a best-effort basis. |
| Device index | `0xFF` for a mouse plugged in directly; `1`–`6` for mice paired to a receiver |
| Receivers | `c52b`, `c532` (Unifying), `c534` (Nano), `c539`, `c53a`, `c53f`, `c541`, `c545`, `c547` (Lightspeed), `c548` (Bolt), or any product string with "Receiver" |

Every request goes out as a long report: `11 <index> <feature index> <function << 4 | 0xB> <params…>`. The answer
echoes the first four bytes. Errors:

- HID++ 2.0: `11 <index> FF <feature index> <function|sw> <code>`.
- HID++ 1.0, from a receiver about one of its mice: `10 <index> 8F <feature index> <function|sw> <code>`. It arrives
  on the short collection, so Wyrm reads both.

Wyrm waits 300 ms for an answer. A receiver slot that doesn't answer is treated as empty or asleep and checked again
every 5 seconds.

## Features and functions (allow-list)

Wyrm can only call these. Everything else is refused before it's sent, including the DFU and reset features.

| Feature | ID | Functions | Use |
|---|---|---|---|
| Root | `0x0000` | 0 getFeature, 1 getProtocolVersion | Feature indexes; ping (major ≥ 2 means HID++ 2.0) |
| Feature set | `0x0001` | 0 count, 1 feature ID at index | `tools/list_devices.py --probe` |
| Device name and type | `0x0005` | 0 name length, 1 name chunk (16 bytes from an offset), 2 type | Name; only types 3 (mouse), 4 (trackpad) and 5 (trackball) are kept |
| Battery status | `0x1000` | 0 level, next level, status | Battery when `0x1004` is missing |
| Unified battery | `0x1004` | 0 capabilities, 1 state of charge %, level, charging status | Battery |
| Adjustable DPI | `0x2201` | 0 sensor count, 1 DPI list, 2 current/default DPI, **3 set DPI** | DPI |
| Adjustable report rate | `0x8060` | 0 rate list (bit *n* = *n* + 1 ms), 1 current rate in ms, **2 set rate** | Polling rate |
| On-board profiles | `0x8100` | **1 set mode** (`1` on-board, `2` host), 2 get mode | Only to switch to host mode with experimental writes on, and back when Wyrm quits |

DPI lists are big-endian 16-bit values after the sensor byte, ending at `0`. A value of `0xE000` or more is a step
marker: the range runs from the value before it to the value after it, in steps of (marker − `0xE000`).
`64 E032 6400` therefore means 100 – 25,600 in steps of 50.

## Writes

- **DPI** and **polling rate** are written, then read back with functions 2 and 1. A mismatch is reported as a
  failed write.
- In **on-board mode** the mouse's stored profile owns DPI and polling rate, so writes wouldn't stick. Wyrm skips
  them and says why on the mouse's card. With experimental writes on, Wyrm first switches the mouse to host mode
  and records the original mode in its snapshot. It switches the mouse back when Wyrm quits, and **Restore
  original settings** does the same.

## Open questions

- Confirm all of the above on real mice: a Lightspeed G mouse, a Bolt or Unifying office mouse, and one plugged in
  by cable.
- Does host mode survive a power cycle on G-series mice? Wyrm assumes it doesn't.
- 2–8 kHz polling (`0x8061`), button remapping (`0x1b04`), lighting (`0x8070` / `0x8071`) and on-board profile
  editing are not implemented.
