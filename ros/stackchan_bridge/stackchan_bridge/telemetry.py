"""Power and sensor telemetry helpers for the bridge."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass


POWER_SOURCE_NAMES = {
    0: "unknown",
    1: "battery",
    2: "usb",
    3: "external",
}


@dataclass(frozen=True)
class PowerStatusSnapshot:
    device_id: str
    voltage_v: float = math.nan
    current_ma: float = math.nan
    power_mw: float = math.nan
    percentage: float = math.nan
    power_source: int = 0
    charging: bool = False
    powered: bool = False
    low_battery: bool = False
    brownout_risk: bool = False
    fault_code: str = ""
    stamp: float = 0.0

    @property
    def power_source_name(self) -> str:
        return POWER_SOURCE_NAMES.get(self.power_source, "unknown")


class PowerTelemetryStore:
    def __init__(self, *, stale_after_seconds: float = 5.0, clock: Callable[[], float] = time.time) -> None:
        self.stale_after_seconds = stale_after_seconds
        self._clock = clock
        self._latest: dict[str, tuple[PowerStatusSnapshot, float]] = {}

    def update(self, snapshot: PowerStatusSnapshot) -> None:
        self._latest[snapshot.device_id] = (snapshot, self._clock())

    def get(self, device_id: str) -> tuple[PowerStatusSnapshot | None, bool]:
        record = self._latest.get(device_id)
        if record is None:
            return None, False
        snapshot, received_at = record
        return snapshot, self._clock() - received_at > self.stale_after_seconds


def public_topic_for(device_id: str, tail: str) -> str:
    return f"/stackchan/{device_id}/{tail}"


def device_topic_for(device_id: str, tail: str) -> str:
    return f"/stackchan/{device_id}/device/{tail}"
