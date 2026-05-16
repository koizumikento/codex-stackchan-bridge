"""Lazy ROS 2 node adapter for the StackChan bridge facade."""

from __future__ import annotations

from stackchan_bridge.facade import StackChanBridgeFacade
from stackchan_bridge.models import CommandMeta


def _time_to_string(stamp: object) -> str:
    sec = getattr(stamp, "sec", 0)
    nanosec = getattr(stamp, "nanosec", 0)
    return f"{sec}.{nanosec:09d}"


def _meta_from_ros(meta: object) -> CommandMeta:
    return CommandMeta(
        device_id=getattr(meta, "device_id", "default"),
        command_id=getattr(meta, "command_id", ""),
        source=getattr(meta, "source", ""),
        created_at=_time_to_string(getattr(meta, "created_at", None)),
        priority=getattr(meta, "priority", 1),
    )


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
            self.facade = StackChanBridgeFacade(logger=self.get_logger())
            self.create_service(
                GetStatus,
                "/stackchan/default/cmd/get_status",
                self._handle_get_status,
            )
            self.create_service(
                SetFace,
                "/stackchan/default/cmd/face/set",
                self._handle_set_face,
            )
            self.create_service(
                SetLed,
                "/stackchan/default/cmd/led/set",
                self._handle_set_led,
            )
            self._motion_action = ActionServer(
                self,
                RunMotion,
                "/stackchan/default/cmd/motion/run",
                self._handle_run_motion,
            )
            self._say_action = ActionServer(
                self,
                Say,
                "/stackchan/default/cmd/say",
                self._handle_say,
            )
            self._play_audio_action = ActionServer(
                self,
                PlayAudio,
                "/stackchan/default/cmd/audio/play",
                self._handle_play_audio,
            )
            self._capture_audio_action = ActionServer(
                self,
                CaptureAudio,
                "/stackchan/default/cmd/audio/capture",
                self._handle_capture_audio,
            )
            self._capture_camera_action = ActionServer(
                self,
                CaptureCamera,
                "/stackchan/default/cmd/camera/capture",
                self._handle_capture_camera,
            )

        def _handle_get_status(self, request: object, response: object) -> object:
            status_response = self.facade.get_status("default")
            _copy_status(response, status_response.status)
            return response

        def _handle_set_face(self, request: object, response: object) -> object:
            command_response = self.facade.set_face(
                _meta_from_ros(request.meta),
                request.name,
                request.duration_ms,
            )
            _copy_result(response.result, command_response.result)
            return response

        def _handle_set_led(self, request: object, response: object) -> object:
            command_response = self.facade.set_led(
                _meta_from_ros(request.meta),
                request.pattern,
                request.color,
                request.duration_ms,
            )
            _copy_result(response.result, command_response.result)
            return response

        def _handle_run_motion(self, goal_handle: object) -> object:
            request = goal_handle.request
            command_response = self.facade.run_motion(
                _meta_from_ros(request.meta),
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

        def _handle_say(self, goal_handle: object) -> object:
            request = goal_handle.request
            command_response = self.facade.say(_meta_from_ros(request.meta), request.text)
            result = Say.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _handle_play_audio(self, goal_handle: object) -> object:
            request = goal_handle.request
            command_response = self.facade.play_audio(_meta_from_ros(request.meta))
            result = PlayAudio.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _handle_capture_audio(self, goal_handle: object) -> object:
            request = goal_handle.request
            command_response = self.facade.capture_audio(_meta_from_ros(request.meta))
            result = CaptureAudio.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _handle_capture_camera(self, goal_handle: object) -> object:
            request = goal_handle.request
            command_response = self.facade.capture_camera(_meta_from_ros(request.meta))
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
