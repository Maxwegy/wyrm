from pathlib import Path

import pytest

from wyrm.core.model import ButtonAction, DpiStage, Lighting, Profile
from wyrm.hid.codec import buttons as B
from wyrm.hid.codec import settings as S
from wyrm.hid.codec.layout import LayoutMismatch

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
    p = Profile(dpi_stages=d["stages"], active_stage=d["active_stage"], lighting=d["lighting"])
    assert S.encode(SET, p) == SET


def test_dpi_change_touches_only_dpi_bytes():
    p = Profile(dpi_stages=[DpiStage(1050, True, (255, 0, 0)), DpiStage(2000, True, (0, 0, 255)),
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
    p = Profile(dpi_stages=[], polling_hz=500)
    assert S.encode(SET, p) == SET
    assert S.encode(SET, p, allow_unverified=True)[10] & 0xF == 3


def test_identity_mismatch_refuses():
    bad = bytearray(SET)
    bad[9] = 0x13
    with pytest.raises(LayoutMismatch):
        S.encode(bytes(bad), Profile())


def test_steady_lighting():
    p = Profile(dpi_stages=[], lighting=Lighting("steady", brightness=3, color=(1, 2, 3)))
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
    p = Profile(name="Gaming", buttons=B.decode_block(BTN), lighting=Lighting("breathing"))
    assert Profile.from_json(p.to_json()) == p
