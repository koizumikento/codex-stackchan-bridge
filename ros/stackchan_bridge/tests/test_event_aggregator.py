from __future__ import annotations

import unittest

from stackchan_bridge.event_aggregator import (
    EventAggregator,
    normalize_event_name,
    normalize_payload,
)
from stackchan_bridge.event_buffer import EventBuffer
from stackchan_bridge.redaction import REDACTED


class MutableClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class EventAggregatorTests(unittest.TestCase):
    def test_normalizes_event_name(self) -> None:
        self.assertEqual(normalize_event_name(" NFC Detected "), "nfc_detected")
        self.assertEqual(normalize_event_name("camera failed"), "camera_capture_failed")
        self.assertEqual(normalize_event_name(""), "unknown")

    def test_normalizes_and_redacts_payload(self) -> None:
        payload = normalize_payload('{"speech_text": "hello", "level": 3}')

        self.assertEqual(payload["speech_text"], REDACTED)
        self.assertEqual(payload["level"], 3)

    def test_normalizes_and_redacts_ir_remote_payload(self) -> None:
        payload = normalize_payload(
            '{"raw_ir_code": "0xDEADBEEF", "protocol_dump": "NEC raw", "nfc_tag_id": "04AABB"}'
        )

        self.assertEqual(payload["raw_ir_code"], REDACTED)
        self.assertEqual(payload["protocol_dump"], REDACTED)
        self.assertEqual(payload["nfc_tag_id"], REDACTED)

    def test_invalid_payload_json_is_not_republished_raw(self) -> None:
        payload = normalize_payload("raw_ir_code=0xDEADBEEF tag_id=04AABB")

        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["reason"], "payload_json_invalid")
        self.assertNotIn("0xDEADBEEF", str(payload))
        self.assertNotIn("04AABB", str(payload))

    def test_non_object_payload_json_is_not_republished_raw(self) -> None:
        for raw_payload in (
            '"raw_ir_code=0xDEADBEEF tag_id=04AABB"',
            '["raw_ir_code=0xDEADBEEF", "tag_id=04AABB"]',
        ):
            with self.subTest(raw_payload=raw_payload):
                payload = normalize_payload(raw_payload)

                self.assertTrue(payload["truncated"])
                self.assertEqual(payload["reason"], "payload_json_invalid")
                self.assertNotIn("0xDEADBEEF", str(payload))
                self.assertNotIn("04AABB", str(payload))

    def test_debounces_duplicate_events_per_device(self) -> None:
        clock = MutableClock(100.0)
        buffer = EventBuffer(clock=clock)
        aggregator = EventAggregator(buffer, debounce_seconds=1.0, clock=clock)

        first = aggregator.add("default", "picked up", payload={"level": 1})
        duplicate = aggregator.add("default", "picked_up", payload={"level": 1})
        other_device = aggregator.add("desk", "picked_up", payload={"level": 1})

        clock.now = 101.0
        after_window = aggregator.add("default", "picked_up", payload={"level": 1})

        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)
        self.assertIsNotNone(other_device)
        self.assertIsNotNone(after_window)
        self.assertEqual(
            [record.event_name for record in buffer.records("default")],
            ["picked_up", "picked_up"],
        )
        self.assertEqual(len(buffer.records("desk")), 1)

    def test_debounce_fingerprints_expire_and_are_bounded(self) -> None:
        clock = MutableClock(100.0)
        aggregator = EventAggregator(
            EventBuffer(clock=clock),
            debounce_seconds=1.0,
            max_debounce_entries=2,
            clock=clock,
        )

        aggregator.add("default", "picked_up", payload={"index": 1})
        aggregator.add("default", "picked_up", payload={"index": 2})
        aggregator.add("default", "picked_up", payload={"index": 3})

        self.assertLessEqual(len(aggregator._last_emit), 2)

        clock.now = 101.0
        aggregator.add("default", "picked_up", payload={"index": 4})

        self.assertEqual(len(aggregator._last_emit), 1)


if __name__ == "__main__":
    unittest.main()
