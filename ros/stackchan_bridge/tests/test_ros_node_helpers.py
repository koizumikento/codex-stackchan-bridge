from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from stackchan_bridge.event_buffer import EventRecord
from stackchan_bridge.ros_node import (
    _copy_event_record,
    _configured_device_records,
    _records_after_event_id,
    _meta_from_ros,
    _normalize_device_ids,
    _transcript_from_event_payload,
)


ROOT = Path(__file__).resolve().parents[1]


class RosNodeHelperTests(unittest.TestCase):
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

    def test_transcript_ready_payload_extracts_utterance_and_text(self) -> None:
        decoded = _transcript_from_event_payload(
            '{"utterance_id":"utt-1","transcript":"hello"}'
        )

        self.assertEqual(decoded, ("utt-1", "hello"))
        self.assertIsNone(_transcript_from_event_payload('{"utterance_id":"utt-1"}'))

    def test_bridge_node_source_wires_event_services_and_topics(self) -> None:
        source = (ROOT / "stackchan_bridge" / "ros_node.py").read_text()

        for name in (
            "ListEvents",
            "NextEvent",
            "ClearEventCursor",
            "GetTranscript",
            "StackChanEvent",
            "/events/list",
            "/events/next",
            "/events/clear_cursor",
            "/speech/transcript/get",
            "/events",
            "/device/events",
        ):
            self.assertIn(name, source)

        self.assertIn(
            "record = self.event_aggregator.add(\n                device_id,",
            source,
        )


if __name__ == "__main__":
    unittest.main()
