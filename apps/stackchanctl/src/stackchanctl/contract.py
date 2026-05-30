from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Priority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    SAFETY = "SAFETY"


class ResultState(StrEnum):
    ACCEPTED = "ACCEPTED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"


class CommandType(StrEnum):
    SAY = "say"
    FACE = "face"
    MOTION = "motion"
    MOTION_POSE = "motion-pose"
    MOTION_HOME = "motion-home"
    MOTION_STATUS = "motion-status"
    LED = "led"
    OBSERVE = "observe"
    EVENTS_LIST = "events-list"
    EVENTS_NEXT = "events-next"
    EVENTS_CLEAR = "events-clear"
    SPEECH_TRANSCRIPT = "speech-transcript"
    POWER_STATUS = "power-status"
    AUDIO_PLAY = "audio-play"
    AUDIO_CAPTURE = "audio-capture"
    CAMERA_CAPTURE = "camera-capture"
    NFC_WAIT = "nfc-wait"
    IMU_STREAM = "imu-stream"
    MAINTENANCE_CALIBRATION_STATUS = "maintenance-calibration-status"
    MAINTENANCE_CALIBRATION_CAPTURE_NEUTRAL = "maintenance-calibration-capture-neutral"
    MAINTENANCE_CALIBRATION_RESET = "maintenance-calibration-reset"


@dataclass(frozen=True)
class ErrorDetail:
    code: str
    message: str
    recoverable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
        }


@dataclass(frozen=True)
class CommandMeta:
    device_id: str
    command_id: str
    source: str
    created_at: str
    priority: Priority

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "command_id": self.command_id,
            "source": self.source,
            "created_at": self.created_at,
            "priority": self.priority.value,
        }


@dataclass(frozen=True)
class CommandRequest:
    command_type: CommandType
    meta: CommandMeta
    args: dict[str, Any]
    wait: bool
    timeout: float


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    result_state: ResultState
    meta: CommandMeta
    command: dict[str, Any]
    error: ErrorDetail | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "result_state": self.result_state.value,
            "device_id": self.meta.device_id,
            "command_id": self.meta.command_id,
            "metadata": self.meta.to_dict(),
            "command": self.command,
        }
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload


@dataclass(frozen=True)
class CapabilityStatus:
    name: str
    state: str
    detail_code: str = ""
    active: bool = False
    queued: int = 0
    last_update: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "state": self.state,
            "active": self.active,
            "queued": self.queued,
            "last_update": self.last_update,
        }
        if self.detail_code:
            payload["detail_code"] = self.detail_code
        return payload


@dataclass(frozen=True)
class DeviceStatus:
    device_id: str
    connected: bool
    device_state: str
    face: str
    last_error: ErrorDetail | None = None
    meta: CommandMeta | None = None
    firmware_version: str = ""
    capabilities: tuple[CapabilityStatus, ...] = ()
    motion: str = "idle"

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "command_id": None if self.meta is None else self.meta.command_id,
            "metadata": None if self.meta is None else self.meta.to_dict(),
            "connected": self.connected,
            "device_state": self.device_state,
            "face": self.face,
            "motion": self.motion,
            "last_error": None if self.last_error is None else self.last_error.to_dict(),
            "firmware_version": self.firmware_version,
            "capabilities": [capability.to_dict() for capability in self.capabilities],
        }


@dataclass(frozen=True)
class Event:
    event_id: str
    device_id: str
    event_name: str
    source: str
    stamp: str
    command_id: str | None = None
    payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "device_id": self.device_id,
            "event_name": self.event_name,
            "source": self.source,
            "stamp": self.stamp,
            "command_id": self.command_id,
            "payload": self.payload or {},
        }


@dataclass(frozen=True)
class EventListResult:
    ok: bool
    result_state: ResultState
    device_id: str
    events: list[Event]
    cursor: str | None = None
    meta: CommandMeta | None = None
    error: ErrorDetail | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "result_state": self.result_state.value,
            "device_id": self.device_id,
            "command_id": None if self.meta is None else self.meta.command_id,
            "metadata": None if self.meta is None else self.meta.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "cursor": self.cursor,
        }
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload


@dataclass(frozen=True)
class TranscriptResult:
    ok: bool
    result_state: ResultState
    device_id: str
    utterance_id: str | None
    transcript: str | None
    confidence: float | None
    expires_at: str | None
    meta: CommandMeta | None = None
    error: ErrorDetail | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "result_state": self.result_state.value,
            "device_id": self.device_id,
            "command_id": None if self.meta is None else self.meta.command_id,
            "metadata": None if self.meta is None else self.meta.to_dict(),
            "utterance_id": self.utterance_id,
            "transcript": self.transcript,
            "confidence": self.confidence,
            "expires_at": self.expires_at,
        }
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload


@dataclass(frozen=True)
class PowerStatusResult:
    ok: bool
    result_state: ResultState
    device_id: str
    voltage_v: float | None
    current_ma: float | None
    power_mw: float | None
    percentage: float | None
    power_source: str
    charging: bool
    powered: bool
    low_battery: bool
    brownout_risk: bool
    fault_code: str | None = None
    stale: bool = False
    stamp: str | None = None
    meta: CommandMeta | None = None
    error: ErrorDetail | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "result_state": self.result_state.value,
            "device_id": self.device_id,
            "command_id": None if self.meta is None else self.meta.command_id,
            "metadata": None if self.meta is None else self.meta.to_dict(),
            "power": {
                "voltage_v": self.voltage_v,
                "current_ma": self.current_ma,
                "power_mw": self.power_mw,
                "percentage": self.percentage,
                "power_source": self.power_source,
                "charging": self.charging,
                "powered": self.powered,
                "low_battery": self.low_battery,
                "brownout_risk": self.brownout_risk,
                "fault_code": self.fault_code,
                "stale": self.stale,
                "stamp": self.stamp,
            },
        }
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload


@dataclass(frozen=True)
class HeadPoseResult:
    ok: bool
    result_state: ResultState
    device_id: str
    pan_deg: float | None
    tilt_deg: float | None
    moving: bool
    frame: str = "home"
    stale: bool = False
    stamp: str | None = None
    meta: CommandMeta | None = None
    error: ErrorDetail | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "result_state": self.result_state.value,
            "device_id": self.device_id,
            "command_id": None if self.meta is None else self.meta.command_id,
            "metadata": None if self.meta is None else self.meta.to_dict(),
            "pose": {
                "frame": self.frame,
                "pan_deg": self.pan_deg,
                "tilt_deg": self.tilt_deg,
                "moving": self.moving,
                "stale": self.stale,
                "stamp": self.stamp,
            },
        }
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload


def utc_timestamp(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")
