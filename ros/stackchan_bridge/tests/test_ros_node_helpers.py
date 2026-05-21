from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from stackchan_bridge.event_buffer import EventRecord
from stackchan_bridge.ros_node import (
    _coerce_telemetry_device_id,
    _copy_power_status,
    _copy_head_pose,
    _copy_status_with_type,
    _copy_event_record,
    _configured_device_records,
    _snapshot_from_power_status,
    _snapshot_from_head_pose,
    _records_after_event_id,
    _sequence_for_event_id,
    _meta_from_ros,
    _normalize_device_ids,
    _reject_external_safety_priority,
    _relay_telemetry_message,
)
from stackchan_bridge.models import CapabilitySnapshot, Result, StatusSnapshot
from stackchan_bridge.telemetry import HeadPoseSnapshot, PowerStatusSnapshot


ROOT = Path(__file__).resolve().parents[1]


class RosNodeHelperTests(unittest.TestCase):
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
            "ClearEventCursor",
            "GetTranscript",
            "GetPowerStatus",
            "GetHeadPose",
            "TouchState",
            "HeadPose",
            "ProximityRaw",
            "LightRaw",
            "PowerStatus",
            "StackChanEvent",
            "EVENT_QOS_DEPTH = 32",
            "reliable_depth_4 = QoSProfile(depth=4)",
            "/events/list",
            "/events/next",
            "/events/clear_cursor",
            "/speech/transcript/get",
            "/power/status",
            "/motion/status",
            "/motion/pose",
            "/events",
            "/device/events",
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
