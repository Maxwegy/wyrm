"""An in-memory Redragon M811 PRO that answers like the real one (fw 2911).

Used by the test suite and by `python -m wyrm --demo` to run the UI without
hardware. Every packet is checked the same way the firmware is picky about.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .enumerate import PID_RECEIVER, DevicePaths
from .transport import BLOCK_WRITE_LEN, CMD_LEN, FORBIDDEN_CMDS

SAMPLES = Path(__file__).resolve().parent / "models"


@dataclass
class FakeMouse:
    settings: bytes = field(default_factory=lambda: (SAMPLES / "sample.settings.bin").read_bytes())
    buttons: bytes = field(default_factory=lambda: (SAMPLES / "sample.buttons.bin").read_bytes())
    macros: dict = field(default_factory=dict)
    link: bool = True
    battery: int = 43
    fw: bytes = b"2911"
    writes: list = field(default_factory=list)
    drop_writes: bool = False   # simulate a sleeping mouse that ignores writes


class FakeTransport:
    def __init__(self, mouse: FakeMouse | None = None, wireless: bool = True):
        self.mouse = mouse or FakeMouse()
        self.paths = DevicePaths(PID_RECEIVER if wireless else 0x002E, b"fake-cmd", b"fake-blk")
        self._last = None

    def close(self) -> None:
        pass

    def set_feature(self, data: bytes) -> None:
        if data[1] in FORBIDDEN_CMDS:
            raise AssertionError("forbidden command sent")
        m = self.mouse
        if data[0] == 5:
            assert len(data) == CMD_LEN
            self._last = bytes(data)
            return
        assert data[0] == 8 and len(data) == BLOCK_WRITE_LEN
        m.writes.append(bytes(data))
        if m.drop_writes:
            return
        cmd = data[1]
        if cmd in (0x11, 0x21):
            assert data[3] == 154 - 8 and data[152] == 0xA5
            m.settings = bytes([8, cmd, 0, 0]) + bytes(data[4:154])
        elif cmd in (0x12, 0x22):
            assert data[3] == 88 - 8 and data[88] == 0xA5
            m.buttons = bytes([8, cmd, 0, 0]) + bytes(data[4:88])
        elif cmd == 0x30:
            n = data[10]
            m.macros[data[8]] = [tuple(data[11 + 3 * i: 14 + 3 * i]) for i in range(n)]
        else:
            raise AssertionError(f"unexpected block write {cmd:#04x}")

    def get_feature(self, report_id: int) -> bytes:
        m, q = self.mouse, self._last
        if q is None:
            raise OSError("read error")
        if report_id == 5:
            if q[1] == 0x01:
                return bytes([5, 1]) + m.fw + b"\0\0"
            if q[1] == 0x80:
                return bytes([5, 0x80, 1 if m.link else 0, 1 if m.link else 0, 0, 0, 0, 0])
            if q[1] == 0x90:
                return bytes([5, 0x90, 0x11, m.battery, 0, 0, 0, 0])
            raise OSError("read error")
        if report_id == 8:
            if q[1] in (0x11, 0x21):
                return m.settings
            if q[1] in (0x12, 0x22):
                return m.buttons
            if q[1] == 0x31:
                ev = m.macros.get(q[2], [])
                f = bytearray(520)
                f[:8] = bytes([8, 0x31]) + q[2:8]
                f[8], f[10] = q[2], len(ev)
                for i, e in enumerate(ev):
                    f[11 + 3 * i: 14 + 3 * i] = bytes(e)
                return bytes(f)
        raise OSError("read error")
