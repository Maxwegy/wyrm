"""SinoWealth command set for the Redragon M811 PRO.

Report 5 (8 bytes) carries short commands; report 8 carries the 154-byte
settings block and the 88-byte button block. Only commands in ALLOWED are
ever sent.
"""
from __future__ import annotations

from dataclasses import dataclass

from .transport import HidTransport, TransportError

CMD_IDENTIFY = 0x01
CMD_LINK = 0x80
CMD_BATTERY = 0x90
CMD_MACRO_WRITE = 0x30
CMD_MACRO_READ = 0x31

SETTINGS_LEN = 154
BUTTONS_LEN = 88
BLOCK_TRAILER = 0xA5

ALLOWED = {CMD_IDENTIFY, CMD_LINK, CMD_BATTERY, CMD_MACRO_WRITE, CMD_MACRO_READ,
           0x11, 0x12, 0x21, 0x22}


def settings_cmd(wireless: bool) -> int:
    return 0x21 if wireless else 0x11


def buttons_cmd(wireless: bool) -> int:
    return 0x22 if wireless else 0x12


class ProtocolError(RuntimeError):
    pass


@dataclass
class Battery:
    level: int | None = None       # 0..100 via the receiver
    charging: bool | None = None   # via the cable
    full: bool | None = None


def command(t: HidTransport, cmd: int, *args: int) -> bytes:
    if cmd not in ALLOWED:
        raise PermissionError(f"command {cmd:#04x} not in allow-list")
    t.set_feature(bytes([5, cmd, *args]).ljust(8, b"\0"))
    r = t.get_feature(5)
    if len(r) < 4 or r[1] != cmd:
        raise ProtocolError(f"unexpected answer to {cmd:#04x}: {r.hex(' ')}")
    return r


def identify(t: HidTransport) -> str:
    return command(t, CMD_IDENTIFY)[2:6].decode("ascii", "replace")


def link_ok(t: HidTransport) -> bool:
    if not t.paths.wireless:
        return True
    return command(t, CMD_LINK)[2] == 1


def battery(t: HidTransport) -> Battery:
    r = command(t, CMD_BATTERY)
    if r[2] == 0x11:
        return Battery(level=r[3])
    if r[2] == 0x10:
        return Battery(charging=r[3] == 1, full=r[3] == 2)
    return Battery()


def _read_block(t: HidTransport, cmd: int, expect_len: int) -> bytes:
    t.set_feature(bytes([5, cmd, 0, 0, 0, 0, 0, 0]))
    r = t.get_feature(8)
    if len(r) != expect_len or r[0] != 8 or r[1] != cmd:
        raise ProtocolError(f"bad block for {cmd:#04x}: len={len(r)} head={r[:4].hex(' ')}")
    return r


def read_settings(t: HidTransport) -> bytes:
    return _read_block(t, settings_cmd(t.paths.wireless), SETTINGS_LEN)


def read_buttons(t: HidTransport) -> bytes:
    return _read_block(t, buttons_cmd(t.paths.wireless), BUTTONS_LEN)


def _frame_settings(block: bytes, wireless: bool) -> bytes:
    if len(block) != SETTINGS_LEN or block[-2] != BLOCK_TRAILER:
        raise ProtocolError("settings block has wrong length or trailer")
    f = bytearray(block)
    f[0], f[1], f[2], f[3] = 8, settings_cmd(wireless), 0, SETTINGS_LEN - 8
    return bytes(f).ljust(520, b"\0")


def _frame_buttons(block: bytes, wireless: bool) -> bytes:
    if len(block) != BUTTONS_LEN:
        raise ProtocolError("button block has wrong length")
    f = bytearray(block) + bytes([BLOCK_TRAILER])
    f[0], f[1], f[2], f[3] = 8, buttons_cmd(wireless), 0, BUTTONS_LEN - 8
    return bytes(f).ljust(520, b"\0")


def write_settings(t: HidTransport, block: bytes) -> None:
    t.set_feature(_frame_settings(block, t.paths.wireless))


def write_buttons(t: HidTransport, block: bytes) -> None:
    t.set_feature(_frame_buttons(block, t.paths.wireless))
