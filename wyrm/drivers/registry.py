"""Find mice: one hid.enumerate() per scan, offered to each driver in turn.

Drivers are asked in priority order. What a driver claims, later drivers don't see. A device
that fails to open is handed to the next driver (usually generic, which just shows it) and probed
again later, waiting longer each time.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

import hid

from .base import Connection, DeviceSession, Driver

log = logging.getLogger(__name__)

RETRY_S = 10.0
RETRY_MAX_S = 300.0


class Registry:
    def __init__(self, drivers: list[Driver], enumerate_fn: Callable[[], list[dict]] | None = None):
        self.drivers = drivers
        self._enumerate = enumerate_fn or hid.enumerate
        self.connections: dict[str, Connection] = {}
        self._retry: dict[str, tuple[float, float]] = {}    # key -> (not before, next delay)

    def scan(self) -> None:
        """Open devices that appeared, close the ones that went away."""
        entries = self._enumerate()
        claimed: set[bytes] = set()
        seen: set[str] = set()
        for drv in self.drivers:
            free = [e for e in entries if e["path"] not in claimed]
            for cand in drv.discover(free):
                if cand.key not in self.connections and not self._open(cand):
                    continue
                seen.add(cand.key)
                claimed.update(e["path"] for e in cand.entries)
        for key in [k for k in self.connections if k not in seen]:
            log.info("device gone: %s", key)
            self._close(key)

    def _open(self, cand) -> bool:
        not_before, delay = self._retry.get(cand.key, (0.0, RETRY_S))
        if time.monotonic() < not_before:
            return False
        try:
            conn = cand.driver.open(cand)
        except Exception as e:  # unplugged mid-probe, busy, or a protocol surprise
            log.warning("opening %s failed: %s", cand.key, e)
            conn = None
        if conn is None:
            self._retry[cand.key] = (time.monotonic() + delay, min(delay * 2, RETRY_MAX_S))
            return False
        self._retry.pop(cand.key, None)
        self.connections[cand.key] = conn
        log.info("opened %s", cand.key)
        return True

    def _close(self, key: str) -> None:
        conn = self.connections.pop(key)
        try:
            conn.close()
        except Exception:
            pass

    def refresh(self) -> None:
        for key, conn in list(self.connections.items()):
            try:
                conn.refresh()
            except OSError as e:
                log.warning("lost %s: %s", key, e)
                self._close(key)

    def sessions(self) -> list[DeviceSession]:
        return [s for conn in self.connections.values() for s in conn.sessions()]

    def drop(self, session: DeviceSession) -> None:
        """A session hit an I/O error: close its connection so the next scan reopens it."""
        for key, conn in list(self.connections.items()):
            if session in conn.sessions():
                self._close(key)

    def close(self) -> None:
        for key in list(self.connections):
            self._close(key)


class StaticRegistry(Registry):
    """Fixed connections (the simulated mice in --demo and tests)."""

    def __init__(self, connections: dict[str, Connection]):
        super().__init__([], lambda: [])
        self.connections = dict(connections)

    def scan(self) -> None:
        pass

    def drop(self, session: DeviceSession) -> None:
        pass
