"""Profiles, macros, app config and the mice Wyrm has seen, as JSON files written atomically."""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from ..drivers.base import Capabilities, DeviceInfo
from .model import M811_KEY, Macro, Profile, macro_from_json, macro_to_json

log = logging.getLogger(__name__)


@dataclass
class AppConfig:
    active_profile_id: str | None = None
    default_profile_id: str | None = None
    profile_order: list[str] = field(default_factory=list)
    auto_switch: bool = True
    start_minimized: bool = True
    osd: bool = True                     # on-screen toast when the profile changes
    experimental: bool = False           # write fields not yet verified on a mouse model
    verified: dict[str, list[str]] = field(default_factory=dict)   # model -> fields verified on it ("polling")
    dry_run: bool = False
    write_ok_models: list[str] = field(default_factory=list)       # mice the user allowed Wyrm to write to
    seeded_models: list[str] = field(default_factory=list)         # mice whose own setup filled the Default profile
    current_device: str | None = None    # the mouse model the editing pages show
    accent: str = "ember"
    schema: int = 2

    def allow(self, key: str) -> set[str]:
        return {"*"} if self.experimental else set(self.verified.get(key, []))


def migrate_config(raw: dict) -> dict:
    """Schema 1 knew one mouse (the M811 PRO): its flags become that model's entries."""
    if raw.get("schema", 1) >= 2:
        return raw
    raw = dict(raw)
    verified = raw.pop("verified", [])
    raw["verified"] = {M811_KEY: list(verified)} if isinstance(verified, list) and verified else {}
    raw["write_ok_models"] = [M811_KEY] if raw.pop("first_write_ok", False) else []
    raw["seeded_models"] = [M811_KEY] if raw.pop("seeded", False) else []
    raw["schema"] = 2
    return raw


def _atomic_write(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.pdir = root / "profiles"
        self.mdir = root / "macros"
        self.pdir.mkdir(parents=True, exist_ok=True)
        self.mdir.mkdir(parents=True, exist_ok=True)
        self.config = AppConfig()
        self.profiles: dict[str, Profile] = {}
        self.macros: dict[str, Macro] = {}
        self.known: dict[str, dict] = {}     # model key -> what the mouse looked like when last seen
        self.load()

    # --- load ------------------------------------------------------------
    def load(self) -> None:
        migrated = False
        cfg = self.root / "config.json"
        if cfg.exists():
            try:
                raw = json.loads(cfg.read_text(encoding="utf-8"))
                if raw.get("schema", 1) < 2:
                    self._backup("backup-v1")
                    raw, migrated = migrate_config(raw), True
                known = {f.name for f in fields(AppConfig)}
                self.config = AppConfig(**{k: v for k, v in raw.items() if k in known})
            except Exception:
                log.exception("config.json unreadable; using defaults")
        self.profiles = {}
        for f in self.pdir.glob("*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                if raw.get("schema", 1) < 2 and not migrated:
                    self._backup("backup-v1")
                p = Profile.from_json(raw)
                self.profiles[p.id] = p
                migrated |= raw.get("schema", 1) < 2
            except Exception:
                log.exception("skipping unreadable profile %s", f.name)
        self.macros = {}
        for f in self.mdir.glob("*.json"):
            try:
                m = macro_from_json(json.loads(f.read_text(encoding="utf-8")))
                self.macros[m.id] = m
            except Exception:
                log.exception("skipping unreadable macro %s", f.name)
        dev = self.root / "devices.json"
        if dev.exists():
            try:
                self.known = json.loads(dev.read_text(encoding="utf-8"))
            except Exception:
                log.exception("devices.json unreadable")
        order = [i for i in self.config.profile_order if i in self.profiles]
        order += [i for i in self.profiles if i not in order]
        self.config.profile_order = order
        if migrated:
            log.info("moved profiles and config to schema 2 (copies in backup-v1)")
            for p in self.profiles.values():
                _atomic_write(self.pdir / f"{p.id}.json", p.to_json())
            self.save_config()

    def _backup(self, name: str) -> None:
        dst = self.root / name
        if dst.exists():
            return
        dst.mkdir(parents=True)
        if self.pdir.exists():
            shutil.copytree(self.pdir, dst / "profiles")
        cfg = self.root / "config.json"
        if cfg.exists():
            shutil.copy2(cfg, dst / "config.json")

    # --- profiles --------------------------------------------------------
    def ordered(self) -> list[Profile]:
        return [self.profiles[i] for i in self.config.profile_order if i in self.profiles]

    def save_profile(self, p: Profile) -> None:
        self.profiles[p.id] = p
        if p.id not in self.config.profile_order:
            self.config.profile_order.append(p.id)
            self.save_config()
        _atomic_write(self.pdir / f"{p.id}.json", p.to_json())

    def delete_profile(self, pid: str) -> None:
        if len(self.profiles) <= 1:
            raise ValueError("keep at least one profile")
        self.profiles.pop(pid, None)
        (self.pdir / f"{pid}.json").unlink(missing_ok=True)
        self.config.profile_order = [i for i in self.config.profile_order if i != pid]
        if self.config.active_profile_id == pid:
            self.config.active_profile_id = self.config.profile_order[0]
        if self.config.default_profile_id == pid:
            self.config.default_profile_id = self.config.profile_order[0]
        self.save_config()

    def move_profile(self, pid: str, delta: int) -> None:
        o = self.config.profile_order
        i = o.index(pid)
        j = max(0, min(len(o) - 1, i + delta))
        o.insert(j, o.pop(i))
        self.save_config()

    # --- macros ----------------------------------------------------------
    def save_macro(self, m: Macro) -> None:
        self.macros[m.id] = m
        _atomic_write(self.mdir / f"{m.id}.json", macro_to_json(m))

    def delete_macro(self, mid: str) -> None:
        self.macros.pop(mid, None)
        (self.mdir / f"{mid}.json").unlink(missing_ok=True)

    # --- mice ------------------------------------------------------------
    def remember(self, info: DeviceInfo) -> None:
        """Keep what a mouse looks like so it can be shown and edited while unplugged."""
        if info.demo or not info.caps.configurable:
            return
        d = asdict(info)
        for k in ("uid", "demo", "fw"):
            d.pop(k, None)
        d["last_seen"] = time.strftime("%Y-%m-%d")
        if json.loads(json.dumps(d)) == self.known.get(info.key):
            return
        self.known[info.key] = d
        _atomic_write(self.root / "devices.json", self.known)

    def known_info(self, key: str) -> DeviceInfo | None:
        d = self.known.get(key)
        if not d:
            return None
        names = {f.name for f in fields(DeviceInfo)}
        d = {k: v for k, v in d.items() if k in names}
        d["caps"] = Capabilities(**{k: v for k, v in (d.get("caps") or {}).items()
                                   if k in {f.name for f in fields(Capabilities)}})
        return DeviceInfo(uid="", **{k: v for k, v in d.items() if k != "uid"})

    # --- config ----------------------------------------------------------
    def save_config(self) -> None:
        _atomic_write(self.root / "config.json", asdict(self.config))
