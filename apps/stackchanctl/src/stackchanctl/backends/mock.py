from __future__ import annotations

import re
from typing import Any

from stackchanctl.contract import (
    CommandRequest,
    CommandResult,
    CommandType,
    DeviceStatus,
    ErrorDetail,
    Priority,
    ResultState,
)


DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
ALLOWED_FACES = {"neutral", "happy", "thinking", "surprised", "sleepy", "error"}
ALLOWED_MOTIONS = {"nod", "shake", "look-left", "look-right", "look-user", "idle"}
ALLOWED_LEDS = {"off", "progress", "success", "warning", "error", "listening"}
BASELINE_AUDIO_FORMAT = "pcm_s16le"
BASELINE_AUDIO_SAMPLE_RATE = 16000
BASELINE_AUDIO_CHANNELS = 1


class MockBackend:
    """Deterministic backend used by tests, skills, and hardware-free demos."""

    def execute(self, request: CommandRequest) -> CommandResult | DeviceStatus:
        validation_error = validate_common_request(request)
        if validation_error is not None:
            return _rejected(request, validation_error)

        if request.command_type is CommandType.OBSERVE:
            return _observe(request)

        if request.timeout <= 0:
            return CommandResult(
                ok=False,
                result_state=ResultState.TIMEOUT,
                meta=request.meta,
                command=_command_payload(request),
                error=ErrorDetail(
                    code="TIMEOUT",
                    message="command timed out before acceptance",
                    recoverable=True,
                ),
            )

        result_state = ResultState.COMPLETED if request.wait else ResultState.ACCEPTED
        return CommandResult(
            ok=True,
            result_state=result_state,
            meta=request.meta,
            command=_command_payload(request),
        )


def validate_common_request(request: CommandRequest) -> ErrorDetail | None:
    device_id = request.meta.device_id
    if not DEVICE_ID_PATTERN.fullmatch(device_id):
        return ErrorDetail(
            code="INVALID_DEVICE_ID",
            message=f"invalid device_id {device_id!r}; use ASCII letters, numbers, '_' or '-'",
            recoverable=False,
        )

    if device_id in {"missing", "unknown"}:
        return ErrorDetail(
            code="DEVICE_NOT_FOUND",
            message=f"device {device_id!r} is not registered",
            recoverable=False,
        )

    if request.meta.priority is Priority.SAFETY:
        return ErrorDetail(
            code="INVALID_PRIORITY",
            message="CLI priority SAFETY is reserved for bridge and firmware internals",
            recoverable=False,
        )

    if request.command_type is CommandType.FACE and request.args["name"] not in ALLOWED_FACES:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message=f"unknown face {request.args['name']!r}",
            recoverable=False,
        )

    if request.command_type is CommandType.MOTION and request.args["name"] not in ALLOWED_MOTIONS:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message=f"unknown motion {request.args['name']!r}",
            recoverable=False,
        )

    if request.command_type is CommandType.LED and request.args["pattern"] not in ALLOWED_LEDS:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message=f"unknown LED pattern {request.args['pattern']!r}",
            recoverable=False,
        )

    if request.command_type is CommandType.SAY and not request.args["text"]:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message="say requires non-empty text",
            recoverable=False,
        )

    if request.command_type is CommandType.AUDIO_PLAY and not request.args["path"]:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message="audio play requires a path",
            recoverable=False,
        )

    if request.command_type is CommandType.AUDIO_CAPTURE:
        seconds = float(request.args["seconds"])
        if seconds <= 0:
            return ErrorDetail(
                code="UNKNOWN_COMMAND",
                message="audio capture requires a positive duration",
                recoverable=False,
            )
        if not request.args["output"]:
            return ErrorDetail(
                code="UNKNOWN_COMMAND",
                message="audio capture requires an output path",
                recoverable=False,
            )

    if request.command_type is CommandType.CAMERA_CAPTURE:
        quality = int(request.args["quality"])
        if quality < 1 or quality > 95:
            return ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera quality must be between 1 and 95",
                recoverable=True,
            )
        if not request.args["output"]:
            return ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera capture requires an output path",
                recoverable=True,
            )

    if request.command_type is CommandType.IMU_STREAM:
        hz = float(request.args["hz"])
        if hz < 10 or hz > 30:
            return ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="IMU stream rate must be between 10 and 30 Hz",
                recoverable=False,
            )

    return None


def _observe(request: CommandRequest) -> DeviceStatus:
    if request.meta.device_id == "disconnected":
        return DeviceStatus(
            device_id=request.meta.device_id,
            connected=False,
            device_state="disconnected",
            face="neutral",
            last_error=ErrorDetail(
                code="TRANSPORT_DISCONNECTED",
                message="mock device is disconnected",
                recoverable=True,
            ),
        )

    return DeviceStatus(
        device_id=request.meta.device_id,
        connected=True,
        device_state="idle",
        face="neutral",
    )


def _rejected(request: CommandRequest, error: ErrorDetail) -> CommandResult:
    return CommandResult(
        ok=False,
        result_state=ResultState.REJECTED,
        meta=request.meta,
        command=_command_payload(request),
        error=error,
    )


def _command_payload(request: CommandRequest) -> dict[str, Any]:
    if request.command_type is CommandType.SAY:
        return {"type": "say", "text_length": len(request.args["text"])}
    if request.command_type is CommandType.FACE:
        return {"type": "face", "name": request.args["name"]}
    if request.command_type is CommandType.MOTION:
        return {"type": "motion", "name": request.args["name"]}
    if request.command_type is CommandType.LED:
        return {"type": "led", "pattern": request.args["pattern"]}
    if request.command_type is CommandType.AUDIO_PLAY:
        return {
            "type": "audio.play",
            "path": request.args["path"],
            "format": BASELINE_AUDIO_FORMAT,
            "sample_rate": BASELINE_AUDIO_SAMPLE_RATE,
            "channels": BASELINE_AUDIO_CHANNELS,
            "chunk_ms": 20,
            "max_chunk_ms": 40,
        }
    if request.command_type is CommandType.AUDIO_CAPTURE:
        return {
            "type": "audio.capture",
            "seconds": request.args["seconds"],
            "output": request.args["output"],
            "format": BASELINE_AUDIO_FORMAT,
            "sample_rate": BASELINE_AUDIO_SAMPLE_RATE,
            "channels": BASELINE_AUDIO_CHANNELS,
            "chunk_ms": 20,
            "max_chunk_ms": 40,
        }
    if request.command_type is CommandType.CAMERA_CAPTURE:
        return {
            "type": "camera.capture",
            "output": request.args["output"],
            "format": "jpeg",
            "width": 320,
            "height": 240,
            "quality": request.args["quality"],
            "max_payload_bytes": 98304,
        }
    if request.command_type is CommandType.NFC_WAIT:
        return {
            "type": "nfc.wait",
            "events": ["nfc_detected", "nfc_removed"],
            "tag_id_logging": "redacted",
        }
    if request.command_type is CommandType.IMU_STREAM:
        return {
            "type": "imu.stream",
            "hz": request.args["hz"],
            "topic": "imu/raw",
            "status_field": False,
        }
    return {"type": request.command_type.value}
