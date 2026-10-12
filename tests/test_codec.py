from pathlib import Path

import pytest

from wyrm.core.model import ButtonAction, DeviceSettings, DpiStage, Lighting, Profile
from wyrm.drivers.sinowealth.codec import buttons as B
from wyrm.drivers.sinowealth.codec import settings as S
from wyrm.drivers.sinowealth.codec.layout import LayoutMismatch, all_layouts, layout_for_block

FIX = Path(__file__).parent / "fixtures"
SET = (FIX / "baseline.settings.bin").read_bytes()
BTN = (FIX / "baseline.buttons.bin").read_bytes()


def test_decode_baseline_dpi_and_colors():
    d = S.decode(SET)
    assert [s.dpi for s in d["stages"]] == [1000, 2000, 4000, 8000, 26000]
    assert [s.color for s in d["stages"]] == [(255, 0, 0), (0, 0, 255), (0, 255, 255), (255, 0, 255), (255, 255, 0)]
    assert d["active_stage"] == 0
    assert d["lighting"].effect == "streaming"
    assert d["lighting"].brightness == 4 and d["lighting"].speed == 2
    assert len(d["lighting"].colors) == 7


def test_roundtrip_is_identity():
    d = S.decode(SET)
    p = DeviceSettings(dpi_stages=d["stages"], active_stage=d["active_stage"], lighting=d["lighting"])
    assert S.encode(SET, p) == SET


def test_dpi_change_touches_only_dpi_bytes():
    p = DeviceSettings(dpi_stages=[DpiStage(1050, True, (255, 0, 0)), DpiStage(2000, True, (0, 0, 255)),
                                   DpiStage(4000, True, (0, 255, 255)), DpiStage(8000, True, (255, 0, 255)),
                                   DpiStage(26000, True, (255, 255, 0))])
    out = S.encode(SET, p)
    assert [i for i in range(len(SET)) if out[i] != SET[i]] == [0x0D]
    assert S.decode(out)["stages"][0].dpi == 1050


def test_dpi_is_clamped_and_snapped():
    L = S.load_layout()
    assert S.raw_to_dpi(S.dpi_to_raw(26050, L)) == 26000
    assert S.raw_to_dpi(S.dpi_to_raw(10, L)) == 50
    assert S.raw_to_dpi(S.dpi_to_raw(1234, L)) == 1250


def test_unverified_polling_is_preserved_by_default():
    p = DeviceSettings(polling_hz=500)
    assert S.encode(SET, p) == SET
    assert S.encode(SET, p, allow={"polling"})[10] & 0xF == 3


def test_identity_mismatch_refuses():
    bad = bytearray(SET)
    bad[9] = 0x13
    with pytest.raises(LayoutMismatch):
        S.encode(bytes(bad), DeviceSettings(dpi_stages=[DpiStage(1000)]))


def test_steady_lighting():
    p = DeviceSettings(lighting=Lighting("steady", brightness=3, color=(1, 2, 3)))
    d = S.decode(S.encode(SET, p))
    assert d["lighting"].effect == "steady" and d["lighting"].color == (1, 2, 3)
    assert d["lighting"].brightness == 3


def test_buttons_decode_baseline():
    acts = B.decode_block(BTN)
    assert acts[0] == ButtonAction.mouse(1)
    assert acts[3] == ButtonAction.mouse(8)
    assert acts[5].kind == "dpi_up" and acts[6].kind == "dpi_down"
    assert acts[7].kind == "profile_cycle"
    assert acts[8] == ButtonAction.key(0x04, 0x01)      # Ctrl+A
    assert acts[12] == ButtonAction.key(0x22, 0x00)     # "5"


def test_buttons_roundtrip():
    assert B.encode_block(BTN, B.decode_block(BTN)) == BTN


def test_consumer_and_macro_encoding():
    assert B.encode_action(ButtonAction("consumer", usage=0xE9)) == bytes([0x22, 0x40, 0, 0])
    assert B.decode_action(bytes([0x22, 0x40, 0, 0])).usage == 0xE9
    assert B.encode_action(ButtonAction("macro", macro_mode=1, count=3), macro_index=2) == bytes([0x70, 2, 1, 3])


def test_refuses_to_remove_last_left_click():
    acts = B.decode_block(BTN)
    acts[0] = ButtonAction("disabled")
    with pytest.raises(ValueError):
        B.encode_block(BTN, acts)


def test_profile_json_roundtrip():
    p = Profile(name="Gaming", devices={"sinowealth/redragon-m811-pro": DeviceSettings(
        polling_hz=1000, dpi_stages=S.decode(SET)["stages"], buttons=B.decode_block(BTN), lighting=Lighting("breathing"))})
    assert Profile.from_json(p.to_json()) == p


def test_profile_hotkey_actions_roundtrip():
    from wyrm.core.keys import HOTKEY_NEXT_PROFILE
    raw = B.encode_action(ButtonAction("profile_next"))
    assert raw == bytes([0x21, 0, HOTKEY_NEXT_PROFILE, 0])
    assert B.decode_action(raw).kind == "profile_next"


def test_unverified_effect_needs_unlock():
    p = DeviceSettings(lighting=Lighting("wave"))
    assert S.encode(SET, p) == SET
    assert S.decode(S.encode(SET, p, allow={"effects"}))["lighting"].effect == "wave"


def test_macro_codec_roundtrip_and_long_delays():
    from wyrm.core.model import MacroEvent
    from wyrm.drivers.sinowealth.codec.macro import decode_events, encode_events
    ev = [MacroEvent("key_down", 0x04, 10), MacroEvent("key_up", 0x04, 700), MacroEvent("btn_down", 1, 5)]
    raw = encode_events(ev)
    assert raw[:2] == [(0x50, 10, 0x04), (0xD0, 255, 0x04)]
    assert len(raw) == 5   # 700 ms = 255 + 255 + 190
    assert decode_events(raw) == ev


def test_macro_too_long_rejected():
    from wyrm.core.model import MacroEvent
    from wyrm.drivers.sinowealth.codec.macro import device_event_count, encode_events
    with pytest.raises(ValueError):
        encode_events([MacroEvent("key_down", 4, 1)] * 169)
    assert device_event_count([MacroEvent("key_down", 4, 1)] * 169) == 169   # counting never raises


def test_model_files_identify_their_blocks():
    keys = {L["key"] for L in all_layouts()}
    assert {"sinowealth/redragon-m811-pro", "sinowealth/redragon-m690-pro"} <= keys
    assert layout_for_block(SET)["name"] == "Redragon M811 PRO"
    m690 = bytearray(SET)
    m690[9] = 0x13
    assert layout_for_block(bytes(m690))["support"] == "detected"
    unknown = bytearray(SET)
    unknown[9] = 0x42
    assert layout_for_block(bytes(unknown)) is None


def test_default_buttons_come_from_the_model_file():
    from wyrm.drivers.sinowealth.driver import default_buttons
    acts = default_buttons("sinowealth/redragon-m811-pro")
    assert len(acts) == 16 and acts[0] == ButtonAction.mouse(1)
    assert acts[7].kind == "profile_next" and acts[8] == ButtonAction.key(0x1E)
