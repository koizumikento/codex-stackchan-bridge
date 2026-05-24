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

from stackchanctl.backends.mock import validate_common_request
from stackchanctl.contract import (
    CapabilityStatus,
    CommandMeta,
    CommandRequest,
    CommandResult,
    CommandType,
    DeviceStatus,
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
CAMERA_MAX_PAYLOAD_BYTES = 96 * 1024


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
        self, meta: CommandMeta, text: str, *, wait: bool, timeout: float
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
    ) -> CommandResult | DeviceStatus | EventListResult | TranscriptResult | PowerStatusResult | HeadPoseResult:
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
            if request.command_type in {
                CommandType.EVENTS_LIST,
                CommandType.EVENTS_NEXT,
                CommandType.EVENTS_CLEAR,
                CommandType.SPEECH_TRANSCRIPT,
                CommandType.POWER_STATUS,
                CommandType.MOTION_STATUS,
            }:
                return self._execute_observation(request, client)
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
            return client.capture_audio(
                request.meta,
                float(request.args["seconds"]),
                str(request.args["output"]),
                wait=request.wait,
                timeout=request.timeout,
            )
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
            from stackchan_msgs.msg import AudioChunk
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
        self._rclpy.init(args=None)
        self._node = self._rclpy.create_node("stackchanctl_bridge_client")
        self._audio_chunk_publishers = {}
        self._audio_chunk_qos = QoSProfile(depth=8)
        self._audio_chunk_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self._audio_chunk_qos.durability = DurabilityPolicy.VOLATILE

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
        self, meta: CommandMeta, text: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        goal = self._say_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.text = text
        goal.voice = ""
        goal.face_hint = ""
        goal.motion_hint = ""
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
        return self._send_action_goal(
            self._play_audio_type,
            f"/stackchan/{meta.device_id}/cmd/audio/play",
            goal,
            wait=wait,
            timeout=timeout,
            on_accepted=lambda: self._publish_audio_playback_chunks(
                meta,
                pcm[first_goal_bytes:],
                timeout,
                start_sequence=1 if first_chunk else 0,
            ),
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
            getattr(self, "_audio_chunk_qos", 8),
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
        camera_result = {}
        goal = self._capture_camera_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.format = CAMERA_JPEG_FORMAT
        goal.width = 320
        goal.height = 240
        goal.quality = quality
        response = self._send_action_goal(
            self._capture_camera_type,
            f"/stackchan/{meta.device_id}/cmd/camera/capture",
            goal,
            wait=wait,
            timeout=timeout,
            on_result=lambda result: camera_result.setdefault("image", result.image),
        )
        if not response.ok:
            return response
        image = camera_result.get("image")
        if image is None:
            return BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=ErrorDetail(
                    code="CAMERA_CAPTURE_FAILED",
                    message="camera capture completed without an image payload",
                    recoverable=True,
                ),
            )
        _write_camera_capture_jpeg(output, image)
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
                getattr(self, "_audio_chunk_qos", 8),
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
    ) -> None:
        if not pcm:
            return
        publisher = self._audio_chunk_publisher(meta.device_id)
        self._wait_for_audio_playback_subscriber(publisher, timeout)
        chunk_bytes = _audio_playback_chunk_bytes()
        for sequence, offset in enumerate(
            range(0, len(pcm), chunk_bytes),
            start=start_sequence,
        ):
            message = self._audio_chunk_type()
            message.device_id = meta.device_id
            message.command_id = meta.command_id
            message.direction = AUDIO_PLAYBACK_DIRECTION
            message.sequence = sequence
            message.format = AUDIO_PCM_S16LE_FORMAT
            message.sample_rate = AUDIO_SAMPLE_RATE
            message.channels = AUDIO_CHANNELS
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


def _write_camera_capture_jpeg(path: str, image) -> None:
    destination = Path(path)
    if destination.parent != Path(".") and not destination.parent.exists():
        raise BridgeBackendError(
            "CAMERA_CAPTURE_FAILED",
            "camera capture output directory does not exist",
            recoverable=False,
        )
    image_format = getattr(image, "format", "")
    data = bytes(getattr(image, "data", b""))
    if image_format != CAMERA_JPEG_FORMAT:
        raise BridgeBackendError(
            "UNSUPPORTED_FEATURE",
            "camera capture only supports JPEG payloads",
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
    if request.command_type is CommandType.SAY:
        return {"type": "say", "text_length": len(str(request.args["text"]))}
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
        return {
            "type": "audio.capture",
            "seconds": request.args["seconds"],
            "output": request.args["output"],
            "format": "pcm_s16le",
            "sample_rate": 16000,
            "channels": 1,
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
