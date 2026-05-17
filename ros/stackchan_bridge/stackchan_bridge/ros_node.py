"""Lazy ROS 2 node adapter for the StackChan bridge facade."""

from __future__ import annotations

import json

from stackchan_bridge.event_aggregator import EventAggregator
from stackchan_bridge.event_buffer import EventBuffer, EventRecord
from stackchan_bridge.facade import StackChanBridgeFacade
from stackchan_bridge.models import CommandMeta, Result
from stackchan_bridge.registry import DeviceRecord, DeviceRegistry
from stackchan_bridge.speech_session import SpeechTranscript, SpeechTranscriptStore


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


def _stamp_to_seconds(stamp: object) -> float | None:
    sec = int(getattr(stamp, "sec", 0))
    nanosec = int(getattr(stamp, "nanosec", 0))
    if sec == 0 and nanosec == 0:
        return None
    return sec + nanosec / 1_000_000_000


def _copy_seconds_to_stamp(target: object, stamp: float) -> None:
    sec = int(stamp)
    target.sec = sec
    target.nanosec = int((stamp - sec) * 1_000_000_000)


def _copy_event_record(target: object, record: EventRecord) -> None:
    target.event_id = record.event_id
    target.device_id = record.device_id
    target.event_name = record.event_name
    target.source = record.source
    _copy_seconds_to_stamp(target.stamp, record.stamp)
    target.command_id = record.command_id
    target.payload_json = json.dumps(
        dict(record.payload),
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _records_after_event_id(
    records: tuple[EventRecord, ...], event_id: str
) -> tuple[EventRecord, ...]:
    if not event_id:
        return records
    for index, record in enumerate(records):
        if record.event_id == event_id:
            return records[index + 1 :]
    return records


def _cursor_for(records: tuple[EventRecord, ...]) -> str:
    return records[-1].event_id if records else ""


def _copy_records(response: object, event_type: object, records: tuple[EventRecord, ...]) -> None:
    events = []
    for record in records:
        event = event_type()
        _copy_event_record(event, record)
        events.append(event)
    response.events = events


def _copy_transcript(response: object, transcript: SpeechTranscript) -> None:
    response.utterance_id = transcript.utterance_id
    response.transcript = transcript.text
    response.confidence = 1.0
    _copy_seconds_to_stamp(response.expires_at, transcript.expires_at)


def _transcript_from_event_payload(payload: object) -> tuple[str, str] | None:
    if not isinstance(payload, str) or not payload:
        return None
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    utterance_id = str(decoded.get("utterance_id") or "")
    transcript = str(decoded.get("transcript") or decoded.get("text") or "")
    if not utterance_id or not transcript:
        return None
    return utterance_id, transcript


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
        from rclpy.action import ActionServer
        from rclpy.node import Node
        from stackchan_msgs.action import CaptureAudio, CaptureCamera, PlayAudio, RunMotion, Say
        from stackchan_msgs.msg import StackChanEvent
        from stackchan_msgs.srv import (
            ClearEventCursor,
            GetStatus,
            GetTranscript,
            ListEvents,
            NextEvent,
            SetFace,
            SetLed,
        )
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
            self.event_buffer = EventBuffer()
            self.event_aggregator = EventAggregator(self.event_buffer)
            self.transcript_store = SpeechTranscriptStore()
            self._stackchan_event_type = StackChanEvent
            self._public_event_publishers = {}
            self._device_event_subscriptions = []
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
            self.create_service(
                ListEvents,
                f"{prefix}/events/list",
                lambda request, response, device_id=device_id: self._handle_list_events(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                NextEvent,
                f"{prefix}/events/next",
                lambda request, response, device_id=device_id: self._handle_next_event(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                ClearEventCursor,
                f"{prefix}/events/clear_cursor",
                lambda request, response, device_id=device_id: self._handle_clear_event_cursor(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                GetTranscript,
                f"{prefix}/speech/transcript/get",
                lambda request, response, device_id=device_id: self._handle_get_transcript(
                    device_id,
                    request,
                    response,
                ),
            )
            self._public_event_publishers[device_id] = self.create_publisher(
                StackChanEvent,
                f"/stackchan/{device_id}/events",
                10,
            )
            self._device_event_subscriptions.append(
                self.create_subscription(
                    StackChanEvent,
                    f"/stackchan/{device_id}/device/events",
                    lambda event, device_id=device_id: self._handle_device_event(
                        device_id,
                        event,
                    ),
                    10,
                )
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

        def _handle_list_events(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            limit = max(0, min(int(request.limit), 32))
            records = self.event_buffer.records(device_id)
            records = _records_after_event_id(records, getattr(request, "since_event_id", ""))
            records = records[-limit:] if limit else ()
            _copy_result(response.result, Result.completed("events listed"))
            _copy_records(response, self._stackchan_event_type, records)
            response.cursor = _cursor_for(records)
            return response

        def _handle_next_event(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            after_event_id = getattr(request, "after_event_id", "")
            if after_event_id:
                records = _records_after_event_id(
                    self.event_buffer.records(device_id),
                    after_event_id,
                )[:1]
            else:
                consumer_id = getattr(request, "consumer_id", "") or "stackchanctl"
                records = self.event_buffer.read(device_id, consumer_id, limit=1)
            _copy_result(response.result, Result.completed("event read"))
            _copy_records(response, self._stackchan_event_type, records)
            response.cursor = _cursor_for(records)
            return response

        def _handle_clear_event_cursor(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            consumer_id = getattr(request, "consumer_id", "") or "stackchanctl"
            self.event_buffer.clear_cursor(consumer_id, device_id)
            _copy_result(response.result, Result.completed("event cursor cleared"))
            response.cursor = ""
            return response

        def _handle_get_transcript(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            utterance_id = getattr(request, "utterance_id", "")
            transcript = self.transcript_store.get(device_id, utterance_id)
            if transcript is None:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "TRANSCRIPT_NOT_FOUND",
                        f"transcript '{utterance_id}' was not found",
                    ),
                )
                response.utterance_id = utterance_id
                response.transcript = ""
                response.confidence = 0.0
                return response
            _copy_result(response.result, Result.completed("transcript found"))
            _copy_transcript(response, transcript)
            return response

        def _handle_device_event(self, device_id: str, event: object) -> None:
            payload_json = getattr(event, "payload_json", "")
            transcript_payload = _transcript_from_event_payload(payload_json)
            record = self.event_aggregator.add(
                device_id,
                getattr(event, "event_name", ""),
                command_id=getattr(event, "command_id", ""),
                source=getattr(event, "source", "") or "firmware",
                event_id=getattr(event, "event_id", ""),
                payload=payload_json,
                stamp=_stamp_to_seconds(getattr(event, "stamp", None)),
            )
            if record is None:
                return
            self._maybe_store_transcript(record, transcript_payload)
            public_event = self._stackchan_event_type()
            _copy_event_record(public_event, record)
            self._public_event_publishers[device_id].publish(public_event)

        def _maybe_store_transcript(
            self,
            record: EventRecord,
            transcript_payload: tuple[str, str] | None,
        ) -> None:
            if record.event_name != "transcript_ready" or transcript_payload is None:
                return
            utterance_id, transcript = transcript_payload
            self.transcript_store.put(
                record.device_id,
                utterance_id,
                transcript,
                command_id=record.command_id,
                source=record.source,
            )

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
