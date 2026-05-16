"""Lazy ROS 2 node adapter for the StackChan bridge facade."""

from __future__ import annotations

from stackchan_bridge.facade import StackChanBridgeFacade
from stackchan_bridge.models import CommandMeta
from stackchan_bridge.registry import DeviceRecord, DeviceRegistry


def _time_to_string(stamp: object) -> str:
    sec = getattr(stamp, "sec", 0)
    nanosec = getattr(stamp, "nanosec", 0)
    return f"{sec}.{nanosec:09d}"


def _meta_from_ros(meta: object, fallback_device_id: str = "default") -> CommandMeta:
    return CommandMeta(
        device_id=getattr(meta, "device_id", "") or fallback_device_id,
        command_id=getattr(meta, "command_id", ""),
        source=getattr(meta, "source", ""),
        created_at=_time_to_string(getattr(meta, "created_at", None)),
        priority=getattr(meta, "priority", 1),
    )


def _normalize_device_ids(value: object) -> list[str]:
    raw_device_ids = [value] if isinstance(value, str) else list(value or [])
    device_ids: list[str] = []
    for raw_device_id in raw_device_ids:
        device_id = str(raw_device_id).strip()
        if device_id and device_id not in device_ids:
            device_ids.append(device_id)
    return device_ids or ["default"]


def _configured_device_records(
    device_ids: list[str], *, connected: bool
) -> list[DeviceRecord]:
    return [DeviceRecord(device_id, connected=connected) for device_id in device_ids]


def _copy_result(result: object, source: object) -> None:
    result.ok = source.ok
    result.state = source.state
    result.error_code = source.error_code
    result.message = source.message
    result.recoverable = source.recoverable


def _copy_status(response: object, status: object) -> None:
    response.device_id = status.device_id
    response.connected = status.connected
    response.state = status.state
    response.face = status.face
    response.motion = status.motion
    response.last_command_id = status.last_command_id
    _copy_result(response.last_error, status.last_error)


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
        from rclpy.action import ActionServer
        from rclpy.node import Node
        from stackchan_msgs.action import CaptureAudio, CaptureCamera, PlayAudio, RunMotion, Say
        from stackchan_msgs.srv import GetStatus, SetFace, SetLed
    except ImportError as exc:  # pragma: no cover - exercised only without ROS.
        raise RuntimeError(
            "stackchan_bridge_node requires ROS 2 Python packages."
        ) from exc

    class StackChanBridgeNode(Node):
        def __init__(self) -> None:
            super().__init__("stackchan_bridge")
            self.declare_parameter("device_ids", ["default"])
            configured_device_ids = _normalize_device_ids(
                self.get_parameter("device_ids").value
            )
            self.declare_parameter("device_connected", False)
            device_connected = bool(self.get_parameter("device_connected").value)
            registry = DeviceRegistry(
                _configured_device_records(
                    configured_device_ids,
                    connected=device_connected,
                )
            )
            self.facade = StackChanBridgeFacade(
                registry=registry,
                logger=self.get_logger(),
            )
            self._action_servers = []
            for device_id in configured_device_ids:
                self._create_device_resources(device_id)

        def _create_device_resources(self, device_id: str) -> None:
            prefix = f"/stackchan/{device_id}/cmd"
            self.create_service(
                GetStatus,
                f"{prefix}/get_status",
                lambda request, response, device_id=device_id: self._handle_get_status(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                SetFace,
                f"{prefix}/face/set",
                lambda request, response, device_id=device_id: self._handle_set_face(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                SetLed,
                f"{prefix}/led/set",
                lambda request, response, device_id=device_id: self._handle_set_led(
                    device_id,
                    request,
                    response,
                ),
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    RunMotion,
                    f"{prefix}/motion/run",
                    lambda goal_handle, device_id=device_id: self._handle_run_motion(
                        device_id,
                        goal_handle,
                    ),
                )
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    Say,
                    f"{prefix}/say",
                    lambda goal_handle, device_id=device_id: self._handle_say(
                        device_id,
                        goal_handle,
                    ),
                )
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    PlayAudio,
                    f"{prefix}/audio/play",
                    lambda goal_handle, device_id=device_id: self._handle_play_audio(
                        device_id,
                        goal_handle,
                    ),
                )
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    CaptureAudio,
                    f"{prefix}/audio/capture",
                    lambda goal_handle, device_id=device_id: self._handle_capture_audio(
                        device_id,
                        goal_handle,
                    ),
                )
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    CaptureCamera,
                    f"{prefix}/camera/capture",
                    lambda goal_handle, device_id=device_id: self._handle_capture_camera(
                        device_id,
                        goal_handle,
                    ),
                )
            )

        def _handle_get_status(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            status_response = self.facade.get_status(device_id)
            _copy_status(response, status_response.status)
            return response

        def _handle_set_face(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            command_response = self.facade.set_face(
                _meta_from_ros(request.meta, device_id),
                request.name,
                request.duration_ms,
            )
            _copy_result(response.result, command_response.result)
            return response

        def _handle_set_led(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            command_response = self.facade.set_led(
                _meta_from_ros(request.meta, device_id),
                request.pattern,
                request.color,
                request.duration_ms,
            )
            _copy_result(response.result, command_response.result)
            return response

        def _handle_run_motion(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            command_response = self.facade.run_motion(
                _meta_from_ros(request.meta, device_id),
                request.name,
                request.intensity,
                request.duration_ms,
            )
            result = RunMotion.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _handle_say(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            command_response = self.facade.say(
                _meta_from_ros(request.meta, device_id),
                request.text,
            )
            result = Say.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _handle_play_audio(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            command_response = self.facade.play_audio(
                _meta_from_ros(request.meta, device_id)
            )
            result = PlayAudio.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _handle_capture_audio(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            command_response = self.facade.capture_audio(
                _meta_from_ros(request.meta, device_id)
            )
            result = CaptureAudio.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _handle_capture_camera(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            command_response = self.facade.capture_camera(
                _meta_from_ros(request.meta, device_id)
            )
            result = CaptureCamera.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

    rclpy.init(args=args)
    node = StackChanBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
