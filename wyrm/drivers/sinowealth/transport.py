"""Size-checked wrapper over the two hidapi handles (command + block)."""
from __future__ import annotations

import threading

import hid

from .enumerate import DevicePaths

CMD_LEN = 8              # firmware stalls report-5 reads of any other length
BLOCK_READ_LEN = 520
BLOCK_WRITE_LEN = 520
FORBIDDEN_CMDS = {0x75}  # DFU / bootloader entry. Never.


class TransportError(OSError):
    pass


class HidTransport:
    def __init__(self, paths: DevicePaths):
        self.paths = paths
        self.lock = threading.RLock()
        self._cmd = hid.device()
        self._blk = hid.device()
        self._cmd.open_path(paths.cmd_path)
        try:
            self._blk.open_path(paths.block_path)
        except OSError:
            self._cmd.close()
            raise

    def close(self) -> None:
        for d in (self._cmd, self._blk):
            try:
                d.close()
            except Exception:
                pass

    def set_feature(self, data: bytes) -> None:
        if len(data) < 2:
            raise ValueError("feature report too short")
        if data[1] in FORBIDDEN_CMDS:
            raise PermissionError(f"command {data[1]:#04x} is forbidden")
        if data[0] == 5:
            dev = self._cmd
            if len(data) != CMD_LEN:
                raise ValueError("report 5 must be exactly 8 bytes")
        elif data[0] == 8:
            dev = self._blk
            if len(data) != BLOCK_WRITE_LEN:
                raise ValueError(f"report 8 writes must be {BLOCK_WRITE_LEN} bytes")
        else:
            raise ValueError(f"unsupported report id {data[0]}")
        with self.lock:
            n = dev.send_feature_report(bytes(data))
        if n < 0:
            raise TransportError(f"send_feature_report failed for report {data[0]}")

    def get_feature(self, report_id: int) -> bytes:
        if report_id == 5:
            dev, ln = self._cmd, CMD_LEN
        elif report_id == 8:
            dev, ln = self._blk, BLOCK_READ_LEN
        else:
            raise ValueError(f"unsupported report id {report_id}")
        with self.lock:
            try:
                return bytes(dev.get_feature_report(report_id, ln))
            except OSError as e:
                raise TransportError(str(e)) from e
