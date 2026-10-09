"""Profiles, macros and app config as JSON files, written atomically."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .model import Macro, Profile, macro_from_json, macro_to_json

log = logging.getLogger(__name__)


@dataclass
class AppConfig:
    active_profile_id: str | None = None
    default_profile_id: str | None = None
    profile_order: list[str] = field(default_factory=list)
    auto_switch: bool = True
    start_minimized: bool = True
    osd: bool = True                     # on-screen toast when the profile changes
    experimental: bool = False           # write fields not yet verified on this mouse
    verified: list[str] = field(default_factory=list)  # fields the user verified ("polling", ...)
    dry_run: bool = False
    first_write_ok: bool = False
    accent: str = "ember"
    schema: int = 1

    def allow(self) -> set[str]:
        return {"*"} if self.experimental else set(self.verified)


def _atomic_write(path: Path, data: dict) -> None:
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
        self.load()

    # --- load ------------------------------------------------------------
    def load(self) -> None:
        cfg = self.root / "config.json"
        if cfg.exists():
            try:
                raw = json.loads(cfg.read_text(encoding="utf-8"))
                known = AppConfig.__dataclass_fields__.keys()
                self.config = AppConfig(**{k: v for k, v in raw.items() if k in known})
            except Exception:
                log.exception("config.json unreadable; using defaults")
        self.profiles = {}
        for f in self.pdir.glob("*.json"):
            try:
                p = Profile.from_json(json.loads(f.read_text(encoding="utf-8")))
                self.profiles[p.id] = p
            except Exception:
                log.exception("skipping unreadable profile %s", f.name)
        self.macros = {}
        for f in self.mdir.glob("*.json"):
            try:
                m = macro_from_json(json.loads(f.read_text(encoding="utf-8")))
                self.macros[m.id] = m
            except Exception:
                log.exception("skipping unreadable macro %s", f.name)
        order = [i for i in self.config.profile_order if i in self.profiles]
        order += [i for i in self.profiles if i not in order]
        self.config.profile_order = order

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

    # --- config ----------------------------------------------------------
    def save_config(self) -> None:
        _atomic_write(self.root / "config.json", asdict(self.config))
