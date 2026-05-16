from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from stackchanctl.backends.mock import validate_common_request
from stackchanctl.contract import (
    CommandMeta,
    CommandRequest,
    CommandResult,
    CommandType,
    DeviceStatus,
    ErrorDetail,
    ResultState,
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
    def get_status(self, device_id: str, timeout: float) -> DeviceStatus:
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


class BridgeBackend:
    """Backend that talks to the stackchan_bridge facade resources."""

    def __init__(self, client: BridgeClient | None = None) -> None:
        self._client = client

    def execute(self, request: CommandRequest) -> CommandResult | DeviceStatus:
        validation_error = validate_common_request(request)
        if validation_error is not None:
            return _rejected(request, validation_error)

        try:
            client = self._get_client()
            if request.command_type is CommandType.OBSERVE:
                return client.get_status(request.meta.device_id, request.timeout)
            response = self._execute_command(request, client)
        except BridgeBackendTimeout:
            return CommandResult(
                ok=False,
                result_state=ResultState.TIMEOUT,
                meta=request.meta,
                command=_command_payload(request),
                error=ErrorDetail(
                    code="TIMEOUT",
                    message="bridge facade call timed out",
                    recoverable=True,
                ),
            )
        except BridgeBackendError as exc:
            return CommandResult(
                ok=False,
                result_state=ResultState.REJECTED,
                meta=request.meta,
                command=_command_payload(request),
                error=ErrorDetail(
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
                PlayAudio,
                RunMotion,
                Say,
            )
            from stackchan_msgs.srv import GetStatus, SetFace, SetLed
        except ImportError as exc:
            raise BridgeBackendError(
                "BRIDGE_BACKEND_UNAVAILABLE",
                "rclpy or stackchan_msgs is not available; source ROS 2 or use --backend mock",
            ) from exc

        self._rclpy = rclpy
        self._action_client_type = ActionClient
        self._get_status_type = GetStatus
        self._set_face_type = SetFace
        self._set_led_type = SetLed
        self._run_motion_type = RunMotion
        self._say_type = Say
        self._play_audio_type = PlayAudio
        self._capture_audio_type = CaptureAudio
        self._capture_camera_type = CaptureCamera
        self._rclpy.init(args=None)
        self._node = self._rclpy.create_node("stackchanctl_bridge_client")

    def get_status(self, device_id: str, timeout: float) -> DeviceStatus:
        client = self._service_client(self._get_status_type, device_id, "get_status", timeout)
        response = self._call_service(client, self._get_status_type.Request(), timeout)
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
        if not wait:
            return BridgeCommandResponse(ok=True, result_state=ResultState.ACCEPTED)

        result_future = goal_handle.get_result_async()
        self._spin_future(result_future, timeout)
        return _response_from_ros(result_future.result().result.result)

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
        del path
        goal = self._play_audio_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.format = "pcm_s16le"
        goal.sample_rate = 16000
        goal.channels = 1
        goal.face_hint = ""
        goal.motion_hint = ""
        return self._send_action_goal(
            self._play_audio_type,
            f"/stackchan/{meta.device_id}/cmd/audio/play",
            goal,
            wait=wait,
            timeout=timeout,
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
        del output
        goal = self._capture_audio_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.format = "pcm_s16le"
        goal.sample_rate = 16000
        goal.channels = 1
        goal.duration_ms = int(seconds * 1000)
        return self._send_action_goal(
            self._capture_audio_type,
            f"/stackchan/{meta.device_id}/cmd/audio/capture",
            goal,
            wait=wait,
            timeout=timeout,
        )

    def capture_camera(
        self, meta: CommandMeta, output: str, quality: int, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        del output
        goal = self._capture_camera_type.Goal()
        _copy_meta(goal.meta, meta)
        goal.format = "jpeg"
        goal.width = 320
        goal.height = 240
        goal.quality = quality
        return self._send_action_goal(
            self._capture_camera_type,
            f"/stackchan/{meta.device_id}/cmd/camera/capture",
            goal,
            wait=wait,
            timeout=timeout,
        )

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
        if not wait:
            return BridgeCommandResponse(ok=True, result_state=ResultState.ACCEPTED)

        result_future = goal_handle.get_result_async()
        self._spin_future(result_future, timeout)
        return _response_from_ros(result_future.result().result.result)

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


def _rejected(request: CommandRequest, error: ErrorDetail) -> CommandResult:
    return CommandResult(
        ok=False,
        result_state=ResultState.REJECTED,
        meta=request.meta,
        command=_command_payload(request),
        error=error,
    )


def _command_payload(request: CommandRequest) -> dict[str, object]:
    if request.command_type is CommandType.FACE:
        return {"type": "face", "name": request.args["name"]}
    if request.command_type is CommandType.MOTION:
        return {"type": "motion", "name": request.args["name"]}
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
    return {"type": request.command_type.value}
