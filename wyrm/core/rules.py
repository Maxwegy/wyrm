"""Decide which profile owns the foreground app."""
from __future__ import annotations

import fnmatch

from .model import AppRule, Profile


def match(rule: AppRule, exe: str, title: str) -> bool:
    if not rule.exe_name:
        return False
    if not fnmatch.fnmatch(exe.lower(), rule.exe_name.strip().lower()):
        return False
    if rule.title_contains and rule.title_contains.lower() not in (title or "").lower():
        return False
    return True


def resolve(profiles: list[Profile], exe: str, title: str) -> Profile | None:
    """Highest priority wins; a rule with a title filter beats one without;
    earlier profiles win remaining ties."""
    best = None
    best_key = None
    for order, p in enumerate(profiles):
        for r in p.rules:
            if match(r, exe, title):
                key = (r.priority, 1 if r.title_contains else 0, -order)
                if best_key is None or key > best_key:
                    best, best_key = p, key
    return best
