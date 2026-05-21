"""Hardware-free core and lazy ROS adapters for the StackChan bridge."""

from stackchan_bridge.facade import StackChanBridgeFacade
from stackchan_bridge.models import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    PRIORITY_SAFETY,
    STATE_ACCEPTED,
    STATE_COMPLETED,
    STATE_REJECTED,
    STATE_TIMEOUT,
    CapabilitySnapshot,
    CommandMeta,
    CommandResponse,
    Result,
    StatusResponse,
    StatusSnapshot,
)
from stackchan_bridge.registry import DeviceRecord, DeviceRegistry

__all__ = [
    "CommandMeta",
    "CommandResponse",
    "CapabilitySnapshot",
    "DeviceRecord",
    "DeviceRegistry",
    "PRIORITY_HIGH",
    "PRIORITY_LOW",
    "PRIORITY_NORMAL",
    "PRIORITY_SAFETY",
    "Result",
    "STATE_ACCEPTED",
    "STATE_COMPLETED",
    "STATE_REJECTED",
    "STATE_TIMEOUT",
    "StackChanBridgeFacade",
    "StatusResponse",
    "StatusSnapshot",
]
