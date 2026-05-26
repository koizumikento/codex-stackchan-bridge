from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from stackchan_bridge.event_buffer import EventRecord
from stackchan_bridge.ros_node import (
    _coerce_telemetry_device_id,
    _copy_command_meta,
    _copy_power_status,
    _copy_head_pose,
    _copy_status_with_type,
    _copy_event_record,
    _configured_device_records,
    _event_matches_device_id,
    _mark_device_available_from_event,
    _mark_device_available_from_status,
    _snapshot_from_power_status,
    _snapshot_from_head_pose,
    _snapshot_from_stackchan_status,
    _records_after_event_id,
    _sequence_for_event_id,
    _select_playback_chunk_for_pull,
    _select_playback_chunks_for_topic_window,
    _meta_from_ros,
    _normalize_device_ids,
    _reject_external_safety_priority,
    _relay_telemetry_message,
    _status_matches_device_id,
)
from stackchan_bridge.models import CapabilitySnapshot, Result, StatusSnapshot
from stackchan_bridge.registry import DeviceAvailability, DeviceRecord, DeviceRegistry
from stackchan_bridge.telemetry import HeadPoseSnapshot, PowerStatusSnapshot


ROOT = Path(__file__).resolve().parents[1]


class RosNodeHelperTests(unittest.TestCase):
    def test_select_playback_chunk_for_pull_is_idempotent_for_same_sequence(self) -> None:
        queue = [
            SimpleNamespace(sequence=4, pcm=b"old"),
            SimpleNamespace(sequence=5, pcm=b"five"),
            SimpleNamespace(sequence=6, pcm=b"six"),
        ]

        first, buffered = _select_playback_chunk_for_pull(queue, 5)
        retry, retry_buffered = _select_playback_chunk_for_pull(queue, 5)

        self.assertEqual(first.pcm, b"five")
        self.assertEqual(retry.pcm, b"five")
        self.assertEqual(buffered, 2)
        self.assertEqual(retry_buffered, 2)
        self.assertEqual([chunk.sequence for chunk in queue], [5, 6])

    def test_select_playback_chunk_for_pull_discards_acknowledged_sequences(self) -> None:
        queue = [
            SimpleNamespace(sequence=5, pcm=b"five"),
            SimpleNamespace(sequence=6, pcm=b"six"),
        ]

        chunk, buffered = _select_playback_chunk_for_pull(queue, 6)

        self.assertEqual(chunk.pcm, b"six")
        self.assertEqual(buffered, 1)
        self.assertEqual([item.sequence for item in queue], [6])

    def test_select_playback_chunks_for_topic_window_limits_future_chunks(self) -> None:
        queue = [SimpleNamespace(sequence=index) for index in range(2, 12)]

        window = _select_playback_chunks_for_topic_window(queue, 4, 3)

        self.assertEqual([chunk.sequence for chunk in window], [4, 5, 6])
        self.assertEqual([chunk.sequence for chunk in queue[:3]], [2, 3, 4])

    def test_status_copy_includes_capability_messages(self) -> None:
        class CapabilityMessage:
            def __init__(self) -> None:
                self.name = ""
                self.state = ""
                self.detail_code = ""
                self.active = False
                self.queued = 0
                self.last_update = SimpleNamespace(sec=0, nanosec=0)

        response = SimpleNamespace(
            last_error=SimpleNamespace(ok=False, state=0, error_code="", message="", recoverable=False),
            firmware_version="",
            capabilities=[],
        )
        status = StatusSnapshot(
            device_id="default",
            firmware_version="bridge-test",
            last_error=Result.accepted(""),
            capabilities=[
                CapabilitySnapshot(
                    "audio_playback",
                    "degraded",
                    detail_code="QUEUE_BACKPRESSURE",
                    active=True,
                    queued=2,
                    last_update=1778889601.25,
                )
            ],
        )

        _copy_status_with_type(response, status, CapabilityMessage)

        self.assertEqual(response.firmware_version, "bridge-test")
        self.assertEqual(response.capabilities[0].name, "audio_playback")
        self.assertEqual(response.capabilities[0].state, "degraded")
        self.assertEqual(response.capabilities[0].queued, 2)
        self.assertEqual(response.capabilities[0].last_update.sec, 1778889601)
        self.assertEqual(response.capabilities[0].last_update.nanosec, 250000000)

    def test_meta_falls_back_to_namespace_device_id(self) -> None:
        stamp = SimpleNamespace(sec=1778889601, nanosec=250000000)
        meta = SimpleNamespace(
            device_id="",
            command_id="cmd-test-0001",
            source="human_cli",
            created_at=stamp,
            priority=1,
        )

        converted = _meta_from_ros(meta, "desk")

        self.assertEqual(converted.device_id, "desk")
        self.assertEqual(converted.created_at, "1778889601.250000000")

    def test_meta_uses_namespace_device_id_over_caller_supplied_device_id(self) -> None:
        stamp = SimpleNamespace(sec=1778889601, nanosec=250000000)
        meta = SimpleNamespace(
            device_id="desk",
            command_id="cmd-test-0001",
            source="human_cli",
            created_at=stamp,
            priority=1,
        )

        converted = _meta_from_ros(meta, "default")

        self.assertEqual(converted.device_id, "default")

    def test_copy_command_meta_preserves_bridge_namespace_device_id(self) -> None:
        target = SimpleNamespace(created_at=None)
        stamp = SimpleNamespace(sec=1778889601, nanosec=250000000)
        meta = _meta_from_ros(
            SimpleNamespace(
                device_id="desk",
                command_id="cmd-test-0001",
                source="human_cli",
                created_at=stamp,
                priority=2,
            ),
            "default",
        )

        _copy_command_meta(target, meta, stamp)

        self.assertEqual(target.device_id, "default")
        self.assertEqual(target.command_id, "cmd-test-0001")
        self.assertEqual(target.source, "human_cli")
        self.assertIs(target.created_at, stamp)
        self.assertEqual(target.priority, 2)

    def test_safety_priority_rejection_helper_clears_result_response_payloads(self) -> None:
        meta = SimpleNamespace(device_id="default", command_id="cmd-test-0001", priority=3)
        response = SimpleNamespace(
            result=SimpleNamespace(ok=True, state=2, error_code="", message="", recoverable=False),
            events=[object()],
            cursor="evt-1",
            stale=True,
            transcript="private",
            confidence=1.0,
        )

        rejected = _reject_external_safety_priority(meta, response)

        self.assertTrue(rejected)
        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "INVALID_PRIORITY")
        self.assertEqual(response.events, [])
        self.assertEqual(response.cursor, "")
        self.assertFalse(response.stale)
        self.assertEqual(response.transcript, "")
        self.assertEqual(response.confidence, 0.0)

    def test_safety_priority_rejection_helper_handles_status_response_shape(self) -> None:
        meta = SimpleNamespace(device_id="default", command_id="cmd-test-0001", priority=3)
        response = SimpleNamespace(
            last_error=SimpleNamespace(ok=True, state=1, error_code="", message="", recoverable=False)
        )

        rejected = _reject_external_safety_priority(meta, response)

        self.assertTrue(rejected)
        self.assertFalse(response.last_error.ok)
        self.assertEqual(response.last_error.error_code, "INVALID_PRIORITY")

    def test_device_ids_are_normalized_for_node_resources_and_registry(self) -> None:
        self.assertEqual(
            _normalize_device_ids(["default", "desk", "desk", ""]),
            ["default", "desk"],
        )
        self.assertEqual(_normalize_device_ids("desk"), ["desk"])
        self.assertEqual(_normalize_device_ids([]), ["default"])

    def test_configured_records_can_start_disconnected_without_hardware(self) -> None:
        records = _configured_device_records(["default", "desk"], connected=False)

        self.assertEqual([record.device_id for record in records], ["default", "desk"])
        self.assertFalse(records[0].connected)
        self.assertFalse(records[1].connected)

    def test_firmware_event_marks_configured_device_available(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        event = SimpleNamespace(
            device_id="default",
            event_name="firmware_ready",
            source="firmware",
        )

        changed = _mark_device_available_from_event(registry, "default", event)

        self.assertTrue(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.AVAILABLE,
        )

    def test_firmware_event_liveness_rejects_device_id_mismatch(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        event = SimpleNamespace(
            device_id="desk",
            event_name="firmware_ready",
            source="firmware",
        )

        self.assertFalse(_event_matches_device_id("default", event))
        changed = _mark_device_available_from_event(registry, "default", event)

        self.assertFalse(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.DISCONNECTED,
        )

    def test_bridge_origin_events_do_not_mark_device_available(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        event = SimpleNamespace(
            device_id="default",
            event_name="device_connected",
            source="bridge",
        )

        changed = _mark_device_available_from_event(registry, "default", event)

        self.assertFalse(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.DISCONNECTED,
        )

    def test_firmware_status_marks_configured_device_available(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        status = SimpleNamespace(device_id="default", connected=True)

        changed = _mark_device_available_from_status(registry, "default", status)

        self.assertTrue(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.AVAILABLE,
        )

    def test_firmware_status_can_mark_available_device_disconnected(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=True)])
        status = SimpleNamespace(device_id="default", connected=False)

        changed = _mark_device_available_from_status(registry, "default", status)

        self.assertFalse(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.DISCONNECTED,
        )

    def test_firmware_status_liveness_rejects_device_id_mismatch(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        status = SimpleNamespace(device_id="desk", connected=True)

        self.assertFalse(_status_matches_device_id("default", status))
        changed = _mark_device_available_from_status(registry, "default", status)

        self.assertFalse(changed)
        self.assertEqual(
            registry.availability("default"),
            DeviceAvailability.DISCONNECTED,
        )

    def test_stackchan_status_snapshot_copies_liveness_fields(self) -> None:
        last_error = SimpleNamespace(
            ok=False,
            state=3,
            error_code="TRANSPORT_DISCONNECTED",
            message="lost heartbeat",
            recoverable=True,
        )
        capability = SimpleNamespace(
            name="face",
            state="available",
            detail_code="",
            active=True,
            queued=0,
            last_update=SimpleNamespace(sec=42, nanosec=250000000),
        )
        status = SimpleNamespace(
            device_id="",
            connected=False,
            state="degraded",
            face="neutral",
            motion="idle",
            last_command_id="cmd-1",
            last_error=last_error,
            firmware_version="bringup",
            capabilities=[capability],
        )

        snapshot = _snapshot_from_stackchan_status(status, fallback_device_id="default")

        self.assertEqual(snapshot.device_id, "default")
        self.assertFalse(snapshot.connected)
        self.assertEqual(snapshot.state, "degraded")
        self.assertEqual(snapshot.last_error.error_code, "TRANSPORT_DISCONNECTED")
        self.assertTrue(snapshot.last_error.recoverable)
        self.assertEqual(snapshot.capabilities[0].name, "face")
        self.assertEqual(snapshot.capabilities[0].last_update, 42.25)

    def test_event_record_copies_to_ros_shape_with_compact_payload(self) -> None:
        target = SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0))
        record = EventRecord(
            sequence=1,
            event_id="evt-0001",
            device_id="default",
            event_name="picked_up",
            source="firmware",
            stamp=1778889601.25,
            command_id="cmd-0001",
            payload={"utterance_id": "utt-1"},
        )

        _copy_event_record(target, record)

        self.assertEqual(target.event_id, "evt-0001")
        self.assertEqual(target.device_id, "default")
        self.assertEqual(target.event_name, "picked_up")
        self.assertEqual(target.source, "firmware")
        self.assertEqual(target.stamp.sec, 1778889601)
        self.assertEqual(target.stamp.nanosec, 250000000)
        self.assertEqual(target.command_id, "cmd-0001")
        self.assertEqual(target.payload_json, '{"utterance_id":"utt-1"}')

    def test_records_after_event_id_supports_since_and_unknown_replay(self) -> None:
        records = (
            EventRecord(1, "evt-1", "default", "one", 1.0),
            EventRecord(2, "evt-2", "default", "two", 2.0),
        )

        self.assertEqual(_records_after_event_id(records, "evt-1"), records[1:])
        self.assertEqual(_records_after_event_id(records, "missing"), records)
        self.assertEqual(_sequence_for_event_id(records, "evt-1"), 1)
        self.assertIsNone(_sequence_for_event_id(records, "missing"))

    def test_bridge_node_source_wires_event_services_and_topics(self) -> None:
        source = (ROOT / "stackchan_bridge" / "ros_node.py").read_text()

        for name in (
            "ListEvents",
            "NextEvent",
            "NextAudioChunk",
            "ClearEventCursor",
            "GetTranscript",
            "GetPowerStatus",
            "GetHeadPose",
            "SetHeadPose",
            "TouchState",
            "HeadPose",
            "ImuRaw",
            "ProximityRaw",
            "LightRaw",
            "PowerStatus",
            "StackChanEvent",
            "StackChanStatus",
            "LoadAudioChunk",
            "EVENT_QOS_DEPTH = 32",
            "DEFAULT_LIVENESS_TIMEOUT_SEC = 3.5",
            "device_command_timeout_sec",
            "device_media_action_timeout_sec",
            'self.declare_parameter("device_media_action_timeout_sec", 35.0)',
            'self.declare_parameter(\n                "tts_speed_scale",',
            "STACKCHAN_TTS_SPEED_SCALE",
            "STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD",
            "MultiThreadedExecutor",
            "ReentrantCallbackGroup",
            "ActionClient",
            "reliable_depth_4 = QoSProfile(depth=4)",
            "reliable_depth_8 = QoSProfile(depth=8)",
            "AUDIO_PLAYBACK_FIRST_CHUNK_RETRY_COUNT = 3",
            "AUDIO_PLAYBACK_FIRST_CHUNK_RETRY_INTERVAL_SEC = 0.03",
            "AUDIO_PLAYBACK_SUBSCRIPTION_MATCH_TIMEOUT_SEC = 1.5",
            "AUDIO_PLAYBACK_INPUT_IDLE_EOS_SEC = 0.35",
            "AUDIO_PLAYBACK_BUFFERED_PUBLISH_INTERVAL_SEC = 0.15",
            "AUDIO_PLAYBACK_TOPIC_CHUNK_RETRY_COUNT = 1",
            "AUDIO_PLAYBACK_PULL_REPUBLISH_RETRY_COUNT = 3",
            "AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS = 2",
            "AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS = 8",
            "AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS = 8",
            "_publish_device_audio_chunk_with_retries",
            "_republish_device_audio_chunk_for_pull",
            "_select_playback_chunks_for_topic_window",
            "AUDIO_PLAYBACK_FIRST_GOAL_BYTES_DEFAULT = 64",
            "AUDIO_PLAYBACK_CHUNK_BYTES_DEFAULT = 160",
            "STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES",
            "STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES",
            "STACKCHAN_AUDIO_PLAYBACK_PULL_ONLY",
            "STACKCHAN_TTS_LOADED_PLAYBACK",
            "_audio_playback_pull_only",
            "_audio_playback_loaded_tts",
            "_wait_for_device_audio_playback_subscription",
            "audio playback relay subscription match",
            "action_status_best_effort_depth_1",
            "feedback_sub_qos_profile=action_status_best_effort_depth_1",
            "status_sub_qos_profile=action_status_best_effort_depth_1",
            "_copy_compressed_image_payload",
            "_make_camera_capture_failed_result",
            "_mark_device_available_from_event(",
            "_mark_device_available_from_status(",
            "_device_audio_capture_clients",
            "_device_audio_load_clients",
            "_device_audio_play_clients",
            "_device_audio_chunk_publishers",
            "_cmd_audio_chunk_subscriptions",
            "_pending_playback_chunks",
            "_handle_next_audio_chunk",
            "/audio/playback/next_chunk",
            "audio playback pull served first chunk",
            "_active_playback_sessions",
            "_closed_playback_sessions",
            "_pull_only_playback_sessions",
            "_prebuffered_topic_playback_sessions",
            "input_drained = prebuffered_topic",
            'close_reason = "drained" if input_drained else "idle"',
            "pull_only = key in self._pull_only_playback_sessions",
            "audio playback pull republished chunk on topic",
            "lookahead=",
            "audio playback pull served fallback chunk",
            "_republish_device_audio_chunk_for_pull_async",
            "_playback_relay_stats",
            "pull_nack_counts",
            "last_received_monotonic",
            "activated_monotonic",
            "audio playback pull closed input",
            "_playback_chunk_lock",
            "_audio_chunk_pcm_size",
            "_device_camera_capture_clients",
            "_device_face_clients",
            "_device_led_clients",
            "_device_head_pose_clients",
            "_device_motion_clients",
            "_call_device_face_set",
            "_set_led_type = SetLed",
            "_call_device_audio_capture",
            "_call_device_audio_play",
            "_load_device_audio_playback",
            "audio playback load service unavailable; falling back to topic relay",
            "audio playback loaded before play action",
            "goal.first_chunk_present",
            "goal.first_chunk_sequence",
            "goal.first_chunk_pcm = bytes",
            "next_chunk_sequence",
            "next_chunk_offset",
            "_handle_cmd_audio_chunk",
            "_activate_playback_chunk_relay",
            "_finish_playback_chunk_relay",
            "_publish_device_audio_chunk",
            "audio playback relay buffered first chunk",
            "audio playback relay activated",
            "audio playback relay topic start",
            "pull_only=_audio_playback_pull_only()",
            "audio playback relay published first chunk",
            "audio playback relay finished",
            "_call_device_camera_capture",
            "_send_device_camera_capture_goal",
            "_call_device_led_set",
            "_call_device_head_pose",
            "_call_device_motion_run",
            "_send_device_action_goal",
            "timeout_sec=self._device_media_action_timeout_sec",
            "(goal.duration_ms / 1000.0) + 2.0",
            "/events/list",
            "/events/next",
            "/events/clear_cursor",
            "/speech/transcript/get",
            "/power/status",
            "/motion/status",
            "/motion/pose",
            "imu/raw",
            "/status",
            "/events",
            "/device/events",
            "/device/status",
            "/device/audio/capture",
            "/device/audio/play",
            "/device/audio/playback/load",
            "/device/audio/playback/chunks",
            "/cmd/audio/chunks",
            "/device/camera/capture",
            "/device/face/set",
            "/device/led/set",
            "/device/motion/pose/set",
            "/device/motion/run",
            "device/{tail}",
        ):
            self.assertIn(name, source)

        self.assertIn(
            "record = self.event_aggregator.add(\n                device_id,",
            source,
        )

    def test_power_status_helpers_copy_ros_like_shapes(self) -> None:
        message = type(
            "Power",
            (),
            {
                "device_id": "",
                "stamp": type("Stamp", (), {"sec": 1778889601, "nanosec": 0})(),
                "voltage_v": 4.9,
                "current_ma": 180.0,
                "power_mw": 882.0,
                "percentage": float("nan"),
                "power_source": 2,
                "charging": True,
                "powered": True,
                "low_battery": False,
                "brownout_risk": False,
                "fault_code": "",
            },
        )()

        snapshot = _snapshot_from_power_status(message, fallback_device_id="default")

        self.assertEqual(snapshot.device_id, "default")
        self.assertEqual(snapshot.power_source, 2)

        target = type("Target", (), {"stamp": type("Stamp", (), {"sec": 0, "nanosec": 0})()})()
        _copy_power_status(target, PowerStatusSnapshot("desk", voltage_v=3.7, stamp=1.5))

        self.assertEqual(target.device_id, "desk")
        self.assertEqual(target.voltage_v, 3.7)
        self.assertEqual(target.stamp.sec, 1)
        self.assertEqual(target.stamp.nanosec, 500000000)

    def test_head_pose_helpers_copy_ros_like_shapes(self) -> None:
        message = type(
            "Pose",
            (),
            {
                "device_id": "",
                "stamp": type("Stamp", (), {"sec": 1778889601, "nanosec": 0})(),
                "pan_deg": 30.0,
                "tilt_deg": 20.0,
                "moving": True,
                "frame": "home",
            },
        )()

        snapshot = _snapshot_from_head_pose(message, fallback_device_id="default")

        self.assertEqual(snapshot.device_id, "default")
        self.assertEqual(snapshot.pan_deg, 30.0)
        self.assertTrue(snapshot.moving)

        target = type("Target", (), {"stamp": type("Stamp", (), {"sec": 0, "nanosec": 0})()})()
        _copy_head_pose(target, HeadPoseSnapshot("desk", pan_deg=5.0, tilt_deg=6.0, stamp=1.5))

        self.assertEqual(target.device_id, "desk")
        self.assertEqual(target.pan_deg, 5.0)
        self.assertEqual(target.tilt_deg, 6.0)
        self.assertEqual(target.frame, "home")

    def test_telemetry_device_id_is_filled_but_mismatch_is_rejected(self) -> None:
        missing = SimpleNamespace(device_id="")
        self.assertTrue(_coerce_telemetry_device_id(missing, "default"))
        self.assertEqual(missing.device_id, "default")

        matching = SimpleNamespace(device_id="default")
        self.assertTrue(_coerce_telemetry_device_id(matching, "default"))
        self.assertEqual(matching.device_id, "default")

        mismatched = SimpleNamespace(device_id="desk")
        self.assertFalse(_coerce_telemetry_device_id(mismatched, "default"))
        self.assertEqual(mismatched.device_id, "desk")

    def test_power_telemetry_relay_fills_device_id_stores_and_publishes(self) -> None:
        class Publisher:
            def __init__(self) -> None:
                self.messages = []

            def publish(self, message) -> None:
                self.messages.append(message)

        message = SimpleNamespace(
            device_id="",
            stamp=SimpleNamespace(sec=12, nanosec=0),
            voltage_v=4.9,
            current_ma=180.0,
            power_mw=882.0,
            percentage=float("nan"),
            power_source=2,
            charging=True,
            powered=True,
            low_battery=False,
            brownout_risk=False,
            fault_code="",
        )
        publisher = Publisher()
        store = type("Store", (), {"snapshots": [], "update": lambda self, snapshot: self.snapshots.append(snapshot)})()

        relayed = _relay_telemetry_message(
            "default",
            "power/status",
            message,
            publisher,
            power_store=store,
        )

        self.assertTrue(relayed)
        self.assertEqual(message.device_id, "default")
        self.assertEqual(publisher.messages, [message])
        self.assertEqual(store.snapshots[0].device_id, "default")

    def test_head_pose_relay_fills_device_id_stores_and_publishes(self) -> None:
        class Publisher:
            def __init__(self) -> None:
                self.messages = []

            def publish(self, message) -> None:
                self.messages.append(message)

        message = SimpleNamespace(
            device_id="",
            stamp=SimpleNamespace(sec=12, nanosec=0),
            pan_deg=30.0,
            tilt_deg=20.0,
            moving=False,
            frame="home",
        )
        publisher = Publisher()
        store = type("Store", (), {"snapshots": [], "update": lambda self, snapshot: self.snapshots.append(snapshot)})()

        relayed = _relay_telemetry_message(
            "default",
            "motion/pose",
            message,
            publisher,
            head_pose_store=store,
        )

        self.assertTrue(relayed)
        self.assertEqual(message.device_id, "default")
        self.assertEqual(publisher.messages, [message])
        self.assertEqual(store.snapshots[0].pan_deg, 30.0)

    def test_telemetry_relay_drops_device_id_mismatch(self) -> None:
        class Publisher:
            def publish(self, message) -> None:
                raise AssertionError(f"unexpected publish: {message}")

        conflicts = []
        message = SimpleNamespace(device_id="desk")

        relayed = _relay_telemetry_message(
            "default",
            "touch/state",
            message,
            Publisher(),
            conflict_handler=lambda device_id, tail, msg: conflicts.append((device_id, tail, msg.device_id)),
        )

        self.assertFalse(relayed)
        self.assertEqual(conflicts, [("default", "touch/state", "desk")])


if __name__ == "__main__":
    unittest.main()
