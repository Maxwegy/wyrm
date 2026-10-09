"""Byte-preserving codec for the 154-byte settings block.

decode() reads what we understand; encode() patches only those offsets onto
the block freshly read from the device. Unknown bytes are never touched.
Fields marked unverified in the layout are only written when the caller
unlocks them through `allow` ("polling", "stage_enable", "effects", or "*").
"""
from __future__ import annotations

from ...core.model import DpiStage, Lighting, Profile
from .layout import check_block, load_layout

MAX_STAGES = 5   # vendor UI exposes 5 of the 8 slots


def _nib(b: int, which: str) -> int:
    return (b >> 4) & 0xF if which == "high" else b & 0xF


def _set_nib(b: int, which: str, v: int) -> int:
    v &= 0xF
    return (b & 0x0F) | (v << 4) if which == "high" else (b & 0xF0) | v


def dpi_to_raw(dpi: int, L: dict) -> int:
    d = L["dpi"]
    dpi = max(d["min"], min(d["max"], int(round(dpi / d["step"])) * d["step"]))
    return dpi // 50 - 1


def raw_to_dpi(raw: int) -> int:
    return (raw + 1) * 50


def decode(block: bytes, layout: dict | None = None) -> dict:
    L = layout or load_layout()
    check_block(block, L)
    st = L["stages"]
    info = block[st["offset"]]
    count = _nib(info, st["count_nibble"]) or MAX_STAGES
    active = max(0, _nib(info, st["active_nibble"]) - 1)
    mask = block[L["disabled_mask"]["offset"]]
    d, c = L["dpi"], L["stage_color"]
    stages = []
    for n in range(min(count, MAX_STAGES)):
        o = d["offset"] + n * d["stride"]
        co = c["offset"] + n * c["stride"]
        stages.append(DpiStage(raw_to_dpi(block[o] | block[o + 1] << 8),
                               not (mask >> n) & 1,
                               (block[co], block[co + 1], block[co + 2])))
    p = L["polling"]
    rate = p["map"].get(str(_nib(block[p["offset"]], p["nibble"])))

    eff_val = block[L["effect"]["offset"]]
    eff = next((k for k, v in L["effect"]["values"].items() if v == eff_val), None)
    lt = Lighting(effect=eff or "streaming")
    params = L["effect_params"].get(lt.effect, {})
    mb = L["mode_byte"]
    if "mode" in params:
        m = block[params["mode"]]
        lt.brightness = _nib(m, mb["brightness_nibble"])
        lt.speed = _nib(m, mb["speed_nibble"])
    sp = L["effect_params"]["steady"]
    lt.color = tuple(block[sp["color"]:sp["color"] + 3])
    bp = L["effect_params"]["breathing"]
    n = min(block[bp["color_count"]], bp["max_colors"])
    lt.colors = [tuple(block[bp["colors"] + 3 * i: bp["colors"] + 3 * i + 3]) for i in range(n)]
    return {"stages": stages, "active_stage": active, "polling_hz": rate,
            "lighting": lt, "effect_raw": eff_val}


VERIFIED_EFFECTS = ("streaming", "steady", "breathing")


def _unlocked(name: str, L: dict, key: str, allow) -> bool:
    allow = allow or ()
    return "*" in allow or name in allow or bool(L[key].get("verified"))


def encode(block: bytes, profile: Profile, *, allow=None, layout: dict | None = None) -> bytes:
    L = layout or load_layout()
    check_block(block, L)
    out = bytearray(block)

    stages = profile.dpi_stages[:MAX_STAGES]
    if stages:
        st = L["stages"]
        o = st["offset"]
        active = min(max(profile.active_stage, 0), len(stages) - 1) + 1
        out[o] = _set_nib(_set_nib(out[o], st["active_nibble"], active), st["count_nibble"], len(stages))
        d, c = L["dpi"], L["stage_color"]
        for n, s in enumerate(stages):
            raw = dpi_to_raw(s.dpi, L)
            po = d["offset"] + n * d["stride"]
            out[po], out[po + 1] = raw & 0xFF, raw >> 8
            co = c["offset"] + n * c["stride"]
            out[co:co + 3] = bytes(s.color)
        if _unlocked("stage_enable", L, "disabled_mask", allow):
            mask = 0
            for n, s in enumerate(stages):
                if not s.enabled:
                    mask |= 1 << n
            if mask == (1 << len(stages)) - 1:
                mask &= ~1   # never disable every stage
            out[L["disabled_mask"]["offset"]] = mask

    p = L["polling"]
    if profile.polling_hz and _unlocked("polling", L, "polling", allow):
        inv = {v: int(k) for k, v in p["map"].items()}
        if profile.polling_hz in inv:
            out[p["offset"]] = _set_nib(out[p["offset"]], p["nibble"], inv[profile.polling_hz])

    lt = profile.lighting
    if lt and (lt.effect in VERIFIED_EFFECTS or _unlocked("effects", L, "effect", allow)):
        vals = L["effect"]["values"]
        if lt.effect in vals:
            out[L["effect"]["offset"]] = vals[lt.effect]
            params = L["effect_params"].get(lt.effect, {})
            mb = L["mode_byte"]
            if "mode" in params:
                m = _set_nib(out[params["mode"]], mb["brightness_nibble"], max(0, min(4, lt.brightness)))
                if lt.effect != "steady":
                    m = _set_nib(m, mb["speed_nibble"], max(0, min(4, lt.speed)))
                out[params["mode"]] = m
            if lt.effect == "steady":
                o = params["color"]
                out[o:o + 3] = bytes(lt.color)
            if lt.effect == "breathing" and lt.colors:
                cols = lt.colors[:params["max_colors"]]
                out[params["color_count"]] = len(cols)
                for i, col in enumerate(cols):
                    o = params["colors"] + 3 * i
                    out[o:o + 3] = bytes(col)
    return bytes(out)
