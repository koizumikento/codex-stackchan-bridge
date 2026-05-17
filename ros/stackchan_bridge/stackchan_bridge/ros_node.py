"""Lazy ROS 2 node adapter for the StackChan bridge facade."""

from __future__ import annotations

import json

from stackchan_bridge.audio_session import AudioChunk
from stackchan_bridge.event_aggregator import EventAggregator
from stackchan_bridge.event_buffer import EventBuffer, EventRecord
from stackchan_bridge.facade import StackChanBridgeFacade
from stackchan_bridge.models import CommandMeta, Result
from stackchan_bridge.registry import DeviceRecord, DeviceRegistry
from stackchan_bridge.speech_node import SpeechEvent, SpeechSessionProcessor
from stackchan_bridge.speech_session import SpeechTranscript, SpeechTranscriptStore
from stackchan_bridge.telemetry import HeadPoseSnapshot, HeadPoseTelemetryStore, PowerStatusSnapshot, PowerTelemetryStore

EVENT_QOS_DEPTH = 32


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


def _sequence_for_event_id(records: tuple[EventRecord, ...], event_id: str) -> int | None:
    if not event_id:
        return None
    for record in records:
        if record.event_id == event_id:
            return record.sequence
    return None


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
    response.confidence = transcript.confidence
    _copy_seconds_to_stamp(response.expires_at, transcript.expires_at)


def _snapshot_from_power_status(status: object, *, fallback_device_id: str) -> PowerStatusSnapshot:
    stamp = _stamp_to_seconds(getattr(status, "stamp", None))
    return PowerStatusSnapshot(
        device_id=getattr(status, "device_id", "") or fallback_device_id,
        voltage_v=float(getattr(status, "voltage_v", float("nan"))),
        current_ma=float(getattr(status, "current_ma", float("nan"))),
        power_mw=float(getattr(status, "power_mw", float("nan"))),
        percentage=float(getattr(status, "percentage", float("nan"))),
        power_source=int(getattr(status, "power_source", 0)),
        charging=bool(getattr(status, "charging", False)),
        powered=bool(getattr(status, "powered", False)),
        low_battery=bool(getattr(status, "low_battery", False)),
        brownout_risk=bool(getattr(status, "brownout_risk", False)),
        fault_code=getattr(status, "fault_code", ""),
        stamp=stamp if stamp is not None else 0.0,
    )


def _snapshot_from_head_pose(pose: object, *, fallback_device_id: str) -> HeadPoseSnapshot:
    stamp = _stamp_to_seconds(getattr(pose, "stamp", None))
    return HeadPoseSnapshot(
        device_id=getattr(pose, "device_id", "") or fallback_device_id,
        pan_deg=float(getattr(pose, "pan_deg", float("nan"))),
        tilt_deg=float(getattr(pose, "tilt_deg", float("nan"))),
        moving=bool(getattr(pose, "moving", False)),
        frame=getattr(pose, "frame", "") or "home",
        stamp=stamp if stamp is not None else 0.0,
    )


def _copy_power_status(target: object, snapshot: PowerStatusSnapshot) -> None:
    target.device_id = snapshot.device_id
    _copy_seconds_to_stamp(target.stamp, snapshot.stamp)
    target.voltage_v = snapshot.voltage_v
    target.current_ma = snapshot.current_ma
    target.power_mw = snapshot.power_mw
    target.percentage = snapshot.percentage
    target.power_source = snapshot.power_source
    target.charging = snapshot.charging
    target.powered = snapshot.powered
    target.low_battery = snapshot.low_battery
    target.brownout_risk = snapshot.brownout_risk
    target.fault_code = snapshot.fault_code


def _copy_head_pose(target: object, snapshot: HeadPoseSnapshot) -> None:
    target.device_id = snapshot.device_id
    _copy_seconds_to_stamp(target.stamp, snapshot.stamp)
    target.pan_deg = snapshot.pan_deg
    target.tilt_deg = snapshot.tilt_deg
    target.moving = snapshot.moving
    target.frame = snapshot.frame


def _coerce_telemetry_device_id(message: object, expected_device_id: str) -> bool:
    incoming_device_id = getattr(message, "device_id", "")
    if not incoming_device_id:
        message.device_id = expected_device_id
        return True
    return incoming_device_id == expected_device_id


def _relay_telemetry_message(
    device_id: str,
    tail: str,
    message: object,
    publisher: object,
    *,
    power_store: PowerTelemetryStore | None = None,
    head_pose_store: HeadPoseTelemetryStore | None = None,
    conflict_handler: object | None = None,
) -> bool:
    if not _coerce_telemetry_device_id(message, device_id):
        if callable(conflict_handler):
            conflict_handler(device_id, tail, message)
        return False
    if tail == "power/status" and power_store is not None:
        power_store.update(_snapshot_from_power_status(message, fallback_device_id=device_id))
    if tail == "motion/pose" and head_pose_store is not None:
        head_pose_store.update(_snapshot_from_head_pose(message, fallback_device_id=device_id))
    publisher.publish(message)
    return True


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
        from rclpy.action import ActionServer
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from stackchan_msgs.action import CaptureAudio, CaptureCamera, MoveHeadPose, PlayAudio, RunMotion, Say
        from stackchan_msgs.msg import AudioChunk as RosAudioChunk
        from stackchan_msgs.msg import HeadPose, LightRaw, PowerStatus, ProximityRaw, StackChanEvent, TouchState
        from stackchan_msgs.srv import (
            ClearEventCursor,
            GetHeadPose,
            GetPowerStatus,
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

    reliable_depth_2 = QoSProfile(depth=2)
    reliable_depth_4 = QoSProfile(depth=4)
    best_effort_depth_5 = QoSProfile(depth=5)
    best_effort_depth_5.reliability = ReliabilityPolicy.BEST_EFFORT
    best_effort_depth_8 = QoSProfile(depth=8)
    best_effort_depth_8.reliability = ReliabilityPolicy.BEST_EFFORT
    best_effort_depth_10 = QoSProfile(depth=10)
    best_effort_depth_10.reliability = ReliabilityPolicy.BEST_EFFORT
    transient_depth_1 = QoSProfile(depth=1)
    transient_depth_1.durability = DurabilityPolicy.TRANSIENT_LOCAL

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
            self.speech_processor = SpeechSessionProcessor(
                transcript_store=self.transcript_store,
                event_sink=self._handle_speech_event,
            )
            self.power_store = PowerTelemetryStore()
            self.head_pose_store = HeadPoseTelemetryStore()
            self._stackchan_event_type = StackChanEvent
            self._public_event_publishers = {}
            self._device_event_subscriptions = []
            self._speech_audio_subscriptions = []
            self._telemetry_publishers = {}
            self._telemetry_subscriptions = []
            self._power_status_type = PowerStatus
            self._head_pose_type = HeadPose
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
            self.create_service(
                GetPowerStatus,
                f"{prefix}/power/status",
                lambda request, response, device_id=device_id: self._handle_get_power_status(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                GetHeadPose,
                f"{prefix}/motion/status",
                lambda request, response, device_id=device_id: self._handle_get_head_pose(
                    device_id,
                    request,
                    response,
                ),
            )
            self._public_event_publishers[device_id] = self.create_publisher(
                StackChanEvent,
                f"/stackchan/{device_id}/events",
                QoSProfile(depth=EVENT_QOS_DEPTH),
            )
            self._create_telemetry_relay(
                device_id,
                "touch/state",
                TouchState,
                public_qos=transient_depth_1,
                device_qos=reliable_depth_4,
            )
            self._create_telemetry_relay(
                device_id,
                "proximity/raw",
                ProximityRaw,
                public_qos=best_effort_depth_10,
                device_qos=best_effort_depth_10,
            )
            self._create_telemetry_relay(
                device_id,
                "light/raw",
                LightRaw,
                public_qos=best_effort_depth_5,
                device_qos=best_effort_depth_5,
            )
            self._create_telemetry_relay(
                device_id,
                "power/status",
                PowerStatus,
                public_qos=transient_depth_1,
                device_qos=reliable_depth_2,
            )
            self._create_telemetry_relay(
                device_id,
                "motion/pose",
                HeadPose,
                public_qos=transient_depth_1,
                device_qos=reliable_depth_2,
            )
            self._speech_audio_subscriptions.append(
                self.create_subscription(
                    RosAudioChunk,
                    f"/stackchan/{device_id}/device/audio/chunks",
                    lambda message, device_id=device_id: self._handle_speech_audio_chunk(
                        device_id,
                        message,
                    ),
                    best_effort_depth_8,
                )
            )
            self._device_event_subscriptions.append(
                self.create_subscription(
                    StackChanEvent,
                    f"/stackchan/{device_id}/device/events",
                    lambda event, device_id=device_id: self._handle_device_event(
                        device_id,
                        event,
                    ),
                    QoSProfile(depth=EVENT_QOS_DEPTH),
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
                    MoveHeadPose,
                    f"{prefix}/motion/pose",
                    lambda goal_handle, device_id=device_id: self._handle_move_head_pose(
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
            meta = _meta_from_ros(request.meta, device_id)
            status_response = self.facade.get_status(
                meta.device_id,
                command_id=meta.command_id,
            )
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
            meta = _meta_from_ros(request.meta, device_id)
            consumer_id = getattr(request, "consumer_id", "") or meta.source or "stackchanctl"
            after_event_id = getattr(request, "after_event_id", "")
            if after_event_id:
                after_sequence = _sequence_for_event_id(
                    self.event_buffer.records(device_id),
                    after_event_id,
                )
                records = self.event_buffer.read(
                    device_id,
                    consumer_id,
                    limit=1,
                    after_sequence=0 if after_sequence is None else after_sequence,
                )
            else:
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
            meta = _meta_from_ros(request.meta, device_id)
            consumer_id = getattr(request, "consumer_id", "") or meta.source or "stackchanctl"
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

        def _handle_get_power_status(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            del request
            snapshot, stale = self.power_store.get(device_id)
            if snapshot is None:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "UNSUPPORTED_FEATURE",
                        f"power telemetry for '{device_id}' has not been received",
                    ),
                )
                response.stale = False
                return response
            if stale:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "STALE_TELEMETRY",
                        f"power telemetry for '{device_id}' is stale",
                        recoverable=True,
                    ),
                )
            else:
                _copy_result(response.result, Result.completed("power status found"))
            _copy_power_status(response.status, snapshot)
            response.stale = stale
            return response

        def _handle_get_head_pose(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            status_response = self.facade.get_status(
                meta.device_id,
                command_id=meta.command_id,
            )
            if not status_response.status.connected:
                _copy_result(response.result, status_response.status.last_error)
                response.stale = False
                return response

            snapshot, stale = self.head_pose_store.get(device_id)
            if snapshot is None:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "UNSUPPORTED_FEATURE",
                        f"head pose telemetry for '{device_id}' has not been received",
                    ),
                )
                response.stale = False
                return response
            if stale:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "STALE_TELEMETRY",
                        f"head pose telemetry for '{device_id}' is stale",
                        recoverable=True,
                    ),
                )
            else:
                _copy_result(response.result, Result.completed("head pose found"))
            _copy_head_pose(response.pose, snapshot)
            response.stale = stale
            return response

        def _create_telemetry_relay(
            self,
            device_id: str,
            tail: str,
            message_type: object,
            *,
            public_qos: object,
            device_qos: object,
        ) -> None:
            public_topic = f"/stackchan/{device_id}/{tail}"
            device_topic = f"/stackchan/{device_id}/device/{tail}"
            publisher = self.create_publisher(message_type, public_topic, public_qos)
            self._telemetry_publishers[(device_id, tail)] = publisher
            self._telemetry_subscriptions.append(
                self.create_subscription(
                    message_type,
                    device_topic,
                    lambda message, device_id=device_id, tail=tail, publisher=publisher: self._handle_telemetry(
                        device_id,
                        tail,
                        message,
                        publisher,
                    ),
                    device_qos,
                )
            )

        def _handle_telemetry(
            self,
            device_id: str,
            tail: str,
            message: object,
            publisher: object,
        ) -> None:
            if not _relay_telemetry_message(
                device_id,
                tail,
                message,
                publisher,
                power_store=self.power_store,
                head_pose_store=self.head_pose_store,
                conflict_handler=self._handle_telemetry_device_id_conflict,
            ):
                return

        def _handle_telemetry_device_id_conflict(self, device_id: str, tail: str, message: object) -> None:
            received_device_id = getattr(message, "device_id", "")
            if received_device_id == device_id:
                return
            if received_device_id:
                self.get_logger().warning(
                    f"dropping {tail} telemetry for unexpected device_id={received_device_id!r}"
                )
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="telemetry_device_id_conflict",
                        source="bridge",
                        payload={
                            "topic": tail,
                            "received_device_id": received_device_id,
                        },
                    )
                )

        def _handle_speech_audio_chunk(self, device_id: str, message: object) -> None:
            if not _coerce_telemetry_device_id(message, device_id):
                self.get_logger().warning(
                    f"dropping audio chunk for unexpected device_id={getattr(message, 'device_id', '')!r}"
                )
                return
            chunk = AudioChunk(
                device_id=getattr(message, "device_id", "") or device_id,
                command_id=getattr(message, "command_id", ""),
                direction=int(getattr(message, "direction", 0)),
                sequence=int(getattr(message, "sequence", 0)),
                format=int(getattr(message, "format", 0)),
                sample_rate=int(getattr(message, "sample_rate", 0)),
                channels=int(getattr(message, "channels", 0)),
                pcm=bytes(getattr(message, "pcm", b"")),
            )
            self.speech_processor.handle_audio_chunk(chunk)

        def _handle_speech_event(self, event: SpeechEvent) -> None:
            record = self.event_aggregator.add(
                event.device_id,
                event.event_name,
                command_id=event.command_id,
                source=event.source,
                payload=event.payload,
            )
            if record is None:
                return
            self._publish_event_record(record)

        def _publish_event_record(self, record: EventRecord) -> None:
            publisher = self._public_event_publishers.get(record.device_id)
            if publisher is None:
                return
            public_event = self._stackchan_event_type()
            _copy_event_record(public_event, record)
            publisher.publish(public_event)

        def _handle_device_event(self, device_id: str, event: object) -> None:
            payload_json = getattr(event, "payload_json", "")
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
            self._publish_event_record(record)

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

        def _handle_move_head_pose(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            meta = _meta_from_ros(request.meta, device_id)
            command_response = self.facade.move_head_pose(
                meta,
                float(request.pan_deg),
                float(request.tilt_deg),
                int(request.speed),
                int(request.duration_ms),
            )
            result = MoveHeadPose.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                snapshot = HeadPoseSnapshot(
                    device_id=meta.device_id,
                    pan_deg=float(request.pan_deg),
                    tilt_deg=float(request.tilt_deg),
                    moving=False,
                    frame="home",
                    stamp=self.get_clock().now().nanoseconds / 1_000_000_000,
                )
                self.head_pose_store.update(snapshot)
                _copy_head_pose(result.pose, snapshot)
                publisher = self._telemetry_publishers.get((device_id, "motion/pose"))
                if publisher is not None:
                    message = self._head_pose_type()
                    _copy_head_pose(message, snapshot)
                    publisher.publish(message)
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
