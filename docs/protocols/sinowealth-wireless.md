# Redragon M811 PRO: USB protocol notes

Everything here was observed on a Redragon M811 PRO (AATROX), firmware `2911`, through its 2.4 GHz receiver,
unless marked otherwise. Byte offsets count from byte 0 of the HID report buffer, where byte 0 is the report ID.

**Status legend:** ✅ verified on hardware (read, write and read-back) · 🔶 decoded from dumps but writes not yet
confirmed · ❓ inferred from related SinoWealth mice ([libratbag `driver-sinowealth.c`][libratbag], the
[OpenMouse M690 PRO notes][openmouse]).

## Device

| Thing | Value |
|---|---|
| Vendor ID | `0x258A` (SinoWealth) |
| Product ID | `0x002F` 2.4 GHz receiver ✅ · `0x002E` USB-C cable ❓ |
| Sensor | PixArt PAW3395, 50 – 26,000 DPI in steps of 50 |
| Interface 0 | standard HID mouse |
| Interface 1 | keyboard (Col01), consumer control (Col02, report 2), vendor collections Col03 – Col06 |

Interface 1's vendor collections (from their report descriptors):

| Collection | Usage page | Report | Role |
|---|---|---|---|
| Col03 | `0xFF00` | feature 8, 519 bytes | **block channel**: settings, buttons, macros ✅ |
| Col04 | `0xFF00` | input 7, 7 bytes | device events (profile button, etc.), not decoded yet |
| Col05 | `0xFF00` | feature 5, 7 bytes | **command channel** ✅ |
| Col06 | `0xFF01` | feature 6, 7 bytes | unused by Wyrm |

Commands go to Col05, but the block they ask for is read back from Col03. Wyrm finds both by probing (identify
on every candidate, then a block read), not by the `ColNN` index, which Windows could renumber.

## Command channel (report 5)

Send `05 <cmd> <args…>` padded to **exactly 8 bytes** with SET_FEATURE, then GET_FEATURE report 5 with length
**8**. The firmware stalls on any other read length.

| Cmd | Meaning | Answer | Status |
|---|---|---|---|
| `01` | identify | `05 01 <4 ASCII>`: `"2911"` (matches the vendor `PSD=32,39,31,31`) | ✅ |
| `80` | receiver link | `05 80 01 01` linked · `05 80 00 …` mouse asleep/off | ✅ |
| `90` | battery | `05 90 11 <0-100>` via receiver ✅ · `05 90 10 01/02` charging/charged via cable ❓ | ✅ |
| `21` / `11` | read settings block (receiver / cable) | block on report 8 (Col03), 154 bytes | ✅ / ❓ |
| `22` / `12` | read button block (receiver / cable) | block on report 8, 88 bytes | ✅ / ❓ |
| `31 <n>` | read macro *n* | block on report 8 | ✅ |
| `75` | **DFU / bootloader**. Wyrm refuses to send this. | | ⛔ |

## Writes (report 8)

Writes are a SET_FEATURE of report 8 on Col03, padded to 520 bytes.

| Block | Frame | Status |
|---|---|---|
| settings | the 154-byte block as read, with byte 3 = `0x92` (154 − 8); the block already ends `a5 00` | ✅ |
| buttons | `08 22 00 50` + bytes 4 – 87 of the block + `a5` | ✅ |
| macro | `08 30 02 00 00 00 00 00 <n> 00 <count> <events…>` | ✅ |

Writes made while the receiver reports the mouse asleep are dropped, so Wyrm checks the link (`05 80`) right
before every write and re-reads afterwards to confirm.

## Settings block (154 bytes)

| Offset | Meaning | Encoding | Status |
|---|---|---|---|
| `0x00` – `0x03` | header | `08 21 00 00` on read | ✅ |
| `0x08` | ? | `0x64` | — |
| `0x09` | model marker | `0x17` on the M811 PRO (`0x13` on the M690 PRO); Wyrm refuses to write if it differs | ✅ |
| `0x0A` | polling rate | low nibble: probably 1 = 125, 2 = 250, 3 = 500, 4 = 1000 Hz (M690 map) | 🔶 |
| `0x0B` | stages | high nibble: active stage (1-based) · low nibble: stage count (5) | ✅ |
| `0x0C` | disabled-stage mask | bit *n* = stage *n* skipped | ❓ |
| `0x0D + 2n` | stage *n* DPI | little-endian 16-bit, `dpi / 50 − 1` (1000 → `13 00`, 26000 → `07 02`) | ✅ |
| `0x1D` – `0x2C` | probably Y-axis DPI for independent X/Y | zero | ❓ |
| `0x2D + 3n` | stage *n* indicator colour (8 slots) | R G B | ✅ |
| `0x45` | LED effect | see below | 🔶 |
| `0x46` | Colorful Streaming mode | high nibble brightness 0-4 · low nibble speed 0-4 | 🔶 |
| `0x47` | Colorful Streaming direction | | ❓ |
| `0x48` | Steady mode | high nibble brightness | 🔶 |
| `0x49` – `0x4B` | Steady colour | R G B | 🔶 |
| `0x4C` | Breathing mode | brightness / speed nibbles | 🔶 |
| `0x4D` | Breathing colour count | 7 | 🔶 |
| `0x4E + 3n` | Breathing colours (7) | R G B | 🔶 |
| `0x63`, `0x64` | Tail / Neon mode bytes | | ❓ |
| `0x66 + 3n` | colour table (8) | R G B | ❓ |
| `0x84` – `0x8A` | `01 02 03 04 05 06 07` | unknown | — |
| `0x98` – `0x99` | trailer | `a5 00` | ✅ |

LED effect values, following the vendor UI order and libratbag's table: `1` Colorful Streaming (this mouse's
default) · `2` Steady · `3` Breathing · `4` Colorful Tail · `5` Neon · `6` Colorful Steady · `7` Flicker ·
`8` Stars Twinkle · `9` Wave · `0` Off. Only `1` has been seen on this mouse so far, so Wyrm treats the others
as experimental.

## Button block (88 bytes)

From offset 8 there are 20 four-byte slots. Slots 1 – 16 are live:

| Slot | Button | Default |
|---|---|---|
| 1 – 3 | Left, Right, Middle | `11 01`, `11 02`, `11 04` |
| 4, 5 | Back, Forward (side, above the grid) | `11 08`, `11 10` |
| 6, 7 | DPI +, DPI − | `41 01`, `41 02` |
| 8 | Profile (top) | `50 06` |
| 9 – 16 | side keys 1 – 8 | `21 00 1e` … `21 00 25` (keys 1 – 8) |
| 17 – 20 | unused | `50 01` |

Slot encodings (✅ means seen on this mouse and round-tripped through a write):

| Bytes | Action |
|---|---|
| `11 <mask>` | mouse button: `01` L, `02` R, `04` M, `08` back, `10` forward ✅ |
| `21 <mods> <usage>` | keyboard key; mods `01` Ctrl `02` Shift `04` Alt `08` Win (right-hand: `10`…`80`) ✅ |
| `22 <b0> <b1> <b2>` | consumer key, one bit per usage of the consumer report, in this order: `B5 B6 B7 CD E2 A2 E9 EA 183 194 186 188 18A 192 2A8 184 221 223 224 225 226 227 22A 2B1` (from the Col02 descriptor) |
| `41 01` / `41 02` / `41 00` | DPI up ✅ / down ✅ / cycle ❓ |
| `42 <dpi/100>` | DPI lock (sniper) ❓ |
| `31 <mask> <gap ms> <count>` | rapid fire ❓ |
| `50 01` / `50 02` / `50 06` | disabled ✅ / lighting toggle ❓ / vendor profile switch ✅ |
| `70 <macro n> <mode> <count>` | macro; mode `1` repeat *count* times, `2` until any key, `4` while held ❓ |

The vendor's "profile switch" (`50 06`) only signals the vendor app (probably on Col04, input report 7).
Wyrm instead puts **F24** on that button and listens for F24 / F23 as global hotkeys.

## Macros

`08 30 02 00 00 00 00 00 <n> 00 <count>` followed by `count` three-byte events from offset 11, with at most 168
events. Read macro *n* back with `05 31 <n>`; the answer echoes the same layout. ✅ (written, read back,
cleared)

Each event is `<cmd> <delay ms after> <code>`. The commands are `50` key down and `D0` key up (code = HID
usage), and `10` button down and `90` button up (code = button bit). The delay is one byte, so Wyrm stretches
longer pauses with filler `D0 <ms> 00` events, which release a key that was never pressed.

Wyrm stores the macro for button slot *k* in macro *k* (1-based).

## Host-side profiles

The vendor app keeps profiles on the PC (`%LOCALAPPDATA%\Redragon\pro.dct`: an 8-byte header plus
5824-byte slots, with the profile name in UTF-16 at slot + `0x208`). It rewrites the mouse on every switch.
Wyrm does the same with its own JSON profiles, and skips the write when the mouse already matches.

## Open questions (help wanted)

- **Polling rate:** confirm the `0x0A` map. Use the "Test polling rate" button in Wyrm, then set each rate in
  the vendor app and dump with `tools/dump_blocks.py`.
- **Effects 2 – 9:** confirm the effect values and each effect's parameter bytes, one dump per effect.
- **Disabled-stage mask** (`0x0C`) and stage count < 5.
- **Col04 input events:** run a reader on Col04 and press the Profile and DPI buttons.
- **The cable path (`0x002E`):** confirm commands `0x11` / `0x12` and the charging answer.

[libratbag]: https://github.com/libratbag/libratbag/blob/master/src/driver-sinowealth.c
[openmouse]: https://github.com/OpenMouse-Project/mouse-protocol/blob/main/docs/redragon-m690-pro-testing.md
