"""Device registry and availability policy for the bridge facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DeviceAvailability(str, Enum):
    AVAILABLE = "available"
    NOT_FOUND = "not_found"
    DISCONNECTED = "disconnected"
    CONFLICT = "conflict"


@dataclass
class DeviceRecord:
    """Bridge-side view of a configured StackChan device."""

    device_id: str
    configured: bool = True
    connected: bool = True
    physical_ids: set[str] = field(default_factory=set)

    @property
    def conflicted(self) -> bool:
        return len(self.physical_ids) > 1


class DeviceRegistry:
    """Minimal device registry with the documented bridge error semantics."""

    def __init__(self, records: list[DeviceRecord] | None = None) -> None:
        self._records: dict[str, DeviceRecord] = {}
        seed_records = records if records is not None else [DeviceRecord("default")]
        for record in seed_records:
            self._records[record.device_id] = record

    def add_configured_device(
        self, device_id: str, *, connected: bool = True
    ) -> DeviceRecord:
        record = DeviceRecord(device_id=device_id, configured=True, connected=connected)
        self._records[device_id] = record
        return record

    def register_physical_device(self, device_id: str, physical_id: str) -> DeviceRecord:
        record = self._records.get(device_id)
        if record is None:
            record = self.add_configured_device(device_id, connected=True)
        record.physical_ids.add(physical_id)
        record.connected = True
        return record

    def set_connected(self, device_id: str, connected: bool) -> None:
        record = self._records.get(device_id)
        if record is None:
            record = self.add_configured_device(device_id, connected=connected)
        record.connected = connected

    def get(self, device_id: str) -> DeviceRecord | None:
        return self._records.get(device_id)

    def device_ids(self) -> tuple[str, ...]:
        return tuple(self._records)

    def availability(self, device_id: str) -> DeviceAvailability:
        record = self.get(device_id)
        if record is None or not record.configured:
            return DeviceAvailability.NOT_FOUND
        if record.conflicted:
            return DeviceAvailability.CONFLICT
        if not record.connected:
            return DeviceAvailability.DISCONNECTED
        return DeviceAvailability.AVAILABLE
