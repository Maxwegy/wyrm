"""What every mouse driver provides. The rest of Wyrm only talks to these types.

A driver finds its devices in one hid.enumerate() listing (no I/O), opens a Connection for each,
and every Connection yields DeviceSessions: one per mouse. A receiver is a connection whose
mice come and go. Sessions are only used from the device thread.
"""
from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..core.model import DeviceSettings

SUPPORT_LABELS = {"full": "Full support", "basic": "Basic support", "detected": "Not supported yet"}


@dataclass
class Capabilities:
    dpi_min: int = 0
    dpi_max: int = 0
    dpi_step: int = 0
    dpi_values: list[int] = field(default_factory=list)   # a fixed DPI list, when the mouse has one
    dpi_stages: int = 0              # 0 = no DPI control, 1 = a single DPI
    stage_colors: bool = False
    polling_rates: list[int] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)      # remappable buttons, in slot order
    effects: list[str] = field(default_factory=list)
    verified_effects: list[str] = field(default_factory=list)
    macro_slots: int = 0
    macro_max_events: int = 0
    battery: bool = False
    sensor: str = ""
    unverified: list[str] = field(default_factory=list)   # fields only written with experimental writes on

    @property
    def configurable(self) -> bool:
        return bool(self.dpi_stages or self.polling_rates or self.buttons or self.effects)

    def snap_dpi(self, dpi: int) -> int:
        if self.dpi_values:
            return min(self.dpi_values, key=lambda v: abs(v - dpi))
        dpi = max(self.dpi_min, min(self.dpi_max, int(dpi)))
        if self.dpi_step:
            dpi = self.dpi_min + round((dpi - self.dpi_min) / self.dpi_step) * self.dpi_step
        return min(dpi, self.dpi_max)


@dataclass
class DeviceInfo:
    uid: str                     # this connection, e.g. "sinowealth:258a:002f"
    key: str                     # the mouse model; profiles store settings under it
    name: str                    # what the UI shows, e.g. "Redragon M811 PRO"
    vendor: str
    driver: str
    vid: int = 0
    pid: int = 0
    connection: str = "usb"      # receiver | cable | usb | bluetooth
    support: str = "detected"    # full | basic | detected
    diagram: str = "generic"
    caps: Capabilities = field(default_factory=Capabilities)
    fw: str = ""
    conflicts: dict[str, str] = field(default_factory=dict)   # exe -> app that fights over the same settings
    demo: bool = False

    @property
    def short_name(self) -> str:
        v = self.vendor + " "
        return self.name[len(v):] if self.vendor and self.name.startswith(v) else self.name


@dataclass
class DeviceStatus:
    link: bool = True            # awake and reachable
    battery: int | None = None
    charging: bool | None = None
    full: bool | None = None
    note: str = ""               # e.g. "uses its on-board profile"


@dataclass
class DeviceState:
    settings: DeviceSettings     # what is on the mouse right now
    snapshot: dict[str, bytes] = field(default_factory=dict)   # file suffix -> raw backup
    fw: str = ""


class NotReady(Exception):
    """The mouse can't take writes right now (asleep). The write waits until it wakes."""


class ApplyRefused(Exception):
    """The write was refused or didn't stick. The message is shown to the user."""


class DeviceSession(ABC):
    info: DeviceInfo

    @abstractmethod
    def poll(self) -> DeviceStatus:
        """Cheap status check, every few seconds."""

    def read_state(self) -> DeviceState | None:
        """Read and decode the mouse's current settings."""
        return None

    def apply(self, settings: DeviceSettings, macros: dict, opts: dict) -> dict:
        """Write `settings`, verify, and return {"changed": [...], "skipped": [...], "dry_run": bool}.
        opts: "allow" (unverified fields unlocked), "experimental", "dry_run"."""
        raise ApplyRefused(f"Wyrm can't change settings on the {self.info.name} yet.")

    def restore(self, snapshot: dict[str, bytes]) -> bool:
        raise ApplyRefused(f"Wyrm can't restore settings on the {self.info.name}.")

    def seed_settings(self, state: DeviceState) -> DeviceSettings:
        """The settings a new model brings into the Default profile."""
        return copy.deepcopy(state.settings)

    def shutdown(self) -> None:
        """Wyrm is quitting: undo anything that only makes sense while it runs."""

    def close(self) -> None:
        pass


@dataclass
class Candidate:
    key: str                     # stable while the device stays plugged in
    driver: "Driver"
    entries: list[dict]          # the hid.enumerate() entries that belong to it


class Connection(ABC):
    def refresh(self) -> None:
        """Called every poll. Receivers look for mice that woke up or were paired."""

    @abstractmethod
    def sessions(self) -> list[DeviceSession]:
        ...

    def close(self) -> None:
        for s in self.sessions():
            s.close()


class SingleConnection(Connection):
    def __init__(self, session: DeviceSession):
        self.session = session

    def sessions(self) -> list[DeviceSession]:
        return [self.session]


class Driver(ABC):
    name = ""

    @abstractmethod
    def discover(self, entries: list[dict]) -> list[Candidate]:
        """Pick this driver's devices from an enumeration. No I/O."""

    @abstractmethod
    def open(self, cand: Candidate) -> Connection | None:
        """Probe and open. None hands the device on to the next driver for now."""


def slug(text: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in text)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "mouse"


def entry_str(e: dict, key: str) -> str:
    v = e.get(key) or ""
    return v.decode(errors="replace") if isinstance(v, bytes) else str(v)
