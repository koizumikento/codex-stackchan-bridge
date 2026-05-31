from __future__ import annotations

from dataclasses import replace
import math
import re
from typing import Any

from stackchanctl.contract import (
    CapabilityStatus,
    CommandRequest,
    CommandResult,
    CommandType,
    DeviceStatus,
    DoctorCheck,
    DoctorResult,
    ErrorDetail,
    Event,
    EventListResult,
    HeadPoseResult,
    PowerStatusResult,
    Priority,
    ResultState,
    TranscriptResult,
)


DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
ALLOWED_FACES = {"neutral", "happy", "thinking", "surprised", "sleepy", "error"}
ALLOWED_MOTIONS = {"nod", "shake", "cheerful", "look-left", "look-right", "look-user", "idle"}
ALLOWED_LEDS = {"off", "progress", "success", "warning", "error", "listening"}
MOOD_PRESETS: dict[str, tuple[dict[str, str], ...]] = {
    "coding": (
        {"type": "face", "name": "thinking"},
        {"type": "led", "pattern": "progress"},
    ),
    "thinking": (
        {"type": "face", "name": "thinking"},
        {"type": "led", "pattern": "progress"},
        {"type": "motion", "name": "look-user"},
    ),
    "blocked": (
        {"type": "face", "name": "error"},
        {"type": "led", "pattern": "warning"},
    ),
    "done": (
        {"type": "face", "name": "happy"},
        {"type": "led", "pattern": "success"},
        {"type": "motion", "name": "cheerful"},
    ),
    "idle": (
        {"type": "face", "name": "neutral"},
        {"type": "led", "pattern": "off"},
        {"type": "motion", "name": "idle"},
    ),
}
BASELINE_AUDIO_FORMAT = "pcm_s16le"
BASELINE_AUDIO_SAMPLE_RATE = 16000
BASELINE_AUDIO_CHANNELS = 1
MAX_EVENTS = 32
PAN_MIN_DEG = -128.0
PAN_MAX_DEG = 128.0
TILT_MIN_DEG = 5.0
TILT_MAX_DEG = 85.0
SPEED_MIN = 0
SPEED_MAX = 1000
MIN_NONZERO_DURATION_MS = 100
MAX_DURATION_MS = 2000


def _default_capabilities(device_id: str = "default") -> tuple[CapabilityStatus, ...]:
    audio_state = "unavailable" if device_id == "unsupported_audio" else "available"
    camera_state = "unavailable" if device_id == "unsupported_camera" else "available"
    audio_detail = "UNSUPPORTED_FEATURE" if audio_state == "unavailable" else ""
    camera_detail = "UNSUPPORTED_FEATURE" if camera_state == "unavailable" else ""
    return (
        CapabilityStatus("face", "available"),
        CapabilityStatus("motion", "available"),
        CapabilityStatus("led", "available"),
        CapabilityStatus("audio_playback", audio_state, detail_code=audio_detail),
        CapabilityStatus("audio_capture", audio_state, detail_code=audio_detail),
        CapabilityStatus("camera_snapshot", camera_state, detail_code=camera_detail),
    )


class MockBackend:
    """Deterministic backend used by tests, skills, and hardware-free demos."""

    def __init__(self) -> None:
        self._events_by_device: dict[str, list[Event]] = {}
        self._event_cursors: dict[tuple[str, str], int] = {}
        self._transcripts_by_device: dict[str, dict[str, TranscriptResult]] = {}

    def execute(
        self, request: CommandRequest
    ) -> CommandResult | DeviceStatus | DoctorResult | EventListResult | TranscriptResult | PowerStatusResult | HeadPoseResult:
        validation_error = validate_common_request(request)
        if validation_error is not None:
            return _rejected(request, validation_error)

        if request.command_type is CommandType.OBSERVE:
            return _observe(request)

        if request.timeout <= 0:
            return _timeout_result(request)

        if request.command_type is CommandType.EVENTS_LIST:
            return self._list_events(request)

        if request.command_type is CommandType.EVENTS_NEXT:
            return self._next_event(request)

        if request.command_type is CommandType.EVENTS_CLEAR:
            return self._clear_events(request)

        if request.command_type is CommandType.SPEECH_TRANSCRIPT:
            return self._get_transcript(request)

        if request.command_type is CommandType.POWER_STATUS:
            return _power_status(request)

        if request.command_type is CommandType.MOTION_STATUS:
            return _head_pose_status(request)

        if request.command_type is CommandType.DOCTOR:
            return self._doctor(request)

        if request.command_type is CommandType.MAINTENANCE_CALIBRATION_STATUS:
            return CommandResult(
                ok=True,
                result_state=ResultState.COMPLETED,
                meta=request.meta,
                command=_command_payload(request),
            )

        command_failure = _mock_command_failure(request)
        if command_failure is not None:
            return command_failure

        result_state = ResultState.COMPLETED if request.wait else ResultState.ACCEPTED
        return CommandResult(
            ok=True,
            result_state=result_state,
            meta=request.meta,
            command=_command_payload(request),
        )

    def _list_events(self, request: CommandRequest) -> EventListResult:
        limit = int(request.args["limit"])
        since_event_id = request.args.get("since_event_id")
        events = self._events_for(request.meta.device_id)
        if since_event_id:
            events = _events_after(events, str(since_event_id))
        selected = events[-limit:]
        return EventListResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=request.meta.device_id,
            events=selected,
            cursor=_cursor_for(selected),
            meta=request.meta,
        )

    def _next_event(self, request: CommandRequest) -> EventListResult:
        events = self._events_for(request.meta.device_id)
        after_event_id = request.args.get("after_event_id")
        consumer_id = str(request.args.get("consumer_id") or request.meta.source)
        if after_event_id:
            candidates = _events_after(events, str(after_event_id))
        else:
            cursor = self._event_cursors.get((consumer_id, request.meta.device_id), 0)
            candidates = events[cursor:]
        if not candidates:
            return EventListResult(
                ok=True,
                result_state=ResultState.COMPLETED,
                device_id=request.meta.device_id,
                events=[],
                cursor=None,
                meta=request.meta,
            )
        event = candidates[0]
        self._event_cursors[(consumer_id, request.meta.device_id)] = events.index(event) + 1
        return EventListResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=request.meta.device_id,
            events=[event],
            cursor=event.event_id,
            meta=request.meta,
        )

    def _clear_events(self, request: CommandRequest) -> EventListResult:
        consumer_id = str(request.args.get("consumer_id") or request.meta.source)
        self._event_cursors.pop((consumer_id, request.meta.device_id), None)
        return EventListResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=request.meta.device_id,
            events=[],
            cursor=None,
            meta=request.meta,
        )

    def _get_transcript(self, request: CommandRequest) -> TranscriptResult:
        utterance_id = request.args.get("utterance_id")
        transcripts = self._transcripts_for(request.meta.device_id)
        if utterance_id is None:
            return transcripts["mock-utt-001"]
        transcript = transcripts.get(str(utterance_id))
        if transcript is None:
            return TranscriptResult(
                ok=False,
                result_state=ResultState.REJECTED,
                device_id=request.meta.device_id,
                utterance_id=str(utterance_id),
                transcript=None,
                confidence=None,
                expires_at=None,
                meta=request.meta,
                error=ErrorDetail(
                    code="TRANSCRIPT_NOT_FOUND",
                    message=f"transcript {utterance_id!r} was not found",
                    recoverable=False,
                ),
            )
        return replace(transcript, meta=request.meta)

    def _doctor(self, request: CommandRequest) -> DoctorResult:
        status = _observe(request)
        power = _power_status(request)
        pose = _head_pose_status(request)
        events = self._list_events(
            replace(request, command_type=CommandType.EVENTS_LIST, args={"limit": 5, "since_event_id": None})
        )
        checks: list[DoctorCheck] = [
            DoctorCheck(
                "connection",
                "ok" if status.connected else "failed",
                detail_code="" if status.last_error is None else status.last_error.code,
                message="" if status.last_error is None else status.last_error.message,
                recoverable=None if status.last_error is None else status.last_error.recoverable,
            )
        ]
        for capability in status.capabilities:
            checks.append(
                DoctorCheck(
                    f"capability.{capability.name}",
                    "ok" if capability.state == "available" else "degraded",
                    detail_code=capability.detail_code,
                )
            )
        checks.append(_check_from_result("power", power))
        checks.append(_check_from_result("motion_pose", pose))
        checks.append(
            DoctorCheck(
                "events",
                "ok" if events.ok else "degraded",
                detail_code="" if events.error is None else events.error.code,
            )
        )
        overall_state = "ok" if all(check.state == "ok" for check in checks) else "degraded"
        return DoctorResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=request.meta.device_id,
            backend="mock",
            connected=status.connected,
            overall_state=overall_state,
            checks=tuple(checks),
            device_state=status.device_state,
            firmware_version=status.firmware_version,
            last_error=status.last_error,
            capabilities=status.capabilities,
            meta=request.meta,
        )

    def _events_for(self, device_id: str) -> list[Event]:
        if device_id not in self._events_by_device:
            self._events_by_device[device_id] = [
                Event(
                    event_id="mock-event-0001",
                    device_id=device_id,
                    event_name="picked_up",
                    source="firmware",
                    stamp="2026-05-16T00:00:01Z",
                    command_id=None,
                    payload={},
                ),
                Event(
                    event_id="mock-event-0002",
                    device_id=device_id,
                    event_name="transcript_ready",
                    source="speech_session",
                    stamp="2026-05-16T00:00:02Z",
                    command_id=None,
                    payload={"utterance_id": "mock-utt-001"},
                ),
            ]
        return self._events_by_device[device_id]

    def _transcripts_for(self, device_id: str) -> dict[str, TranscriptResult]:
        if device_id not in self._transcripts_by_device:
            self._transcripts_by_device[device_id] = {
                "mock-utt-001": TranscriptResult(
                    ok=True,
                    result_state=ResultState.COMPLETED,
                    device_id=device_id,
                    utterance_id="mock-utt-001",
                    transcript="mock transcript",
                    confidence=1.0,
                    expires_at="2026-05-16T00:10:02Z",
                    meta=None,
                )
            }
        return self._transcripts_by_device[device_id]


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

    if request.command_type in {
        CommandType.MAINTENANCE_CALIBRATION_STATUS,
        CommandType.MAINTENANCE_CALIBRATION_CAPTURE_NEUTRAL,
        CommandType.MAINTENANCE_CALIBRATION_RESET,
    }:
        if request.meta.source != "human_cli":
            return ErrorDetail(
                code="INVALID_SOURCE",
                message="maintenance calibration commands require source=human_cli",
                recoverable=False,
            )
        if request.command_type in {
            CommandType.MAINTENANCE_CALIBRATION_CAPTURE_NEUTRAL,
            CommandType.MAINTENANCE_CALIBRATION_RESET,
        } and not bool(request.args.get("confirmed")):
            return ErrorDetail(
                code="OPERATOR_CONFIRMATION_REQUIRED",
                message="maintenance calibration write/reset commands require --confirm",
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

    if request.command_type is CommandType.MOTION_POSE:
        pose_error = _validate_pose_args(request)
        if pose_error is not None:
            return pose_error

    if request.command_type is CommandType.MOTION_HOME:
        timing_error = _validate_motion_timing(request)
        if timing_error is not None:
            return timing_error

    if request.command_type is CommandType.LED and request.args["pattern"] not in ALLOWED_LEDS:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message=f"unknown LED pattern {request.args['pattern']!r}",
            recoverable=False,
        )

    if request.command_type is CommandType.MOOD and request.args["name"] not in MOOD_PRESETS:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message=f"unknown mood {request.args['name']!r}",
            recoverable=False,
        )

    if request.command_type is CommandType.SAY and not request.args["text"]:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message="say requires non-empty text",
            recoverable=False,
        )
    if request.command_type is CommandType.SAY:
        face_hint = str(request.args.get("face_hint", "")).strip()
        if face_hint and face_hint not in ALLOWED_FACES:
            return ErrorDetail(
                code="UNKNOWN_COMMAND",
                message=f"unknown face {face_hint!r}",
                recoverable=False,
            )
        motion_hint = str(request.args.get("motion_hint", "")).strip()
        if motion_hint and motion_hint not in ALLOWED_MOTIONS:
            return ErrorDetail(
                code="UNKNOWN_COMMAND",
                message=f"unknown motion {motion_hint!r}",
                recoverable=False,
            )
        after_face = str(request.args.get("after_face", "")).strip()
        if after_face and after_face not in ALLOWED_FACES:
            return ErrorDetail(
                code="UNKNOWN_COMMAND",
                message=f"unknown face {after_face!r}",
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

    if request.command_type in {CommandType.EVENTS_LIST, CommandType.EVENTS_NEXT}:
        limit = int(request.args["limit"])
        if limit < 1 or limit > MAX_EVENTS:
            return ErrorDetail(
                code="UNKNOWN_COMMAND",
                message="events limit must be between 1 and 32",
                recoverable=False,
            )

    return None


def _validate_pose_args(request: CommandRequest) -> ErrorDetail | None:
    try:
        pan_deg = float(request.args["pan_deg"])
        tilt_deg = float(request.args["tilt_deg"])
    except (KeyError, TypeError, ValueError):
        return ErrorDetail(
            code="SERVO_LIMIT_EXCEEDED",
            message="motion pose requires numeric pan_deg and tilt_deg",
            recoverable=True,
        )
    if not math.isfinite(pan_deg) or not math.isfinite(tilt_deg):
        return ErrorDetail(
            code="SERVO_LIMIT_EXCEEDED",
            message="motion pose angles must be finite",
            recoverable=True,
        )
    if pan_deg < PAN_MIN_DEG or pan_deg > PAN_MAX_DEG:
        return ErrorDetail(
            code="SERVO_LIMIT_EXCEEDED",
            message="motion pose pan_deg is outside -128..128",
            recoverable=True,
        )
    if tilt_deg < TILT_MIN_DEG or tilt_deg > TILT_MAX_DEG:
        return ErrorDetail(
            code="SERVO_LIMIT_EXCEEDED",
            message="motion pose tilt_deg is outside 5..85",
            recoverable=True,
        )
    return _validate_motion_timing(request)


def _validate_motion_timing(request: CommandRequest) -> ErrorDetail | None:
    speed = int(request.args.get("speed", 0))
    duration_ms = int(request.args.get("duration_ms", 0))
    if speed < SPEED_MIN or speed > SPEED_MAX:
        return ErrorDetail(
            code="SERVO_LIMIT_EXCEEDED",
            message="motion speed must be between 0 and 1000",
            recoverable=True,
        )
    if duration_ms != 0 and (duration_ms < MIN_NONZERO_DURATION_MS or duration_ms > MAX_DURATION_MS):
        return ErrorDetail(
            code="MOTION_INTERRUPTED",
            message="motion duration must be 0 or between 100 and 2000 ms",
            recoverable=True,
        )
    return None


def _check_from_result(name: str, result: PowerStatusResult | HeadPoseResult) -> DoctorCheck:
    if result.ok:
        return DoctorCheck(name, "ok")
    error = result.error
    return DoctorCheck(
        name,
        "degraded",
        detail_code="" if error is None else error.code,
        message="" if error is None else error.message,
        recoverable=None if error is None else error.recoverable,
    )


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
            meta=request.meta,
            firmware_version="mock-firmware-0.1",
            capabilities=_default_capabilities(request.meta.device_id),
        )

    return DeviceStatus(
        device_id=request.meta.device_id,
        connected=True,
        device_state="idle",
        face="neutral",
        meta=request.meta,
        firmware_version="mock-firmware-0.1",
        capabilities=_default_capabilities(request.meta.device_id),
    )


def _power_status(request: CommandRequest) -> PowerStatusResult:
    if request.meta.device_id == "unsupported_power":
        return PowerStatusResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            voltage_v=None,
            current_ma=None,
            power_mw=None,
            percentage=None,
            power_source="unknown",
            charging=False,
            powered=False,
            low_battery=False,
            brownout_risk=False,
            stale=False,
            meta=request.meta,
            error=ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="power telemetry is not available on this mock device",
                recoverable=False,
            ),
        )
    if request.meta.device_id == "stale_power":
        return PowerStatusResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            voltage_v=3.55,
            current_ma=-90.0,
            power_mw=-319.5,
            percentage=None,
            power_source="battery",
            charging=False,
            powered=True,
            low_battery=True,
            brownout_risk=False,
            fault_code=None,
            stale=True,
            stamp="2026-05-16T00:00:00Z",
            meta=request.meta,
            error=ErrorDetail(
                code="STALE_TELEMETRY",
                message="power telemetry is stale",
                recoverable=True,
            ),
        )
    return PowerStatusResult(
        ok=True,
        result_state=ResultState.COMPLETED,
        device_id=request.meta.device_id,
        voltage_v=4.92,
        current_ma=184.0,
        power_mw=905.3,
        percentage=None,
        power_source="usb",
        charging=True,
        powered=True,
        low_battery=False,
        brownout_risk=False,
        fault_code=None,
        stale=False,
        stamp="2026-05-16T00:00:03Z",
        meta=request.meta,
    )


def _head_pose_status(request: CommandRequest) -> HeadPoseResult:
    if request.meta.device_id == "unsupported_pose":
        return HeadPoseResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            pan_deg=None,
            tilt_deg=None,
            moving=False,
            meta=request.meta,
            error=ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="head pose telemetry is not available on this mock device",
                recoverable=False,
            ),
        )
    if request.meta.device_id == "stale_pose":
        return HeadPoseResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            pan_deg=15.0,
            tilt_deg=20.0,
            moving=False,
            stale=True,
            stamp="2026-05-16T00:00:00Z",
            meta=request.meta,
            error=ErrorDetail(
                code="STALE_TELEMETRY",
                message="head pose telemetry is stale",
                recoverable=True,
            ),
        )
    if request.meta.device_id == "uncalibrated_pose":
        return HeadPoseResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            pan_deg=None,
            tilt_deg=None,
            moving=False,
            meta=request.meta,
            error=ErrorDetail(
                code="CALIBRATION_INVALID",
                message="head pose calibration is invalid",
                recoverable=True,
            ),
        )
    if request.meta.device_id == "servo_read_failed":
        return HeadPoseResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            pan_deg=None,
            tilt_deg=None,
            moving=False,
            meta=request.meta,
            error=ErrorDetail(
                code="SERVO_READ_FAILED",
                message="servo current position could not be read",
                recoverable=True,
            ),
        )
    return HeadPoseResult(
        ok=True,
        result_state=ResultState.COMPLETED,
        device_id=request.meta.device_id,
        pan_deg=0.0,
        tilt_deg=0.0,
        moving=False,
        stale=False,
        stamp="2026-05-16T00:00:03Z",
        meta=request.meta,
    )


def _rejected(
    request: CommandRequest, error: ErrorDetail
) -> CommandResult | EventListResult | TranscriptResult | PowerStatusResult | HeadPoseResult:
    if request.command_type in {
        CommandType.EVENTS_LIST,
        CommandType.EVENTS_NEXT,
        CommandType.EVENTS_CLEAR,
    }:
        return EventListResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            events=[],
            meta=request.meta,
            error=error,
        )
    if request.command_type is CommandType.SPEECH_TRANSCRIPT:
        return TranscriptResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            utterance_id=request.args.get("utterance_id"),
            transcript=None,
            confidence=None,
            expires_at=None,
            meta=request.meta,
            error=error,
        )
    if request.command_type is CommandType.POWER_STATUS:
        return PowerStatusResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            voltage_v=None,
            current_ma=None,
            power_mw=None,
            percentage=None,
            power_source="unknown",
            charging=False,
            powered=False,
            low_battery=False,
            brownout_risk=False,
            meta=request.meta,
            error=error,
        )
    if request.command_type is CommandType.MOTION_STATUS:
        return HeadPoseResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            pan_deg=None,
            tilt_deg=None,
            moving=False,
            meta=request.meta,
            error=error,
        )
    return CommandResult(
        ok=False,
        result_state=ResultState.REJECTED,
        meta=request.meta,
        command=_command_payload(request),
        error=error,
    )


def _timeout_result(
    request: CommandRequest,
) -> CommandResult | EventListResult | TranscriptResult | PowerStatusResult | HeadPoseResult:
    error = ErrorDetail(
        code="TIMEOUT",
        message="command timed out before acceptance",
        recoverable=True,
    )
    if request.command_type in {
        CommandType.EVENTS_LIST,
        CommandType.EVENTS_NEXT,
        CommandType.EVENTS_CLEAR,
    }:
        return EventListResult(
            ok=False,
            result_state=ResultState.TIMEOUT,
            device_id=request.meta.device_id,
            events=[],
            meta=request.meta,
            error=error,
        )
    if request.command_type is CommandType.SPEECH_TRANSCRIPT:
        return TranscriptResult(
            ok=False,
            result_state=ResultState.TIMEOUT,
            device_id=request.meta.device_id,
            utterance_id=request.args.get("utterance_id"),
            transcript=None,
            confidence=None,
            expires_at=None,
            meta=request.meta,
            error=error,
        )
    if request.command_type is CommandType.POWER_STATUS:
        return PowerStatusResult(
            ok=False,
            result_state=ResultState.TIMEOUT,
            device_id=request.meta.device_id,
            voltage_v=None,
            current_ma=None,
            power_mw=None,
            percentage=None,
            power_source="unknown",
            charging=False,
            powered=False,
            low_battery=False,
            brownout_risk=False,
            meta=request.meta,
            error=error,
        )
    if request.command_type is CommandType.MOTION_STATUS:
        return HeadPoseResult(
            ok=False,
            result_state=ResultState.TIMEOUT,
            device_id=request.meta.device_id,
            pan_deg=None,
            tilt_deg=None,
            moving=False,
            meta=request.meta,
            error=error,
        )
    return CommandResult(
        ok=False,
        result_state=ResultState.TIMEOUT,
        meta=request.meta,
        command=_command_payload(request),
        error=error,
    )


def _command_timeout_result(request: CommandRequest, message: str) -> CommandResult:
    return CommandResult(
        ok=False,
        result_state=ResultState.TIMEOUT,
        meta=request.meta,
        command=_command_payload(request),
        error=ErrorDetail(code="TIMEOUT", message=message, recoverable=True),
    )


def _command_error_result(request: CommandRequest, error: ErrorDetail) -> CommandResult:
    return CommandResult(
        ok=False,
        result_state=ResultState.REJECTED,
        meta=request.meta,
        command=_command_payload(request),
        error=error,
    )


def _mock_command_failure(request: CommandRequest) -> CommandResult | None:
    device_id = request.meta.device_id
    if request.command_type is CommandType.AUDIO_PLAY:
        if device_id == "audio_timeout":
            return _command_timeout_result(request, "mock audio playback timed out")
        if device_id == "audio_underrun":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="AUDIO_UNDERRUN",
                    message="mock audio playback underrun",
                    recoverable=True,
                ),
            )
        if device_id == "audio_malformed":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="MALFORMED_AUDIO_CHUNK",
                    message="mock audio playback chunk was malformed",
                    recoverable=True,
                ),
            )
        if device_id == "audio_disconnected":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="TRANSPORT_DISCONNECTED",
                    message="mock audio playback disconnected mid-stream",
                    recoverable=True,
                ),
            )
        if device_id == "unsupported_audio":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="UNSUPPORTED_FEATURE",
                    message="audio playback is not available on this mock device",
                    recoverable=False,
                ),
            )

    if request.command_type is CommandType.AUDIO_CAPTURE:
        if device_id == "audio_timeout":
            return _command_timeout_result(request, "mock audio capture timed out")
        if device_id == "mic_overrun":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="MIC_OVERRUN",
                    message="mock microphone overrun dropped the current chunk",
                    recoverable=True,
                ),
            )
        if device_id == "audio_capture_failed":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="AUDIO_CAPTURE_FAILED",
                    message="mock audio capture failed",
                    recoverable=True,
                ),
            )
        if device_id == "audio_malformed":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="MALFORMED_AUDIO_CHUNK",
                    message="mock audio capture chunk was malformed",
                    recoverable=True,
                ),
            )
        if device_id == "audio_disconnected":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="TRANSPORT_DISCONNECTED",
                    message="mock audio capture disconnected mid-stream",
                    recoverable=True,
                ),
            )
        if device_id == "unsupported_audio":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="UNSUPPORTED_FEATURE",
                    message="audio capture is not available on this mock device",
                    recoverable=False,
                ),
            )

    if request.command_type is CommandType.CAMERA_CAPTURE:
        if device_id == "camera_timeout":
            return _command_timeout_result(request, "mock camera capture timed out")
        if device_id == "camera_oversize":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="CAMERA_CAPTURE_FAILED",
                    message="mock camera frame exceeded 96 KiB and was discarded",
                    recoverable=True,
                ),
            )
        if device_id == "unsupported_camera":
            return _command_error_result(
                request,
                ErrorDetail(
                    code="UNSUPPORTED_FEATURE",
                    message="camera capture is not available on this mock device",
                    recoverable=False,
                ),
            )
    return None


def _command_payload(request: CommandRequest) -> dict[str, Any]:
    if request.command_type is CommandType.SAY:
        payload: dict[str, Any] = {
            "type": "say",
            "text_length": len(request.args["text"]),
        }
        voice = str(request.args.get("voice", "")).strip()
        if voice:
            payload["voice_profile"] = voice
        face_hint = str(request.args.get("face_hint", "")).strip()
        if face_hint:
            payload["face_hint"] = face_hint
        motion_hint = str(request.args.get("motion_hint", "")).strip()
        if motion_hint:
            payload["motion_hint"] = motion_hint
        after_face = str(request.args.get("after_face", "")).strip()
        if after_face:
            payload["after_face"] = after_face
        return payload
    if request.command_type is CommandType.FACE:
        return {"type": "face", "name": request.args["name"]}
    if request.command_type is CommandType.MOTION:
        return {"type": "motion", "name": request.args["name"]}
    if request.command_type is CommandType.MOTION_POSE:
        return {
            "type": "motion.pose",
            "frame": "home",
            "pan_deg": request.args["pan_deg"],
            "tilt_deg": request.args["tilt_deg"],
            "speed": request.args["speed"],
            "duration_ms": request.args["duration_ms"],
        }
    if request.command_type is CommandType.MOTION_HOME:
        return {
            "type": "motion.home",
            "frame": "home",
            "speed": request.args["speed"],
            "duration_ms": request.args["duration_ms"],
        }
    if request.command_type is CommandType.MOTION_STATUS:
        return {"type": "motion.status", "frame": "home"}
    if request.command_type is CommandType.LED:
        return {"type": "led", "pattern": request.args["pattern"]}
    if request.command_type is CommandType.MOOD:
        name = str(request.args["name"])
        steps = MOOD_PRESETS.get(name, ())
        return {
            "type": "mood",
            "name": name,
            "steps": [dict(step) for step in steps],
        }
    if request.command_type is CommandType.DEMO:
        return {
            "type": "demo",
            "include_say": bool(request.args.get("include_say")),
            "include_media": bool(request.args.get("include_media")),
            "steps": _demo_steps(request),
        }
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
        payload = {
            "type": "audio.capture",
            "seconds": request.args["seconds"],
            "output": request.args["output"],
            "format": BASELINE_AUDIO_FORMAT,
            "sample_rate": BASELINE_AUDIO_SAMPLE_RATE,
            "channels": BASELINE_AUDIO_CHANNELS,
            "chunk_ms": 20,
            "max_chunk_ms": 40,
        }
        if bool(request.args.get("cue_led")):
            payload["cue"] = "led.progress"
        return payload
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
            "identifier_policy": "reference",
        }
    if request.command_type is CommandType.IMU_STREAM:
        return {
            "type": "imu.stream",
            "hz": request.args["hz"],
            "topic": "imu/raw",
            "status_field": False,
        }
    if request.command_type is CommandType.EVENTS_LIST:
        return {"type": "events.list", "limit": request.args["limit"]}
    if request.command_type is CommandType.EVENTS_NEXT:
        return {"type": "events.next", "limit": request.args["limit"]}
    if request.command_type is CommandType.EVENTS_CLEAR:
        return {"type": "events.clear"}
    if request.command_type is CommandType.SPEECH_TRANSCRIPT:
        return {
            "type": "speech.transcript",
            "utterance_id": request.args.get("utterance_id"),
        }
    if request.command_type is CommandType.POWER_STATUS:
        return {"type": "power.status"}
    if request.command_type is CommandType.MAINTENANCE_CALIBRATION_STATUS:
        return {
            "type": "maintenance.calibration.status",
            "calibration_valid": True,
            "store": "firmware_nvs",
            "mode": "mock",
            "write": False,
        }
    if request.command_type is CommandType.MAINTENANCE_CALIBRATION_CAPTURE_NEUTRAL:
        return {
            "type": "maintenance.calibration.capture-neutral",
            "confirmed": bool(request.args.get("confirmed")),
            "calibration_valid": True,
            "store": "firmware_nvs",
            "mode": "mock",
            "write": True,
        }
    if request.command_type is CommandType.MAINTENANCE_CALIBRATION_RESET:
        return {
            "type": "maintenance.calibration.reset",
            "confirmed": bool(request.args.get("confirmed")),
            "calibration_valid": False,
            "reset_to": "invalid",
            "store": "firmware_nvs",
            "mode": "mock",
            "write": True,
        }
    return {"type": request.command_type.value}


def _demo_steps(request: CommandRequest) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {"name": "observe", "state": "completed"},
        {"name": "face.neutral", "state": "completed"},
        {"name": "face.happy", "state": "completed"},
        {"name": "face.thinking", "state": "completed"},
        {"name": "led.progress", "state": "completed"},
        {"name": "led.success", "state": "completed"},
        {"name": "led.off", "state": "completed"},
        {"name": "motion.nod", "state": "completed"},
    ]
    if bool(request.args.get("include_say")):
        step: dict[str, Any] = {"name": "say", "state": "completed", "text_length": 2}
        voice = str(request.args.get("voice", "")).strip()
        if voice:
            step["voice_profile"] = voice
        steps.append(step)
    else:
        steps.append({"name": "say", "state": "skipped", "reason": "not_requested"})
    if bool(request.args.get("include_media")):
        steps.append(
            {
                "name": "audio.capture",
                "state": "completed",
                "output": request.args["audio_output"],
            }
        )
        steps.append(
            {
                "name": "camera.capture",
                "state": "completed",
                "output": request.args["camera_output"],
            }
        )
    else:
        steps.append({"name": "audio.capture", "state": "skipped", "reason": "not_requested"})
        steps.append({"name": "camera.capture", "state": "skipped", "reason": "not_requested"})
    return steps


def _events_after(events: list[Event], event_id: str) -> list[Event]:
    for index, event in enumerate(events):
        if event.event_id == event_id:
            return events[index + 1 :]
    return events


def _cursor_for(events: list[Event]) -> str | None:
    if not events:
        return None
    return events[-1].event_id
