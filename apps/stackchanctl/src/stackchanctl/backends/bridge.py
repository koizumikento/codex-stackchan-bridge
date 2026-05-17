from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC, datetime
import math
from typing import Any, Protocol

from stackchanctl.backends.mock import validate_common_request
from stackchanctl.contract import (
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
            return _unsupported_media("audio playback data transport")
        if request.command_type is CommandType.AUDIO_CAPTURE:
            return _unsupported_media("audio capture data transport")
        if request.command_type is CommandType.CAMERA_CAPTURE:
            return _unsupported_media("camera capture result transport")
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
            from stackchan_msgs.action import (
                CaptureAudio,
                CaptureCamera,
                MoveHeadPose,
                PlayAudio,
                RunMotion,
                Say,
            )
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
        self._rclpy.init(args=None)
        self._node = self._rclpy.create_node("stackchanctl_bridge_client")

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
        del meta, path, wait, timeout
        return _unsupported_media("audio playback data transport")

    def capture_audio(
        self,
        meta: CommandMeta,
        seconds: float,
        output: str,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        del meta, seconds, output, wait, timeout
        return _unsupported_media("audio capture data transport")

    def capture_camera(
        self, meta: CommandMeta, output: str, quality: int, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        del meta, output, quality, wait, timeout
        return _unsupported_media("camera capture result transport")

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
        self, action_type, action_name: str, goal, *, wait: bool, timeout: float
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
        # The facade action result is the bridge's immediate shared Result,
        # not proof that the physical behavior has completed.
        result_future = goal_handle.get_result_async()
        self._spin_future(result_future, timeout)
        response = _response_from_ros(result_future.result().result.result)
        return _normalize_action_response(response, wait=wait)

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


def _unsupported_media(feature: str) -> BridgeCommandResponse:
    return BridgeCommandResponse(
        ok=False,
        result_state=ResultState.REJECTED,
        error=ErrorDetail(
            code="UNSUPPORTED_FEATURE",
            message=f"bridge backend does not implement {feature} yet",
            recoverable=False,
        ),
    )


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
            if normalized_key in SENSITIVE_EVENT_FIELDS or any(
                marker in normalized_key for marker in SENSITIVE_EVENT_MARKERS
            ):
                redacted[str(key)] = REDACTED
            else:
                redacted[str(key)] = _redact_event_payload(value)
        return redacted
    if isinstance(payload, bytes | bytearray):
        return REDACTED
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [_redact_event_payload(item) for item in payload]
    return payload


def _stamp_to_iso(stamp) -> str | None:
    if stamp is None:
        return None
    sec = int(getattr(stamp, "sec", 0))
    nanosec = int(getattr(stamp, "nanosec", 0))
    if sec == 0 and nanosec == 0:
        return None
    value = datetime.fromtimestamp(sec + nanosec / 1_000_000_000, UTC)
    return value.replace(microsecond=nanosec // 1000).isoformat().replace("+00:00", "Z")


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
        return {"type": "audio.play", "path": request.args["path"]}
    if request.command_type is CommandType.AUDIO_CAPTURE:
        return {
            "type": "audio.capture",
            "seconds": request.args["seconds"],
            "output": request.args["output"],
        }
    if request.command_type is CommandType.CAMERA_CAPTURE:
        return {
            "type": "camera.capture",
            "output": request.args["output"],
            "quality": request.args["quality"],
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
