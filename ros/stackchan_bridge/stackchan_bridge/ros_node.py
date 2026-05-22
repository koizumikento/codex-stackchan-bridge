"""Lazy ROS 2 node adapter for the StackChan bridge facade."""

from __future__ import annotations

import json
import time

from stackchan_bridge.audio_session import AudioChunk
from stackchan_bridge.event_aggregator import EventAggregator
from stackchan_bridge.event_buffer import EventBuffer, EventRecord
from stackchan_bridge.facade import StackChanBridgeFacade
from stackchan_bridge.models import CapabilitySnapshot, CommandMeta, Result, StatusSnapshot
from stackchan_bridge.models import PRIORITY_SAFETY
from stackchan_bridge.models import STATE_COMPLETED
from stackchan_bridge.models import STATE_TIMEOUT
from stackchan_bridge.registry import DeviceAvailability, DeviceRecord, DeviceRegistry
from stackchan_bridge.speech_node import SpeechEvent, SpeechSessionProcessor
from stackchan_bridge.speech_session import SpeechTranscript, SpeechTranscriptStore
from stackchan_bridge.telemetry import HeadPoseSnapshot, HeadPoseTelemetryStore, PowerStatusSnapshot, PowerTelemetryStore

EVENT_QOS_DEPTH = 32
DEFAULT_LIVENESS_TIMEOUT_SEC = 3.5
LIVENESS_CHECK_INTERVAL_SEC = 1.0


def _time_to_string(stamp: object) -> str:
    sec = getattr(stamp, "sec", 0)
    nanosec = getattr(stamp, "nanosec", 0)
    return f"{sec}.{nanosec:09d}"


def _meta_from_ros(meta: object, fallback_device_id: str = "default") -> CommandMeta:
    return CommandMeta(
        device_id=fallback_device_id,
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


def _copy_command_meta(target: object, source: CommandMeta, created_at: object) -> None:
    target.device_id = source.device_id
    target.command_id = source.command_id
    target.source = source.source
    target.created_at = created_at
    target.priority = source.priority


def _make_transport_result(message: str) -> Result:
    return Result.rejected("TRANSPORT_DISCONNECTED", message, recoverable=True)


def _make_timeout_result(message: str) -> Result:
    return Result(
        ok=False,
        state=STATE_TIMEOUT,
        error_code="TIMEOUT",
        message=message,
        recoverable=True,
    )


def _copy_status(response: object, status: object) -> None:
    response.device_id = status.device_id
    response.connected = status.connected
    response.state = status.state
    response.face = status.face
    response.motion = status.motion
    response.last_command_id = status.last_command_id
    _copy_result(response.last_error, status.last_error)
    if hasattr(response, "firmware_version"):
        response.firmware_version = getattr(status, "firmware_version", "")


def _copy_status_with_type(response: object, status: object, capability_type: object) -> None:
    _copy_status(response, status)
    if hasattr(response, "capabilities"):
        response.capabilities = [
            _make_capability_status(capability_type, capability)
            for capability in getattr(status, "capabilities", [])
        ]


def _make_capability_status(capability_type: object, capability: object) -> object:
    message = capability_type()
    message.name = getattr(capability, "name", "")
    message.state = getattr(capability, "state", "")
    message.detail_code = getattr(capability, "detail_code", "")
    message.active = bool(getattr(capability, "active", False))
    message.queued = int(getattr(capability, "queued", 0))
    last_update = getattr(capability, "last_update", None)
    if last_update is not None:
        _copy_seconds_to_stamp(message.last_update, float(last_update))
    return message


def _result_from_ros(source: object) -> Result:
    return Result(
        ok=bool(getattr(source, "ok", True)),
        state=int(getattr(source, "state", 1)),
        error_code=getattr(source, "error_code", ""),
        message=getattr(source, "message", ""),
        recoverable=bool(getattr(source, "recoverable", False)),
    )


def _capability_from_ros(source: object) -> CapabilitySnapshot:
    last_update = _stamp_to_seconds(getattr(source, "last_update", None))
    return CapabilitySnapshot(
        name=getattr(source, "name", ""),
        state=getattr(source, "state", ""),
        detail_code=getattr(source, "detail_code", ""),
        active=bool(getattr(source, "active", False)),
        queued=int(getattr(source, "queued", 0)),
        last_update=last_update,
    )


def _snapshot_from_stackchan_status(
    status: object, *, fallback_device_id: str
) -> StatusSnapshot:
    capabilities = [
        _capability_from_ros(capability)
        for capability in getattr(status, "capabilities", [])
    ]
    return StatusSnapshot(
        device_id=getattr(status, "device_id", "") or fallback_device_id,
        connected=bool(getattr(status, "connected", False)),
        state=getattr(status, "state", "") or "unknown",
        face=getattr(status, "face", "") or "neutral",
        motion=getattr(status, "motion", "") or "idle",
        last_command_id=getattr(status, "last_command_id", ""),
        last_error=_result_from_ros(getattr(status, "last_error", object())),
        firmware_version=getattr(status, "firmware_version", ""),
        capabilities=capabilities or StatusSnapshot().capabilities,
    )


def _reject_external_safety_priority(meta: CommandMeta, response: object) -> bool:
    if meta.priority != PRIORITY_SAFETY:
        return False

    result = Result.rejected(
        "INVALID_PRIORITY",
        "SAFETY priority is reserved for bridge and firmware internals.",
    )
    if hasattr(response, "result"):
        _copy_result(response.result, result)
    elif hasattr(response, "last_error"):
        _copy_result(response.last_error, result)

    if hasattr(response, "events"):
        response.events = []
    if hasattr(response, "cursor"):
        response.cursor = ""
    if hasattr(response, "stale"):
        response.stale = False
    if hasattr(response, "transcript"):
        response.transcript = ""
    if hasattr(response, "confidence"):
        response.confidence = 0.0
    return True


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


def _event_matches_device_id(device_id: str, event: object) -> bool:
    incoming_device_id = getattr(event, "device_id", "")
    return not incoming_device_id or incoming_device_id == device_id


def _status_matches_device_id(device_id: str, status: object) -> bool:
    incoming_device_id = getattr(status, "device_id", "")
    return not incoming_device_id or incoming_device_id == device_id


def _mark_device_available_from_event(
    registry: DeviceRegistry,
    device_id: str,
    event: object,
) -> bool:
    if not _event_matches_device_id(device_id, event):
        return False
    source = getattr(event, "source", "") or "firmware"
    event_name = getattr(event, "event_name", "")
    if source != "firmware" or not event_name:
        return False
    was_available = registry.availability(device_id) == DeviceAvailability.AVAILABLE
    registry.set_connected(device_id, True)
    return not was_available


def _mark_device_available_from_status(
    registry: DeviceRegistry,
    device_id: str,
    status: object,
) -> bool:
    if not _status_matches_device_id(device_id, status):
        return False
    is_connected = bool(getattr(status, "connected", False))
    was_available = registry.availability(device_id) == DeviceAvailability.AVAILABLE
    registry.set_connected(device_id, is_connected)
    return is_connected and not was_available


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
        from rclpy.action import ActionServer
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.executors import MultiThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from stackchan_msgs.action import CaptureAudio, CaptureCamera, MoveHeadPose, PlayAudio, RunMotion, Say
        from stackchan_msgs.msg import AudioChunk as RosAudioChunk
        from stackchan_msgs.msg import CapabilityStatus
        from stackchan_msgs.msg import (
            HeadPose,
            LightRaw,
            PowerStatus,
            ProximityRaw,
            StackChanEvent,
            StackChanStatus,
            TouchState,
        )
        from stackchan_msgs.srv import (
            ClearEventCursor,
            GetHeadPose,
            GetPowerStatus,
            GetStatus,
            GetTranscript,
            ListEvents,
            NextEvent,
            SetFace,
            SetHeadPose,
            SetLed,
            SetMotion,
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
            self.declare_parameter("liveness_timeout_sec", DEFAULT_LIVENESS_TIMEOUT_SEC)
            self._liveness_timeout_sec = float(
                self.get_parameter("liveness_timeout_sec").value
            )
            self.declare_parameter("device_command_timeout_sec", 2.0)
            self._device_command_timeout_sec = float(
                self.get_parameter("device_command_timeout_sec").value
            )
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
            self._stackchan_status_type = StackChanStatus
            self._set_face_type = SetFace
            self._set_head_pose_type = SetHeadPose
            self._set_motion_type = SetMotion
            self._command_callback_group = ReentrantCallbackGroup()
            self._device_client_callback_group = ReentrantCallbackGroup()
            self._public_event_publishers = {}
            self._public_status_publishers = {}
            self._device_face_clients = {}
            self._device_head_pose_clients = {}
            self._device_motion_clients = {}
            self._device_event_subscriptions = []
            self._device_status_subscriptions = []
            self._speech_audio_subscriptions = []
            self._telemetry_publishers = {}
            self._telemetry_subscriptions = []
            self._device_last_seen = {}
            self._power_status_type = PowerStatus
            self._head_pose_type = HeadPose
            self._capability_status_type = CapabilityStatus
            self._action_servers = []
            for device_id in configured_device_ids:
                self._create_device_resources(device_id)
            self._liveness_timer = self.create_timer(
                LIVENESS_CHECK_INTERVAL_SEC,
                self._expire_stale_devices,
            )

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
                callback_group=self._command_callback_group,
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
            self._device_face_clients[device_id] = self.create_client(
                SetFace,
                f"/stackchan/{device_id}/device/face/set",
                callback_group=self._device_client_callback_group,
            )
            self._device_motion_clients[device_id] = self.create_client(
                SetMotion,
                f"/stackchan/{device_id}/device/motion/run",
                callback_group=self._device_client_callback_group,
            )
            self._device_head_pose_clients[device_id] = self.create_client(
                SetHeadPose,
                f"/stackchan/{device_id}/device/motion/pose/set",
                callback_group=self._device_client_callback_group,
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
            self._public_status_publishers[device_id] = self.create_publisher(
                StackChanStatus,
                f"/stackchan/{device_id}/status",
                transient_depth_1,
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
            self._device_status_subscriptions.append(
                self.create_subscription(
                    StackChanStatus,
                    f"/stackchan/{device_id}/device/status",
                    lambda status, device_id=device_id: self._handle_device_status(
                        device_id,
                        status,
                    ),
                    reliable_depth_2,
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
                    callback_group=self._command_callback_group,
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
            if _reject_external_safety_priority(meta, response):
                response.device_id = meta.device_id
                response.connected = (
                    self.facade.registry.availability(meta.device_id)
                    == DeviceAvailability.AVAILABLE
                )
                response.state = "rejected"
                response.face = ""
                response.motion = ""
                response.last_command_id = meta.command_id
                return response
            status_response = self.facade.get_status(
                meta.device_id,
                command_id=meta.command_id,
            )
            _copy_status_with_type(
                response,
                status_response.status,
                self._capability_status_type,
            )
            return response

        def _handle_set_face(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            command_response = self.facade.set_face(
                meta,
                request.name,
                request.duration_ms,
            )
            if not command_response.result.ok:
                _copy_result(response.result, command_response.result)
                return response

            device_result = self._call_device_face_set(device_id, request, meta)
            _copy_result(response.result, device_result)
            return response

        def _call_device_face_set(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> Result:
            client = self._device_face_clients.get(device_id)
            if client is None:
                return _make_transport_result(
                    f"firmware face service for '{device_id}' is not configured"
                )
            if not client.wait_for_service(timeout_sec=0.1):
                return _make_transport_result(
                    f"firmware face service for '{device_id}' is unavailable"
                )

            device_request = self._set_face_type.Request()
            _copy_command_meta(
                device_request.meta,
                meta,
                getattr(request.meta, "created_at", device_request.meta.created_at),
            )
            device_request.name = request.name
            device_request.duration_ms = request.duration_ms

            future = client.call_async(device_request)
            deadline = time.monotonic() + self._device_command_timeout_sec
            while not future.done() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not future.done():
                future.cancel()
                return _make_timeout_result(
                    f"firmware face service for '{device_id}' timed out"
                )
            try:
                device_response = future.result()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                return _make_transport_result(
                    f"firmware face service for '{device_id}' failed: {exc}"
                )
            return _result_from_ros(device_response.result)

        def _call_device_motion_run(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> Result:
            client = self._device_motion_clients.get(device_id)
            if client is None:
                return _make_transport_result(
                    f"firmware motion service for '{device_id}' is not configured"
                )
            if not client.wait_for_service(timeout_sec=0.1):
                return _make_transport_result(
                    f"firmware motion service for '{device_id}' is unavailable"
                )

            device_request = self._set_motion_type.Request()
            _copy_command_meta(
                device_request.meta,
                meta,
                getattr(request.meta, "created_at", device_request.meta.created_at),
            )
            device_request.name = request.name
            device_request.intensity = request.intensity
            device_request.duration_ms = request.duration_ms

            future = client.call_async(device_request)
            deadline = time.monotonic() + self._device_command_timeout_sec
            while not future.done() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not future.done():
                future.cancel()
                return _make_timeout_result(
                    f"firmware motion service for '{device_id}' timed out"
                )
            try:
                device_response = future.result()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                return _make_transport_result(
                    f"firmware motion service for '{device_id}' failed: {exc}"
                )
            return _result_from_ros(device_response.result)

        def _handle_list_events(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            if _reject_external_safety_priority(meta, response):
                return response
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
            if _reject_external_safety_priority(meta, response):
                return response
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
            if _reject_external_safety_priority(meta, response):
                return response
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
            meta = _meta_from_ros(request.meta, device_id)
            if _reject_external_safety_priority(meta, response):
                response.utterance_id = getattr(request, "utterance_id", "")
                return response
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
            meta = _meta_from_ros(request.meta, device_id)
            if _reject_external_safety_priority(meta, response):
                return response
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
            if _reject_external_safety_priority(meta, response):
                return response
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

        def _publish_status(self, device_id: str) -> None:
            publisher = self._public_status_publishers.get(device_id)
            if publisher is None:
                return
            status_response = self.facade.get_status(device_id)
            public_status = self._stackchan_status_type()
            _copy_status_with_type(
                public_status,
                status_response.status,
                self._capability_status_type,
            )
            publisher.publish(public_status)

        def _handle_device_status(self, device_id: str, status: object) -> None:
            if not _status_matches_device_id(device_id, status):
                self.get_logger().warning(
                    f"dropping firmware status for unexpected device_id={getattr(status, 'device_id', '')!r}"
                )
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="device_conflict_detected",
                        source="bridge",
                        payload={
                            "topic": "status",
                            "received_device_id": getattr(status, "device_id", ""),
                        },
                    )
                )
                return
            now = self.get_clock().now().nanoseconds / 1_000_000_000
            self._device_last_seen[device_id] = now
            became_available = _mark_device_available_from_status(
                self.facade.registry,
                device_id,
                status,
            )
            snapshot = _snapshot_from_stackchan_status(
                status,
                fallback_device_id=device_id,
            )
            self.facade.update_status(snapshot)
            if became_available:
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="device_connected",
                        source="bridge",
                        payload={"reason": "firmware_status"},
                    )
                )
            self._publish_status(device_id)

        def _expire_stale_devices(self) -> None:
            if self._liveness_timeout_sec <= 0:
                return
            now = self.get_clock().now().nanoseconds / 1_000_000_000
            for device_id, last_seen in tuple(self._device_last_seen.items()):
                if now - last_seen <= self._liveness_timeout_sec:
                    continue
                if self.facade.registry.availability(device_id) != DeviceAvailability.AVAILABLE:
                    continue
                self.facade.registry.set_connected(device_id, False)
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="device_disconnected",
                        source="bridge",
                        payload={
                            "reason": "liveness_timeout",
                            "timeout_sec": self._liveness_timeout_sec,
                        },
                    )
                )
                self._publish_status(device_id)

        def _handle_device_event(self, device_id: str, event: object) -> None:
            if not _event_matches_device_id(device_id, event):
                self.get_logger().warning(
                    f"dropping firmware event for unexpected device_id={getattr(event, 'device_id', '')!r}"
                )
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="device_conflict_detected",
                        source="bridge",
                        payload={
                            "topic": "events",
                            "received_device_id": getattr(event, "device_id", ""),
                        },
                    )
                )
                return
            became_available = _mark_device_available_from_event(
                self.facade.registry,
                device_id,
                event,
            )
            if became_available:
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="device_connected",
                        source="bridge",
                        payload={"reason": "firmware_event"},
                    )
                )
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
            meta = _meta_from_ros(request.meta, device_id)
            command_response = self.facade.run_motion(
                meta,
                request.name,
                request.intensity,
                request.duration_ms,
            )
            if command_response.result.ok:
                device_result = self._call_device_motion_run(device_id, request, meta)
                command_response = type(command_response)(
                    command_response.device_id,
                    command_response.command_id,
                    device_result,
                )
            result = RunMotion.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _call_device_head_pose(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> object:
            client = self._device_head_pose_clients.get(device_id)
            response = type("HeadPoseDeviceResponse", (), {})()
            response.result = _make_transport_result(
                f"firmware head pose service for '{device_id}' is not configured"
            )
            response.pose = self._head_pose_type()
            if client is None:
                return response
            if not client.wait_for_service(timeout_sec=0.1):
                response.result = _make_transport_result(
                    f"firmware head pose service for '{device_id}' is unavailable"
                )
                return response

            device_request = self._set_head_pose_type.Request()
            _copy_command_meta(
                device_request.meta,
                meta,
                getattr(request.meta, "created_at", device_request.meta.created_at),
            )
            device_request.home = bool(getattr(request, "home", False))
            device_request.pan_deg = float(getattr(request, "pan_deg", 0.0))
            device_request.tilt_deg = float(getattr(request, "tilt_deg", 0.0))
            device_request.speed = int(getattr(request, "speed", 0))
            device_request.duration_ms = int(getattr(request, "duration_ms", 0))

            future = client.call_async(device_request)
            deadline = time.monotonic() + self._device_command_timeout_sec
            while not future.done() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not future.done():
                future.cancel()
                response.result = _make_timeout_result(
                    f"firmware head pose service for '{device_id}' timed out"
                )
                return response
            try:
                device_response = future.result()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                response.result = _make_transport_result(
                    f"firmware head pose service for '{device_id}' failed: {exc}"
                )
                return response
            response.result = _result_from_ros(device_response.result)
            response.pose = device_response.pose
            return response

        def _handle_move_head_pose(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            meta = _meta_from_ros(request.meta, device_id)
            is_home = bool(getattr(request, "home", False))
            if is_home:
                command_response = self.facade.home_head_pose(
                    meta,
                    int(request.speed),
                    int(request.duration_ms),
                )
            else:
                command_response = self.facade.move_head_pose(
                    meta,
                    float(request.pan_deg),
                    float(request.tilt_deg),
                    int(request.speed),
                    int(request.duration_ms),
                )
            result = MoveHeadPose.Result()
            if command_response.result.ok:
                device_response = self._call_device_head_pose(device_id, request, meta)
                command_response = type(command_response)(
                    command_response.device_id,
                    command_response.command_id,
                    device_response.result,
                )
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                snapshot = _snapshot_from_head_pose(
                    device_response.pose,
                    fallback_device_id=meta.device_id,
                )
                if snapshot.device_id != meta.device_id:
                    _copy_result(
                        result.result,
                        Result.rejected(
                            "DEVICE_ID_CONFLICT",
                            "firmware head pose response device_id does not match target",
                            recoverable=True,
                        ),
                    )
                    goal_handle.abort()
                    return result
                if int(command_response.result.state) == STATE_COMPLETED:
                    self.head_pose_store.update(snapshot)
                    publisher = self._telemetry_publishers.get((device_id, "motion/pose"))
                    if publisher is not None:
                        message = self._head_pose_type()
                        _copy_head_pose(message, snapshot)
                        publisher.publish(message)
                _copy_head_pose(result.pose, snapshot)
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
                _meta_from_ros(request.meta, device_id),
                format=request.format,
                sample_rate=int(request.sample_rate),
                channels=int(request.channels),
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
                _meta_from_ros(request.meta, device_id),
                format=request.format,
                sample_rate=int(request.sample_rate),
                channels=int(request.channels),
                duration_ms=int(request.duration_ms),
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
                _meta_from_ros(request.meta, device_id),
                format=request.format,
                width=int(request.width),
                height=int(request.height),
                quality=int(request.quality),
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
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.remove_node(node)
        node.destroy_node()
        rclpy.shutdown()
