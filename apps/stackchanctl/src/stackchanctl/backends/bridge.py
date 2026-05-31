from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC, datetime
import math
import os
from pathlib import Path
import time
from typing import Any, Protocol
import wave

from stackchanctl.backends.mock import MOOD_PRESETS
from stackchanctl.backends.mock import validate_common_request
from stackchanctl.contract import (
    CapabilityStatus,
    CommandMeta,
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
    ResultState,
    TranscriptResult,
)

REDACTED = "<redacted>"
SENSITIVE_EVENT_FIELDS = frozenset(
    {
        "audio",
        "audio_data",
        "audio_payload",
        "api_key",
        "authorization",
        "frame",
        "image",
        "image_data",
        "image_payload",
        "ir_code",
        "jpeg",
        "nfc_tag_id",
        "pcm",
        "pcm_data",
        "protocol",
        "protocol_dump",
        "raw_ir",
        "raw_ir_code",
        "raw_remote_code",
        "remote_code",
        "speech_text",
        "tag_id",
        "text",
        "transcript",
        "uid",
        "utterance",
    }
)
SENSITIVE_EVENT_MARKERS = (
    "ir_code",
    "password",
    "protocol_dump",
    "raw_ir",
    "raw_remote",
    "remote_code",
    "secret",
    "token",
)
SENSITIVE_EVENT_KEY_PARTS = ("transcript", "speech_text")
AUDIO_PLAYBACK_DIRECTION = 1
AUDIO_CAPTURE_DIRECTION = 2
AUDIO_PCM_S16LE_FORMAT = 1
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_CHUNK_BYTES = 640
AUDIO_PLAYBACK_FIRST_GOAL_BYTES_ENV = "STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES"
AUDIO_PLAYBACK_FIRST_GOAL_BYTES_DEFAULT = 0
AUDIO_PLAYBACK_CHUNK_BYTES_ENV = "STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES"
AUDIO_PLAYBACK_CHUNK_INTERVAL_SEC = 0.02
AUDIO_PLAYBACK_DISCOVERY_WAIT_SEC = 0.35
AUDIO_PLAYBACK_EXPECTED_SUBSCRIPTIONS = 1
CAMERA_JPEG_FORMAT = "jpeg"
CAMERA_CHUNK_JPEG_FORMAT = 1
CAMERA_MAX_PAYLOAD_BYTES = 96 * 1024
CAMERA_CHUNK_MAX_BYTES = 256


def _audio_playback_first_goal_bytes() -> int:
    raw_value = os.environ.get(AUDIO_PLAYBACK_FIRST_GOAL_BYTES_ENV)
    if raw_value is None:
        return AUDIO_PLAYBACK_FIRST_GOAL_BYTES_DEFAULT
    try:
        value = int(raw_value)
    except ValueError:
        return AUDIO_PLAYBACK_FIRST_GOAL_BYTES_DEFAULT
    return min(max(value, 0), AUDIO_CHUNK_BYTES)


def _audio_playback_chunk_bytes() -> int:
    raw_value = os.environ.get(AUDIO_PLAYBACK_CHUNK_BYTES_ENV)
    if raw_value is None:
        return AUDIO_CHUNK_BYTES
    try:
        value = int(raw_value)
    except ValueError:
        return AUDIO_CHUNK_BYTES
    value = min(max(value, 2), AUDIO_CHUNK_BYTES)
    if value % 2:
        value -= 1
    return max(value, 2)


class BridgeBackendError(RuntimeError):
    def __init__(self, code: str, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


class BridgeBackendTimeout(TimeoutError):
    pass


@dataclass(frozen=True)
class BridgeCommandResponse:
    ok: bool
    result_state: ResultState
    error: ErrorDetail | None = None


class _AudioCaptureCollector:
    def __init__(self, device_id: str, command_id: str) -> None:
        self.device_id = device_id
        self.command_id = command_id
        self._chunks: dict[int, bytes] = {}
        self.error: ErrorDetail | None = None

    def handle_chunk(self, message) -> None:
        if getattr(message, "device_id", "") != self.device_id:
            return
        if getattr(message, "command_id", "") != self.command_id:
            return
        if int(getattr(message, "direction", 0)) != AUDIO_CAPTURE_DIRECTION:
            return
        if (
            int(getattr(message, "format", 0)) != AUDIO_PCM_S16LE_FORMAT
            or int(getattr(message, "sample_rate", 0)) != AUDIO_SAMPLE_RATE
            or int(getattr(message, "channels", 0)) != AUDIO_CHANNELS
        ):
            self.error = ErrorDetail(
                code="MALFORMED_AUDIO_CHUNK",
                message="audio capture chunk metadata did not match PCM S16LE 16 kHz mono",
                recoverable=True,
            )
            return
        pcm = bytes(getattr(message, "pcm", b""))
        if len(pcm) % 2:
            self.error = ErrorDetail(
                code="MALFORMED_AUDIO_CHUNK",
                message="audio capture chunk had an odd byte length",
                recoverable=True,
            )
            return
        self._chunks[int(getattr(message, "sequence", 0))] = pcm

    def pcm(self) -> bytes:
        if not self._chunks:
            return b""
        expected = list(range(max(self._chunks) + 1))
        if sorted(self._chunks) != expected:
            self.error = ErrorDetail(
                code="AUDIO_CAPTURE_FAILED",
                message="audio capture chunks were not contiguous",
                recoverable=True,
            )
            return b""
        return b"".join(self._chunks[index] for index in expected)


class _CameraFrameCollector:
    def __init__(self, device_id: str, command_id: str) -> None:
        self.device_id = device_id
        self.command_id = command_id
        self._chunks: dict[int, bytes] = {}
        self._total_chunks: int | None = None
        self._total_bytes: int | None = None
        self._saw_end = False
        self.error: ErrorDetail | None = None

    def handle_chunk(self, message) -> None:
        if getattr(message, "device_id", "") != self.device_id:
            return
        if getattr(message, "command_id", "") != self.command_id:
            return
        if int(getattr(message, "format", 0)) != CAMERA_CHUNK_JPEG_FORMAT:
            self.error = ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera frame chunk was not JPEG",
                recoverable=True,
            )
            return
        if int(getattr(message, "width", 0)) != 320 or int(getattr(message, "height", 0)) != 240:
            self.error = ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera frame chunk metadata was not QVGA",
                recoverable=True,
            )
            return
        total_bytes = int(getattr(message, "total_bytes", 0))
        total_chunks = int(getattr(message, "total_chunks", 0))
        if total_bytes <= 0 or total_bytes > CAMERA_MAX_PAYLOAD_BYTES or total_chunks <= 0:
            self.error = ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera frame chunk had invalid bounds metadata",
                recoverable=True,
            )
            return
        if self._total_bytes is not None and self._total_bytes != total_bytes:
            self.error = ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera frame chunk total byte count changed mid-frame",
                recoverable=True,
            )
            return
        if self._total_chunks is not None and self._total_chunks != total_chunks:
            self.error = ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera frame chunk count changed mid-frame",
                recoverable=True,
            )
            return
        data = bytes(getattr(message, "data", b""))
        if not data or len(data) > CAMERA_CHUNK_MAX_BYTES:
            self.error = ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera frame chunk payload size was invalid",
                recoverable=True,
            )
            return
        sequence = int(getattr(message, "sequence", 0))
        if sequence < 0 or sequence >= total_chunks:
            self.error = ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera frame chunk sequence was out of range",
                recoverable=True,
            )
            return
        self._total_bytes = total_bytes
        self._total_chunks = total_chunks
        self._chunks[sequence] = data
        if bool(getattr(message, "end_of_stream", False)):
            self._saw_end = True

    def complete(self) -> bool:
        return (
            self._total_chunks is not None
            and self._saw_end
            and sorted(self._chunks) == list(range(self._total_chunks))
        )

    def jpeg(self) -> bytes:
        if self.error is not None:
            return b""
        if self._total_chunks is None or self._total_bytes is None:
            self.error = ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera capture completed without JPEG chunks",
                recoverable=True,
            )
            return b""
        expected = list(range(self._total_chunks))
        if sorted(self._chunks) != expected:
            self.error = ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera frame chunks were not contiguous",
                recoverable=True,
            )
            return b""
        data = b"".join(self._chunks[index] for index in expected)
        if len(data) != self._total_bytes:
            self.error = ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera frame chunk byte count did not match metadata",
                recoverable=True,
            )
            return b""
        return data


class BridgeClient(Protocol):
    def get_status(self, meta: CommandMeta, timeout: float) -> DeviceStatus:
        raise NotImplementedError

    def set_face(
        self, meta: CommandMeta, name: str, timeout: float
    ) -> BridgeCommandResponse:
        raise NotImplementedError

    def set_led(
        self, meta: CommandMeta, pattern: str, timeout: float
    ) -> BridgeCommandResponse:
        raise NotImplementedError

    def run_motion(
        self, meta: CommandMeta, name: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        raise NotImplementedError

    def move_head_pose(
        self,
        meta: CommandMeta,
        pan_deg: float,
        tilt_deg: float,
        speed: int,
        duration_ms: int,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        raise NotImplementedError

    def home_head_pose(
        self,
        meta: CommandMeta,
        speed: int,
        duration_ms: int,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        raise NotImplementedError

    def say(
        self,
        meta: CommandMeta,
        text: str,
        voice: str,
        face_hint: str,
        motion_hint: str,
        after_face: str,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        raise NotImplementedError

    def play_audio(
        self, meta: CommandMeta, path: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        raise NotImplementedError

    def capture_audio(
        self,
        meta: CommandMeta,
        seconds: float,
        output: str,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        raise NotImplementedError

    def capture_camera(
        self, meta: CommandMeta, output: str, quality: int, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        raise NotImplementedError

    def list_events(
        self,
        meta: CommandMeta,
        limit: int,
        since_event_id: str | None,
        timeout: float,
    ) -> EventListResult:
        raise NotImplementedError

    def next_event(
        self,
        meta: CommandMeta,
        consumer_id: str,
        after_event_id: str | None,
        timeout: float,
    ) -> EventListResult:
        raise NotImplementedError

    def clear_events(
        self, meta: CommandMeta, consumer_id: str, timeout: float
    ) -> EventListResult:
        raise NotImplementedError

    def get_transcript(
        self, meta: CommandMeta, utterance_id: str | None, timeout: float
    ) -> TranscriptResult:
        raise NotImplementedError

    def get_power_status(self, meta: CommandMeta, timeout: float) -> PowerStatusResult:
        raise NotImplementedError

    def get_head_pose(self, meta: CommandMeta, timeout: float) -> HeadPoseResult:
        raise NotImplementedError


class BridgeBackend:
    """Backend that talks to the stackchan_bridge facade resources."""

    def __init__(self, client: BridgeClient | None = None) -> None:
        self._client = client

    def execute(
        self, request: CommandRequest
    ) -> CommandResult | DeviceStatus | DoctorResult | EventListResult | TranscriptResult | PowerStatusResult | HeadPoseResult:
        validation_error = validate_common_request(request)
        if validation_error is not None:
            return _rejected(request, validation_error)

        try:
            client = self._get_client()
            if request.command_type is CommandType.OBSERVE:
                return replace(
                    client.get_status(request.meta, request.timeout),
                    meta=request.meta,
                )
            if request.command_type is CommandType.DOCTOR:
                return self._execute_doctor_result(request, client)
            if request.command_type in {
                CommandType.EVENTS_LIST,
                CommandType.EVENTS_NEXT,
                CommandType.EVENTS_CLEAR,
                CommandType.SPEECH_TRANSCRIPT,
                CommandType.POWER_STATUS,
                CommandType.MOTION_STATUS,
            }:
                return self._execute_observation(request, client)
            if request.command_type is CommandType.DEMO:
                return self._execute_demo_result(request, client)
            response = self._execute_command(request, client)
        except BridgeBackendTimeout:
            return _timeout_result(request)
        except BridgeBackendError as exc:
            return _error_result(
                request,
                ErrorDetail(
                    code=exc.code,
                    message=str(exc),
                    recoverable=exc.recoverable,
                ),
            )

        return CommandResult(
            ok=response.ok,
            result_state=response.result_state,
            meta=request.meta,
            command=_command_payload(request),
            error=response.error,
        )

    def _get_client(self) -> BridgeClient:
        if self._client is None:
            self._client = RclpyBridgeClient()
        return self._client

    def close(self) -> None:
        if self._client is None:
            return
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
        self._client = None

    def _execute_command(
        self, request: CommandRequest, client: BridgeClient
    ) -> BridgeCommandResponse:
        if request.command_type is CommandType.FACE:
            return client.set_face(
                request.meta, str(request.args["name"]), request.timeout
            )
        if request.command_type is CommandType.LED:
            return client.set_led(
                request.meta, str(request.args["pattern"]), request.timeout
            )
        if request.command_type is CommandType.MOOD:
            return self._execute_mood(request, client)
        if request.command_type is CommandType.MOTION:
            return client.run_motion(
                request.meta,
                str(request.args["name"]),
                wait=request.wait,
                timeout=request.timeout,
            )
        if request.command_type is CommandType.MOTION_POSE:
            return client.move_head_pose(
                request.meta,
                float(request.args["pan_deg"]),
                float(request.args["tilt_deg"]),
                int(request.args["speed"]),
                int(request.args["duration_ms"]),
                wait=request.wait,
                timeout=request.timeout,
            )
        if request.command_type is CommandType.MOTION_HOME:
            return client.home_head_pose(
                request.meta,
                int(request.args["speed"]),
                int(request.args["duration_ms"]),
                wait=request.wait,
                timeout=request.timeout,
            )
        if request.command_type is CommandType.SAY:
            return client.say(
                request.meta,
                str(request.args["text"]),
                str(request.args.get("voice", "")),
                str(request.args.get("face_hint", "")),
                str(request.args.get("motion_hint", "")),
                str(request.args.get("after_face", "")),
                wait=request.wait,
                timeout=request.timeout,
            )
        if request.command_type is CommandType.AUDIO_PLAY:
            return client.play_audio(
                request.meta,
                str(request.args["path"]),
                wait=request.wait,
                timeout=request.timeout,
            )
        if request.command_type is CommandType.AUDIO_CAPTURE:
            return self._execute_audio_capture(request, client)
        if request.command_type is CommandType.CAMERA_CAPTURE:
            return client.capture_camera(
                request.meta,
                str(request.args["output"]),
                int(request.args["quality"]),
                wait=request.wait,
                timeout=request.timeout,
            )
        if request.command_type in {
            CommandType.MAINTENANCE_CALIBRATION_STATUS,
            CommandType.MAINTENANCE_CALIBRATION_CAPTURE_NEUTRAL,
            CommandType.MAINTENANCE_CALIBRATION_RESET,
        }:
            return BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=ErrorDetail(
                    code="UNSUPPORTED_FEATURE",
                    message=(
                        "maintenance calibration requires a firmware-owned "
                        "maintenance service before bridge execution"
                    ),
                    recoverable=True,
                ),
            )
        raise BridgeBackendError(
            "UNSUPPORTED_FEATURE",
            f"bridge backend does not support {request.command_type.value!r} yet",
            recoverable=False,
        )

    def _execute_audio_capture(
        self, request: CommandRequest, client: BridgeClient
    ) -> BridgeCommandResponse:
        if not bool(request.args.get("cue_led")):
            return client.capture_audio(
                request.meta,
                float(request.args["seconds"]),
                str(request.args["output"]),
                wait=request.wait,
                timeout=request.timeout,
            )

        cue_response = client.set_led(request.meta, "progress", request.timeout)
        if not cue_response.ok:
            return cue_response
        try:
            capture_response = client.capture_audio(
                request.meta,
                float(request.args["seconds"]),
                str(request.args["output"]),
                wait=request.wait,
                timeout=request.timeout,
            )
        finally:
            off_response = client.set_led(request.meta, "off", request.timeout)
        if not capture_response.ok:
            return capture_response
        if not off_response.ok:
            return off_response
        return capture_response

    def _execute_mood(
        self, request: CommandRequest, client: BridgeClient
    ) -> BridgeCommandResponse:
        name = str(request.args["name"])
        final_state = ResultState.COMPLETED if request.wait else ResultState.ACCEPTED
        for step in MOOD_PRESETS[name]:
            step_type = step["type"]
            if step_type == "face":
                response = client.set_face(request.meta, step["name"], request.timeout)
            elif step_type == "led":
                response = client.set_led(request.meta, step["pattern"], request.timeout)
            elif step_type == "motion":
                response = client.run_motion(
                    request.meta,
                    step["name"],
                    wait=request.wait,
                    timeout=request.timeout,
                )
            else:  # pragma: no cover - preset table guard
                return BridgeCommandResponse(
                    ok=False,
                    result_state=ResultState.REJECTED,
                    error=ErrorDetail(
                        code="UNKNOWN_COMMAND",
                        message=f"unsupported mood step {step_type!r}",
                        recoverable=False,
                    ),
                )
            if not response.ok or response.result_state in {
                ResultState.REJECTED,
                ResultState.TIMEOUT,
            }:
                return response
        return BridgeCommandResponse(ok=True, result_state=final_state)

    def _execute_demo_result(
        self, request: CommandRequest, client: BridgeClient
    ) -> CommandResult:
        steps: list[dict[str, object]] = []

        def command() -> dict[str, object]:
            payload = _command_payload(request)
            payload["steps"] = steps
            return payload

        status = client.get_status(request.meta, request.timeout)
        if not status.connected:
            error = status.last_error or ErrorDetail(
                code="TRANSPORT_DISCONNECTED",
                message="device is disconnected",
                recoverable=True,
            )
            steps.append({"name": "observe", "state": "failed", "error_code": error.code})
            return CommandResult(
                ok=False,
                result_state=ResultState.REJECTED,
                meta=request.meta,
                command=command(),
                error=error,
            )
        steps.append({"name": "observe", "state": "completed"})

        face_steps = (("face.neutral", "neutral"), ("face.happy", "happy"), ("face.thinking", "thinking"))
        for step_name, face in face_steps:
            response = client.set_face(request.meta, face, request.timeout)
            failed = _append_demo_step(steps, step_name, response)
            if failed is not None:
                return _demo_failed_result(request, command(), failed)

        for step_name, led in (("led.progress", "progress"), ("led.success", "success"), ("led.off", "off")):
            response = client.set_led(request.meta, led, request.timeout)
            failed = _append_demo_step(steps, step_name, response)
            if failed is not None:
                return _demo_failed_result(request, command(), failed)

        motion_response = client.run_motion(
            request.meta,
            "nod",
            wait=request.wait,
            timeout=request.timeout,
        )
        failed = _append_demo_step(steps, "motion.nod", motion_response, degraded_codes={"CALIBRATION_INVALID"})
        if failed is not None:
            return _demo_failed_result(request, command(), failed)

        if bool(request.args.get("include_say")):
            say_response = client.say(
                request.meta,
                "OK",
                str(request.args.get("voice", "")),
                "happy",
                "cheerful",
                "happy",
                wait=request.wait,
                timeout=request.timeout,
            )
            failed = _append_demo_step(steps, "say", say_response)
            if failed is not None:
                return _demo_failed_result(request, command(), failed)
        else:
            steps.append({"name": "say", "state": "skipped", "reason": "not_requested"})

        if bool(request.args.get("include_media")):
            output_dir = Path(str(request.args["output_dir"]))
            output_dir.mkdir(parents=True, exist_ok=True)
            capture_audio_response = client.capture_audio(
                request.meta,
                1.0,
                str(request.args["audio_output"]),
                wait=True,
                timeout=request.timeout,
            )
            failed = _append_demo_step(
                steps,
                "audio.capture",
                capture_audio_response,
                skipped_codes={"UNSUPPORTED_FEATURE"},
            )
            if failed is not None:
                return _demo_failed_result(request, command(), failed)
            capture_camera_response = client.capture_camera(
                request.meta,
                str(request.args["camera_output"]),
                80,
                wait=True,
                timeout=request.timeout,
            )
            failed = _append_demo_step(
                steps,
                "camera.capture",
                capture_camera_response,
                skipped_codes={"UNSUPPORTED_FEATURE"},
            )
            if failed is not None:
                return _demo_failed_result(request, command(), failed)
        else:
            steps.append({"name": "audio.capture", "state": "skipped", "reason": "not_requested"})
            steps.append({"name": "camera.capture", "state": "skipped", "reason": "not_requested"})

        return CommandResult(
            ok=True,
            result_state=ResultState.COMPLETED if request.wait else ResultState.ACCEPTED,
            meta=request.meta,
            command=command(),
        )

    def _execute_doctor_result(
        self, request: CommandRequest, client: BridgeClient
    ) -> DoctorResult:
        status = replace(client.get_status(request.meta, request.timeout), meta=request.meta)
        checks: list[DoctorCheck] = [
            DoctorCheck(
                "connection",
                "ok" if status.connected else "degraded",
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

        try:
            power = client.get_power_status(request.meta, request.timeout)
        except BridgeBackendError as exc:
            checks.append(
                DoctorCheck("power", "degraded", detail_code=exc.code, message=str(exc), recoverable=exc.recoverable)
            )
        else:
            checks.append(_doctor_check_from_result("power", power))

        try:
            pose = client.get_head_pose(request.meta, request.timeout)
        except BridgeBackendError as exc:
            checks.append(
                DoctorCheck("motion_pose", "degraded", detail_code=exc.code, message=str(exc), recoverable=exc.recoverable)
            )
        else:
            checks.append(_doctor_check_from_result("motion_pose", pose))

        try:
            events = client.list_events(request.meta, 5, None, request.timeout)
        except BridgeBackendError as exc:
            checks.append(
                DoctorCheck("events", "degraded", detail_code=exc.code, message=str(exc), recoverable=exc.recoverable)
            )
        else:
            checks.append(_doctor_check_from_result("events", events))

        overall_state = "ok" if all(check.state == "ok" for check in checks) else "degraded"
        return DoctorResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=request.meta.device_id,
            backend="bridge",
            connected=status.connected,
            overall_state=overall_state,
            checks=tuple(checks),
            device_state=status.device_state,
            firmware_version=status.firmware_version,
            last_error=status.last_error,
            capabilities=status.capabilities,
            meta=request.meta,
        )

    def _execute_observation(
        self, request: CommandRequest, client: BridgeClient
    ) -> EventListResult | TranscriptResult | PowerStatusResult | HeadPoseResult:
        if request.command_type is CommandType.EVENTS_LIST:
            return client.list_events(
                request.meta,
                int(request.args["limit"]),
                _optional_string_arg(request, "since_event_id"),
                request.timeout,
            )
        if request.command_type is CommandType.EVENTS_NEXT:
            return client.next_event(
                request.meta,
                str(request.args.get("consumer_id") or request.meta.source),
                _optional_string_arg(request, "after_event_id"),
                request.timeout,
            )
        if request.command_type is CommandType.EVENTS_CLEAR:
            return client.clear_events(
                request.meta,
                str(request.args.get("consumer_id") or request.meta.source),
                request.timeout,
            )
        if request.command_type is CommandType.SPEECH_TRANSCRIPT:
            return client.get_transcript(
                request.meta,
                request.args.get("utterance_id"),
                request.timeout,
            )
        if request.command_type is CommandType.POWER_STATUS:
            return client.get_power_status(request.meta, request.timeout)
        if request.command_type is CommandType.MOTION_STATUS:
            return client.get_head_pose(request.meta, request.timeout)
        raise BridgeBackendError(
            "UNSUPPORTED_FEATURE",
            f"bridge backend does not support {request.command_type.value!r} yet",
            recoverable=False,
        )


class RclpyBridgeClient:
    def __init__(self) -> None:
        try:
            import rclpy
            from rclpy.action import ActionClient
            from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
            from stackchan_msgs.action import (
                CaptureAudio,
                CaptureCamera,
                MoveHeadPose,
                PlayAudio,
                RunMotion,
                Say,
            )
            from stackchan_msgs.msg import AudioChunk, CameraFrameChunk
            from stackchan_msgs.srv import GetHeadPose, GetPowerStatus, GetStatus, SetFace, SetLed
            from stackchan_msgs.srv import (
                ClearEventCursor,
                GetTranscript,
                ListEvents,
                NextEvent,
            )
        except ImportError as exc:
            raise BridgeBackendError(
                "BRIDGE_BACKEND_UNAVAILABLE",
                "rclpy or stackchan_msgs is not available; source ROS 2 or use --backend mock",
            ) from exc

        self._rclpy = rclpy
        self._action_client_type = ActionClient
        self._get_status_type = GetStatus
        self._get_head_pose_type = GetHeadPose
        self._get_power_status_type = GetPowerStatus
        self._list_events_type = ListEvents
        self._next_event_type = NextEvent
        self._clear_event_cursor_type = ClearEventCursor
        self._get_transcript_type = GetTranscript
        self._set_face_type = SetFace
        self._set_led_type = SetLed
        self._move_head_pose_type = MoveHeadPose
        self._run_motion_type = RunMotion
        self._say_type = Say
        self._play_audio_type = PlayAudio
        self._capture_audio_type = CaptureAudio
        self._capture_camera_type = CaptureCamera
        self._audio_chunk_type = AudioChunk
        self._camera_chunk_type = CameraFrameChunk
        self._rclpy.init(args=None)
        self._node = self._rclpy.create_node("stackchanctl_bridge_client")
        self._audio_chunk_publishers = {}
        self._audio_playback_chunk_qos = QoSProfile(depth=64)
        self._audio_playback_chunk_qos.reliability = ReliabilityPolicy.RELIABLE
        self._audio_playback_chunk_qos.durability = DurabilityPolicy.VOLATILE
        self._audio_capture_chunk_qos = QoSProfile(depth=8)
        self._audio_capture_chunk_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self._audio_capture_chunk_qos.durability = DurabilityPolicy.VOLATILE
        self._camera_chunk_qos = QoSProfile(depth=64)
        self._camera_chunk_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self._camera_chunk_qos.durability = DurabilityPolicy.VOLATILE

    def get_status(self, meta: CommandMeta, timeout: float) -> DeviceStatus:
        request = self._get_status_type.Request()
        _copy_meta(request.meta, meta)
        client = self._service_client(self._get_status_type, meta.device_id, "get_status", timeout)
        response = self._call_service(client, request, timeout)
        return DeviceStatus(
            device_id=response.device_id,
            connected=bool(response.connected),
            device_state=response.state,
            face=response.face,
            motion=getattr(response, "motion", "idle"),
            last_error=_error_from_ros(response.last_error),
            firmware_version=getattr(response, "firmware_version", ""),
            capabilities=tuple(
                _capability_from_ros(capability)
                for capability in getattr(response, "capabilities", [])
            ),
        )

    def set_face(
        self, meta: CommandMeta, name: str, timeout: float
    ) -> BridgeCommandResponse:
        request = self._set_face_type.Request()
        _copy_meta(request.meta, meta)
        request.name = name
        request.duration_ms = 0
        client = self._service_client(self._set_face_type, meta.device_id, "face/set", timeout)
        response = self._call_service(client, request, timeout)
        return _response_from_ros(response.result)

    def set_led(
        self, meta: CommandMeta, pattern: str, timeout: float
    ) -> BridgeCommandResponse:
        request = self._set_led_type.Request()
        _copy_meta(request.meta, meta)
        request.pattern = pattern
        request.color = ""
        request.duration_ms = 0
        client = self._service_client(self._set_led_type, meta.device_id, "led/set", timeout)
        response = self._call_service(client, request, timeout)
        return _response_from_ros(response.result)

    def run_motion(
        self, meta: CommandMeta, name: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        action = self._action_client_type(
            self._node,
            self._run_motion_type,
            f"/stackchan/{meta.device_id}/cmd/motion/run",
        )
        if not action.wait_for_server(timeout_sec=timeout):
            raise BridgeBackendTimeout()

        goal = self._run_motion_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.name = name
        goal.intensity = 1.0
        goal.duration_ms = 0

        future = action.send_goal_async(goal)
        self._spin_future(future, timeout)
        goal_handle = future.result()
        if goal_handle is None or not goal_handle.accepted:
            return BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=ErrorDetail(
                    code="UNKNOWN_COMMAND",
                    message="motion goal was rejected by bridge facade",
                    recoverable=False,
                ),
            )
        # The facade action result is the bridge's immediate shared Result,
        # not proof that the physical behavior has completed.
        result_future = goal_handle.get_result_async()
        self._spin_future(result_future, timeout)
        response = _response_from_ros(result_future.result().result.result)
        return _normalize_action_response(response, wait=wait)

    def move_head_pose(
        self,
        meta: CommandMeta,
        pan_deg: float,
        tilt_deg: float,
        speed: int,
        duration_ms: int,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        goal = self._move_head_pose_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.home = False
        goal.pan_deg = pan_deg
        goal.tilt_deg = tilt_deg
        goal.speed = speed
        goal.duration_ms = duration_ms
        return self._send_action_goal(
            self._move_head_pose_type,
            f"/stackchan/{meta.device_id}/cmd/motion/pose",
            goal,
            wait=wait,
            timeout=timeout,
        )

    def home_head_pose(
        self,
        meta: CommandMeta,
        speed: int,
        duration_ms: int,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        goal = self._move_head_pose_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.home = True
        goal.pan_deg = 0.0
        goal.tilt_deg = 0.0
        goal.speed = speed
        goal.duration_ms = duration_ms
        return self._send_action_goal(
            self._move_head_pose_type,
            f"/stackchan/{meta.device_id}/cmd/motion/pose",
            goal,
            wait=wait,
            timeout=timeout,
        )

    def say(
        self,
        meta: CommandMeta,
        text: str,
        voice: str,
        face_hint: str,
        motion_hint: str,
        after_face: str,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        goal = self._say_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.text = text
        goal.voice = voice
        goal.face_hint = face_hint
        goal.motion_hint = motion_hint
        goal.after_face_hint = after_face
        return self._send_action_goal(
            self._say_type,
            f"/stackchan/{meta.device_id}/cmd/say",
            goal,
            wait=wait,
            timeout=timeout,
        )

    def play_audio(
        self, meta: CommandMeta, path: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        status = self.get_status(meta, timeout)
        if not _capability_available(status, "audio_playback"):
            return BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=ErrorDetail(
                    code="UNSUPPORTED_FEATURE",
                    message="audio playback requires firmware-confirmed device transport.",
                    recoverable=False,
                ),
            )
        pcm = _read_audio_playback_pcm(path)
        goal = self._play_audio_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.format = "pcm_s16le"
        goal.sample_rate = AUDIO_SAMPLE_RATE
        goal.channels = AUDIO_CHANNELS
        first_goal_bytes = _audio_playback_first_goal_bytes()
        first_chunk = pcm[:first_goal_bytes]
        goal.first_chunk_present = bool(first_chunk)
        goal.first_chunk_sequence = 0
        goal.first_chunk_pcm = first_chunk
        goal.face_hint = ""
        goal.motion_hint = ""
        self._publish_audio_playback_chunks(
            meta,
            pcm[first_goal_bytes:],
            timeout,
            start_sequence=1 if first_chunk else 0,
            total_bytes=len(pcm),
        )
        return self._send_action_goal(
            self._play_audio_type,
            f"/stackchan/{meta.device_id}/cmd/audio/play",
            goal,
            wait=wait,
            timeout=timeout,
            return_on_accept=True,
        )

    def capture_audio(
        self,
        meta: CommandMeta,
        seconds: float,
        output: str,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        status = self.get_status(meta, timeout)
        if not _capability_available(status, "audio_capture"):
            return BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=ErrorDetail(
                    code="UNSUPPORTED_FEATURE",
                    message="audio capture requires firmware-confirmed device transport.",
                    recoverable=False,
                ),
            )
        collector = _AudioCaptureCollector(meta.device_id, meta.command_id)
        subscription = self._node.create_subscription(
            self._audio_chunk_type,
            f"/stackchan/{meta.device_id}/device/audio/chunks",
            collector.handle_chunk,
            getattr(self, "_audio_capture_chunk_qos", 8),
        )
        goal = self._capture_audio_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.format = "pcm_s16le"
        goal.sample_rate = AUDIO_SAMPLE_RATE
        goal.channels = AUDIO_CHANNELS
        goal.duration_ms = max(1, int(seconds * 1000))
        try:
            response = self._send_action_goal(
                self._capture_audio_type,
                f"/stackchan/{meta.device_id}/cmd/audio/capture",
                goal,
                wait=wait,
                timeout=timeout,
            )
        finally:
            destroy_subscription = getattr(self._node, "destroy_subscription", None)
            if destroy_subscription is not None:
                destroy_subscription(subscription)
        if not response.ok:
            return response
        pcm = collector.pcm()
        if collector.error is not None:
            return BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=collector.error,
            )
        if not pcm:
            return BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=ErrorDetail(
                    code="AUDIO_CAPTURE_FAILED",
                    message="audio capture completed without PCM chunks",
                    recoverable=True,
                ),
            )
        _write_audio_capture_wav(output, pcm)
        return response

    def capture_camera(
        self, meta: CommandMeta, output: str, quality: int, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        status = self.get_status(meta, timeout)
        if not _capability_available(status, "camera_snapshot"):
            return BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=ErrorDetail(
                    code="UNSUPPORTED_FEATURE",
                    message="camera capture requires firmware-confirmed device transport.",
                    recoverable=False,
                ),
            )
        collector = _CameraFrameCollector(meta.device_id, meta.command_id)
        subscription = self._node.create_subscription(
            self._camera_chunk_type,
            f"/stackchan/{meta.device_id}/device/camera/chunks",
            collector.handle_chunk,
            getattr(self, "_camera_chunk_qos", 16),
        )
        self._wait_for_camera_frame_publisher(subscription, timeout)
        goal = self._capture_camera_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.format = CAMERA_JPEG_FORMAT
        goal.width = 320
        goal.height = 240
        goal.quality = quality
        try:
            response = self._send_action_goal(
                self._capture_camera_type,
                f"/stackchan/{meta.device_id}/cmd/camera/capture",
                goal,
                wait=wait,
                timeout=timeout,
            )
            if response.ok:
                self._spin_camera_collector_until_complete(collector, timeout)
        finally:
            destroy_subscription = getattr(self._node, "destroy_subscription", None)
            if destroy_subscription is not None:
                destroy_subscription(subscription)
        if not response.ok:
            return response
        jpeg = collector.jpeg()
        if collector.error is not None:
            return BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=collector.error,
            )
        _write_camera_capture_jpeg(output, jpeg)
        return response

    def list_events(
        self,
        meta: CommandMeta,
        limit: int,
        since_event_id: str | None,
        timeout: float,
    ) -> EventListResult:
        request = self._list_events_type.Request()
        _copy_meta(request.meta, meta)
        request.limit = limit
        request.since_event_id = since_event_id or ""
        client = self._service_client(self._list_events_type, meta.device_id, "events/list", timeout)
        response = self._call_service(client, request, timeout)
        return _event_list_from_ros(meta, response.result, response.events, response.cursor)

    def next_event(
        self,
        meta: CommandMeta,
        consumer_id: str,
        after_event_id: str | None,
        timeout: float,
    ) -> EventListResult:
        request = self._next_event_type.Request()
        _copy_meta(request.meta, meta)
        request.consumer_id = consumer_id
        request.after_event_id = after_event_id or ""
        request.timeout_ms = _timeout_ms(timeout)
        client = self._service_client(self._next_event_type, meta.device_id, "events/next", timeout)
        response = self._call_service(client, request, timeout)
        return _event_list_from_ros(meta, response.result, response.events, response.cursor)

    def clear_events(
        self, meta: CommandMeta, consumer_id: str, timeout: float
    ) -> EventListResult:
        request = self._clear_event_cursor_type.Request()
        _copy_meta(request.meta, meta)
        request.consumer_id = consumer_id
        client = self._service_client(self._clear_event_cursor_type, meta.device_id, "events/clear_cursor", timeout)
        response = self._call_service(client, request, timeout)
        return EventListResult(
            ok=bool(response.result.ok),
            result_state=_state_from_ros(int(response.result.state)),
            device_id=meta.device_id,
            events=[],
            cursor=response.cursor or None,
            meta=meta,
            error=_error_from_ros(response.result),
        )

    def get_transcript(
        self, meta: CommandMeta, utterance_id: str | None, timeout: float
    ) -> TranscriptResult:
        request = self._get_transcript_type.Request()
        _copy_meta(request.meta, meta)
        request.utterance_id = utterance_id or ""
        client = self._service_client(self._get_transcript_type, meta.device_id, "speech/transcript/get", timeout)
        response = self._call_service(client, request, timeout)
        return TranscriptResult(
            ok=bool(response.result.ok),
            result_state=_state_from_ros(int(response.result.state)),
            device_id=meta.device_id,
            utterance_id=response.utterance_id or utterance_id,
            transcript=response.transcript if response.transcript else None,
            confidence=float(response.confidence),
            expires_at=_stamp_to_iso(response.expires_at),
            meta=meta,
            error=_error_from_ros(response.result),
        )

    def get_power_status(self, meta: CommandMeta, timeout: float) -> PowerStatusResult:
        request = self._get_power_status_type.Request()
        _copy_meta(request.meta, meta)
        client = self._service_client(self._get_power_status_type, meta.device_id, "power/status", timeout)
        response = self._call_service(client, request, timeout)
        return _power_status_from_ros(meta, response.result, response.status, bool(response.stale))

    def get_head_pose(self, meta: CommandMeta, timeout: float) -> HeadPoseResult:
        request = self._get_head_pose_type.Request()
        _copy_meta(request.meta, meta)
        client = self._service_client(self._get_head_pose_type, meta.device_id, "motion/status", timeout)
        response = self._call_service(client, request, timeout)
        return _head_pose_from_ros(meta, response.result, response.pose, bool(response.stale))

    def _send_action_goal(
        self,
        action_type,
        action_name: str,
        goal,
        *,
        wait: bool,
        timeout: float,
        on_accepted=None,
        on_result=None,
        return_on_accept: bool = False,
    ) -> BridgeCommandResponse:
        action = self._action_client_type(self._node, action_type, action_name)
        if not action.wait_for_server(timeout_sec=timeout):
            raise BridgeBackendTimeout()

        future = action.send_goal_async(goal)
        self._spin_future(future, timeout)
        goal_handle = future.result()
        if goal_handle is None or not goal_handle.accepted:
            return BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=ErrorDetail(
                    code="UNKNOWN_COMMAND",
                    message="goal was rejected by bridge facade",
                    recoverable=False,
                ),
            )
        if on_accepted is not None:
            on_accepted()
        if return_on_accept and not wait and on_result is None:
            return BridgeCommandResponse(ok=True, result_state=ResultState.ACCEPTED)
        # The facade action result is the bridge's immediate shared Result,
        # not proof that the physical behavior has completed.
        result_future = goal_handle.get_result_async()
        self._spin_future(result_future, timeout)
        action_result = result_future.result().result
        response = _response_from_ros(action_result.result)
        if response.ok and on_result is not None:
            on_result(action_result)
        return _normalize_action_response(response, wait=wait)

    def _audio_chunk_publisher(self, device_id: str):
        publisher = self._audio_chunk_publishers.get(device_id)
        if publisher is None:
            publisher = self._node.create_publisher(
                self._audio_chunk_type,
                f"/stackchan/{device_id}/cmd/audio/chunks",
                getattr(self, "_audio_playback_chunk_qos", 8),
            )
            self._audio_chunk_publishers[device_id] = publisher
        return publisher

    def _publish_audio_playback_chunks(
        self,
        meta: CommandMeta,
        pcm: bytes,
        timeout: float,
        *,
        start_sequence: int = 0,
        total_bytes: int | None = None,
    ) -> None:
        if not pcm:
            return
        publisher = self._audio_chunk_publisher(meta.device_id)
        self._wait_for_audio_playback_subscriber(publisher, timeout)
        chunk_bytes = _audio_playback_chunk_bytes()
        offsets = list(range(0, len(pcm), chunk_bytes))
        total_chunks = start_sequence + len(offsets)
        total_payload_bytes = len(pcm) if total_bytes is None else int(total_bytes)
        for index, offset in enumerate(offsets):
            sequence = start_sequence + index
            message = self._audio_chunk_type()
            message.device_id = meta.device_id
            message.command_id = meta.command_id
            message.direction = AUDIO_PLAYBACK_DIRECTION
            message.sequence = sequence
            message.total_chunks = total_chunks
            message.total_bytes = total_payload_bytes
            message.format = AUDIO_PCM_S16LE_FORMAT
            message.sample_rate = AUDIO_SAMPLE_RATE
            message.channels = AUDIO_CHANNELS
            message.end_of_stream = index + 1 >= len(offsets)
            message.pcm = pcm[offset : offset + chunk_bytes]
            publisher.publish(message)
            self._pace_audio_playback_chunk()

    def _wait_for_audio_playback_subscriber(self, publisher, timeout: float) -> None:
        get_subscription_count = getattr(publisher, "get_subscription_count", None)
        if get_subscription_count is None:
            self._sleep_audio_playback(AUDIO_PLAYBACK_CHUNK_INTERVAL_SEC)
            return
        deadline = time.monotonic() + min(
            max(timeout, 0.0),
            AUDIO_PLAYBACK_DISCOVERY_WAIT_SEC,
        )
        while (
            get_subscription_count() < AUDIO_PLAYBACK_EXPECTED_SUBSCRIPTIONS
            and time.monotonic() < deadline
        ):
            self._sleep_audio_playback(AUDIO_PLAYBACK_CHUNK_INTERVAL_SEC)
            spin_once = getattr(self._rclpy, "spin_once", None)
            if spin_once is not None:
                spin_once(self._node, timeout_sec=0)

    def _pace_audio_playback_chunk(self) -> None:
        self._sleep_audio_playback(AUDIO_PLAYBACK_CHUNK_INTERVAL_SEC)
        spin_once = getattr(self._rclpy, "spin_once", None)
        if spin_once is not None:
            spin_once(self._node, timeout_sec=0)

    def _sleep_audio_playback(self, seconds: float) -> None:
        sleep = getattr(self, "_audio_playback_sleep", time.sleep)
        sleep(seconds)

    def _service_client(self, service_type, device_id: str, tail: str, timeout: float):
        client = self._node.create_client(
            service_type,
            f"/stackchan/{device_id}/cmd/{tail}",
        )
        if not client.wait_for_service(timeout_sec=timeout):
            raise BridgeBackendTimeout()
        return client

    def _call_service(self, client, request, timeout: float):
        future = client.call_async(request)
        self._spin_future(future, timeout)
        response = future.result()
        if response is None:
            raise BridgeBackendTimeout()
        return response

    def _spin_future(self, future, timeout: float) -> None:
        self._rclpy.spin_until_future_complete(self._node, future, timeout_sec=timeout)
        if not future.done():
            raise BridgeBackendTimeout()

    def _spin_camera_collector_until_complete(
        self,
        collector: _CameraFrameCollector,
        timeout: float,
    ) -> None:
        if collector.complete() or collector.error is not None:
            return
        spin_once = getattr(self._rclpy, "spin_once", None)
        if spin_once is None:
            return
        deadline = time.monotonic() + min(max(timeout, 0.1), 2.0)
        while (
            not collector.complete()
            and collector.error is None
            and time.monotonic() < deadline
        ):
            spin_once(self._node, timeout_sec=0.02)

    def _wait_for_camera_frame_publisher(self, subscription, timeout: float) -> None:
        get_publisher_count = getattr(subscription, "get_publisher_count", None)
        if get_publisher_count is None:
            return
        deadline = time.monotonic() + min(max(timeout, 0.0), 1.0)
        while get_publisher_count() < 1 and time.monotonic() < deadline:
            spin_once = getattr(self._rclpy, "spin_once", None)
            if spin_once is not None:
                spin_once(self._node, timeout_sec=0.02)

    def close(self) -> None:
        self._node.destroy_node()
        self._rclpy.shutdown()


def _copy_meta(target, meta: CommandMeta) -> None:
    target.device_id = meta.device_id
    target.command_id = meta.command_id
    target.source = meta.source
    _copy_created_at(target.created_at, meta.created_at)
    target.priority = _priority_value(meta.priority.value)


def _capability_available(status: DeviceStatus, name: str) -> bool:
    return any(
        capability.name == name and capability.state == "available"
        for capability in status.capabilities
    )


def _read_audio_playback_pcm(path: str) -> bytes:
    source = Path(path)
    if not source.exists() or not source.is_file():
        raise BridgeBackendError(
            "AUDIO_PAYLOAD_NOT_FOUND",
            "audio playback input file was not found",
            recoverable=False,
        )
    if source.suffix.lower() == ".wav":
        return _read_audio_playback_wav(source)
    if source.suffix.lower() == ".pcm":
        return _validate_audio_playback_pcm(source.read_bytes())
    raise BridgeBackendError(
        "UNSUPPORTED_FEATURE",
        "audio play only supports PCM S16LE 16 kHz mono .wav or .pcm input",
        recoverable=False,
    )


def _read_audio_playback_wav(path: Path) -> bytes:
    try:
        with wave.open(str(path), "rb") as wav:
            if (
                wav.getnchannels() != AUDIO_CHANNELS
                or wav.getsampwidth() != 2
                or wav.getframerate() != AUDIO_SAMPLE_RATE
                or wav.getcomptype() != "NONE"
            ):
                raise BridgeBackendError(
                    "UNSUPPORTED_FEATURE",
                    "audio play only supports PCM S16LE 16 kHz mono WAV input",
                    recoverable=False,
                )
            return _validate_audio_playback_pcm(wav.readframes(wav.getnframes()))
    except wave.Error as exc:
        raise BridgeBackendError(
            "INVALID_AUDIO_PAYLOAD",
            "audio playback input is not a readable WAV file",
            recoverable=False,
        ) from exc


def _write_audio_capture_wav(path: str, pcm: bytes) -> None:
    destination = Path(path)
    if destination.parent != Path(".") and not destination.parent.exists():
        raise BridgeBackendError(
            "AUDIO_CAPTURE_FAILED",
            "audio capture output directory does not exist",
            recoverable=False,
        )
    try:
        with wave.open(str(destination), "wb") as wav:
            wav.setnchannels(AUDIO_CHANNELS)
            wav.setsampwidth(2)
            wav.setframerate(AUDIO_SAMPLE_RATE)
            wav.writeframes(pcm)
    except OSError as exc:
        raise BridgeBackendError(
            "AUDIO_CAPTURE_FAILED",
            "audio capture output file could not be written",
            recoverable=False,
        ) from exc
    except wave.Error as exc:
        raise BridgeBackendError(
            "AUDIO_CAPTURE_FAILED",
            "audio capture output WAV could not be written",
            recoverable=False,
        ) from exc


def _write_camera_capture_jpeg(path: str, data: bytes) -> None:
    destination = Path(path)
    if destination.parent != Path(".") and not destination.parent.exists():
        raise BridgeBackendError(
            "CAMERA_CAPTURE_FAILED",
            "camera capture output directory does not exist",
            recoverable=False,
        )
    if not data:
        raise BridgeBackendError(
            "CAMERA_CAPTURE_FAILED",
            "camera capture image payload was empty",
            recoverable=True,
        )
    if len(data) > CAMERA_MAX_PAYLOAD_BYTES:
        raise BridgeBackendError(
            "CAMERA_CAPTURE_FAILED",
            "camera capture image payload exceeded 96 KiB",
            recoverable=True,
        )
    try:
        destination.write_bytes(data)
    except OSError as exc:
        raise BridgeBackendError(
            "CAMERA_CAPTURE_FAILED",
            "camera capture output file could not be written",
            recoverable=False,
        ) from exc


def _validate_audio_playback_pcm(pcm: bytes) -> bytes:
    if not pcm:
        raise BridgeBackendError(
            "INVALID_AUDIO_PAYLOAD",
            "audio playback input is empty",
            recoverable=False,
        )
    if len(pcm) % 2 != 0:
        raise BridgeBackendError(
            "INVALID_AUDIO_PAYLOAD",
            "audio playback PCM payload must contain complete 16-bit samples",
            recoverable=False,
        )
    return pcm


def _copy_created_at(target, created_at: str) -> None:
    value = created_at
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    parsed = datetime.fromisoformat(value).astimezone(UTC)
    target.sec = int(parsed.timestamp())
    target.nanosec = parsed.microsecond * 1000


def _timeout_ms(timeout: float) -> int:
    return max(0, int(timeout * 1000))


def _priority_value(priority: str) -> int:
    return {
        "LOW": 0,
        "NORMAL": 1,
        "HIGH": 2,
        "SAFETY": 3,
    }[priority]


def _response_from_ros(result) -> BridgeCommandResponse:
    state = _state_from_ros(int(result.state))
    error = _error_from_ros(result)
    return BridgeCommandResponse(
        ok=bool(result.ok),
        result_state=state,
        error=None if result.ok else error,
    )


def _normalize_action_response(
    response: BridgeCommandResponse, *, wait: bool
) -> BridgeCommandResponse:
    if wait or not response.ok:
        return response
    return BridgeCommandResponse(ok=True, result_state=ResultState.ACCEPTED)


def _event_list_from_ros(meta: CommandMeta, result, events, cursor: str) -> EventListResult:
    return EventListResult(
        ok=bool(result.ok),
        result_state=_state_from_ros(int(result.state)),
        device_id=meta.device_id,
        events=[_event_from_ros(event) for event in events],
        cursor=cursor or None,
        meta=meta,
        error=_error_from_ros(result),
    )


def _event_from_ros(event) -> Event:
    return Event(
        event_id=getattr(event, "event_id", ""),
        device_id=getattr(event, "device_id", ""),
        event_name=getattr(event, "event_name", ""),
        source=getattr(event, "source", ""),
        stamp=_stamp_to_iso(getattr(event, "stamp", None)),
        command_id=getattr(event, "command_id", "") or None,
        payload=_payload_from_json(getattr(event, "payload_json", "")),
    )


def _payload_from_json(payload_json: str) -> dict[str, object]:
    invalid_marker: dict[str, object] = {
        "truncated": True,
        "reason": "payload_json_invalid",
    }
    if not payload_json:
        return {}
    try:
        import json

        loaded = json.loads(payload_json)
    except ValueError:
        return invalid_marker
    if isinstance(loaded, dict):
        return dict(_redact_event_payload(loaded))
    return invalid_marker


def _redact_event_payload(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            normalized_key = str(key).strip().lower()
            if _is_sensitive_event_key(normalized_key):
                redacted[str(key)] = REDACTED
            else:
                redacted[str(key)] = _redact_event_payload(value)
        return redacted
    if isinstance(payload, bytes | bytearray):
        return REDACTED
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [_redact_event_payload(item) for item in payload]
    return payload


def _is_sensitive_event_key(normalized_key: str) -> bool:
    utterance_text_key = "utterance" in normalized_key and normalized_key != "utterance_id"
    return (
        normalized_key in SENSITIVE_EVENT_FIELDS
        or any(marker in normalized_key for marker in SENSITIVE_EVENT_MARKERS)
        or any(part in normalized_key for part in SENSITIVE_EVENT_KEY_PARTS)
        or utterance_text_key
    )


def _stamp_to_iso(stamp) -> str | None:
    if stamp is None:
        return None
    sec = int(getattr(stamp, "sec", 0))
    nanosec = int(getattr(stamp, "nanosec", 0))
    if sec == 0 and nanosec == 0:
        return None
    value = datetime.fromtimestamp(sec + nanosec / 1_000_000_000, UTC)
    return value.replace(microsecond=nanosec // 1000).isoformat().replace("+00:00", "Z")


def _capability_from_ros(capability) -> CapabilityStatus:
    return CapabilityStatus(
        name=getattr(capability, "name", ""),
        state=getattr(capability, "state", ""),
        detail_code=getattr(capability, "detail_code", ""),
        active=bool(getattr(capability, "active", False)),
        queued=int(getattr(capability, "queued", 0)),
        last_update=_stamp_to_iso(getattr(capability, "last_update", None)),
    )


def _unsupported_events(device_id: str, feature: str) -> EventListResult:
    return EventListResult(
        ok=False,
        result_state=ResultState.REJECTED,
        device_id=device_id,
        events=[],
        error=ErrorDetail(
            code="UNSUPPORTED_FEATURE",
            message=f"bridge backend does not implement {feature} yet",
            recoverable=False,
        ),
    )


def _unsupported_transcript(device_id: str, utterance_id: str | None = None) -> TranscriptResult:
    return TranscriptResult(
        ok=False,
        result_state=ResultState.REJECTED,
        device_id=device_id,
        utterance_id=utterance_id,
        transcript=None,
        confidence=None,
        expires_at=None,
        error=ErrorDetail(
            code="UNSUPPORTED_FEATURE",
            message="bridge backend does not implement speech transcript service yet",
            recoverable=False,
        ),
    )


def _state_from_ros(state: int) -> ResultState:
    return {
        1: ResultState.ACCEPTED,
        2: ResultState.COMPLETED,
        3: ResultState.REJECTED,
        4: ResultState.TIMEOUT,
    }.get(state, ResultState.REJECTED)


def _error_from_ros(result) -> ErrorDetail | None:
    if getattr(result, "ok", False):
        return None
    error_code = getattr(result, "error_code", "")
    message = getattr(result, "message", "")
    recoverable = bool(getattr(result, "recoverable", False))
    if not error_code and not message:
        return None
    return ErrorDetail(
        code=error_code,
        message=message,
        recoverable=recoverable,
    )


def _rejected(
    request: CommandRequest, error: ErrorDetail
) -> CommandResult | EventListResult | TranscriptResult | PowerStatusResult | HeadPoseResult:
    return _error_result(request, error)


def _timeout_result(
    request: CommandRequest,
) -> CommandResult | EventListResult | TranscriptResult | PowerStatusResult | HeadPoseResult:
    return _error_result(
        request,
        ErrorDetail(
            code="TIMEOUT",
            message="bridge facade call timed out",
            recoverable=True,
        ),
        result_state=ResultState.TIMEOUT,
    )


def _error_result(
    request: CommandRequest,
    error: ErrorDetail,
    *,
    result_state: ResultState = ResultState.REJECTED,
) -> CommandResult | EventListResult | TranscriptResult | PowerStatusResult | HeadPoseResult:
    if request.command_type in {
        CommandType.EVENTS_LIST,
        CommandType.EVENTS_NEXT,
        CommandType.EVENTS_CLEAR,
    }:
        return EventListResult(
            ok=False,
            result_state=result_state,
            device_id=request.meta.device_id,
            events=[],
            meta=request.meta,
            error=error,
        )
    if request.command_type is CommandType.SPEECH_TRANSCRIPT:
        return TranscriptResult(
            ok=False,
            result_state=result_state,
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
            result_state=result_state,
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
            result_state=result_state,
            device_id=request.meta.device_id,
            pan_deg=None,
            tilt_deg=None,
            moving=False,
            meta=request.meta,
            error=error,
        )
    return CommandResult(
        ok=False,
        result_state=result_state,
        meta=request.meta,
        command=_command_payload(request),
        error=error,
    )


def _append_demo_step(
    steps: list[dict[str, object]],
    name: str,
    response: BridgeCommandResponse,
    *,
    degraded_codes: set[str] | None = None,
    skipped_codes: set[str] | None = None,
) -> ErrorDetail | None:
    degraded_codes = degraded_codes or set()
    skipped_codes = skipped_codes or set()
    error = response.error
    if response.ok:
        steps.append({"name": name, "state": "completed"})
        return None
    error_code = "UNKNOWN_COMMAND" if error is None else error.code
    if error_code in skipped_codes:
        steps.append({"name": name, "state": "skipped", "error_code": error_code})
        return None
    if error_code in degraded_codes:
        steps.append({"name": name, "state": "degraded", "error_code": error_code})
        return None
    steps.append({"name": name, "state": "failed", "error_code": error_code})
    return error or ErrorDetail(
        code=error_code,
        message=f"demo step {name} failed",
        recoverable=True,
    )


def _doctor_check_from_result(
    name: str, result: EventListResult | PowerStatusResult | HeadPoseResult
) -> DoctorCheck:
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


def _demo_failed_result(
    request: CommandRequest, command: dict[str, object], error: ErrorDetail
) -> CommandResult:
    return CommandResult(
        ok=False,
        result_state=ResultState.REJECTED,
        meta=request.meta,
        command=command,
        error=error,
    )


def _command_payload(request: CommandRequest) -> dict[str, object]:
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
            "steps": [],
        }
    if request.command_type is CommandType.SAY:
        payload: dict[str, Any] = {
            "type": "say",
            "text_length": len(str(request.args["text"])),
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
    if request.command_type is CommandType.AUDIO_PLAY:
        return {
            "type": "audio.play",
            "path": request.args["path"],
            "format": "pcm_s16le",
            "sample_rate": 16000,
            "channels": 1,
            "chunk_ms": 20,
            "max_chunk_ms": 40,
        }
    if request.command_type is CommandType.AUDIO_CAPTURE:
        payload = {
            "type": "audio.capture",
            "seconds": request.args["seconds"],
            "output": request.args["output"],
            "format": "pcm_s16le",
            "sample_rate": 16000,
            "channels": 1,
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
        return {"type": "nfc.wait"}
    if request.command_type is CommandType.IMU_STREAM:
        return {"type": "imu.stream", "hz": request.args["hz"]}
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
            "store": "firmware_nvs",
            "write": False,
        }
    if request.command_type is CommandType.MAINTENANCE_CALIBRATION_CAPTURE_NEUTRAL:
        return {
            "type": "maintenance.calibration.capture-neutral",
            "confirmed": bool(request.args.get("confirmed")),
            "store": "firmware_nvs",
            "write": True,
        }
    if request.command_type is CommandType.MAINTENANCE_CALIBRATION_RESET:
        return {
            "type": "maintenance.calibration.reset",
            "confirmed": bool(request.args.get("confirmed")),
            "reset_to": "invalid",
            "store": "firmware_nvs",
            "write": True,
        }
    return {"type": request.command_type.value}


def _power_status_from_ros(meta: CommandMeta, result, status, stale: bool) -> PowerStatusResult:
    return PowerStatusResult(
        ok=bool(result.ok),
        result_state=_state_from_ros(int(result.state)),
        device_id=getattr(status, "device_id", "") or meta.device_id,
        voltage_v=_finite_float_or_none(getattr(status, "voltage_v", math.nan)),
        current_ma=_finite_float_or_none(getattr(status, "current_ma", math.nan)),
        power_mw=_finite_float_or_none(getattr(status, "power_mw", math.nan)),
        percentage=_finite_float_or_none(getattr(status, "percentage", math.nan)),
        power_source=_power_source_name(int(getattr(status, "power_source", 0))),
        charging=bool(getattr(status, "charging", False)),
        powered=bool(getattr(status, "powered", False)),
        low_battery=bool(getattr(status, "low_battery", False)),
        brownout_risk=bool(getattr(status, "brownout_risk", False)),
        fault_code=getattr(status, "fault_code", "") or None,
        stale=stale,
        stamp=_stamp_to_iso(getattr(status, "stamp", None)),
        meta=meta,
        error=_error_from_ros(result),
    )


def _head_pose_from_ros(meta: CommandMeta, result, pose, stale: bool) -> HeadPoseResult:
    return HeadPoseResult(
        ok=bool(result.ok),
        result_state=_state_from_ros(int(result.state)),
        device_id=getattr(pose, "device_id", "") or meta.device_id,
        pan_deg=_finite_float_or_none(getattr(pose, "pan_deg", math.nan)),
        tilt_deg=_finite_float_or_none(getattr(pose, "tilt_deg", math.nan)),
        moving=bool(getattr(pose, "moving", False)),
        frame=getattr(pose, "frame", "") or "home",
        stale=stale,
        stamp=_stamp_to_iso(getattr(pose, "stamp", None)),
        meta=meta,
        error=_error_from_ros(result),
    )


def _finite_float_or_none(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _power_source_name(value: int) -> str:
    return {
        1: "battery",
        2: "usb",
        3: "external",
    }.get(value, "unknown")


def _optional_string_arg(request: CommandRequest, key: str) -> str | None:
    value = request.args.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
