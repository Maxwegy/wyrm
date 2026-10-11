"""Mouse drivers. Add a new one to DRIVERS (before the generic fallback)."""
from __future__ import annotations

from ..core.model import ButtonAction, MacroEvent
from .base import SUPPORT_LABELS, Capabilities, DeviceInfo
from .generic import GenericDriver
from .logitech.driver import LogitechDriver
from .registry import Registry, StaticRegistry
from .sinowealth.driver import SinoWealthDriver

__all__ = ["SUPPORT_LABELS", "Capabilities", "DeviceInfo", "default_registry", "demo_registry",
           "default_buttons", "macro_event_count"]


def default_registry() -> Registry:
    return Registry([SinoWealthDriver(), LogitechDriver(), GenericDriver()])


def demo_registry() -> Registry:
    """Two simulated mice: a Redragon M811 PRO and a HID++ mouse."""
    from .base import SingleConnection
    from .logitech.driver import LogitechConnection
    from .logitech.fake import FakeHidppMouse, FakeHidppTransport
    from .logitech.hidpp import DIRECT
    from .sinowealth.driver import SinoWealthSession
    from .sinowealth.fake import FakeTransport

    sino = SingleConnection(SinoWealthSession(FakeTransport(), "demo:sinowealth", demo=True))
    logi = LogitechConnection(FakeHidppTransport({DIRECT: FakeHidppMouse()}), "demo:logitech", 0, False, demo=True)
    logi.refresh()
    return StaticRegistry({"demo:sinowealth": sino, "demo:logitech": logi})


def default_buttons(info: DeviceInfo) -> list[ButtonAction]:
    """The layout "Restore defaults" puts back, for mice that have one."""
    if info.driver == "sinowealth":
        from .sinowealth.driver import default_buttons as sino_defaults
        return sino_defaults(info.key)
    return []


def macro_event_count(info: DeviceInfo, events: list[MacroEvent]) -> int:
    """How many of the mouse's macro slots these events need."""
    if info.driver == "sinowealth":
        from .sinowealth.codec.macro import device_event_count
        return device_event_count(events)
    return len(events)
