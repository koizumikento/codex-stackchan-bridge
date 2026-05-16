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
    LED = "led"
    OBSERVE = "observe"
    AUDIO_PLAY = "audio-play"
    AUDIO_CAPTURE = "audio-capture"
    CAMERA_CAPTURE = "camera-capture"
    NFC_WAIT = "nfc-wait"
    IMU_STREAM = "imu-stream"


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
class DeviceStatus:
    device_id: str
    connected: bool
    device_state: str
    face: str
    last_error: ErrorDetail | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "connected": self.connected,
            "device_state": self.device_state,
            "face": self.face,
            "last_error": None if self.last_error is None else self.last_error.to_dict(),
        }


def utc_timestamp(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")
