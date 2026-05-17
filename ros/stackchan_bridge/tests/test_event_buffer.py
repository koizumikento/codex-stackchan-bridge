from __future__ import annotations

import unittest

from stackchan_bridge.event_buffer import EventBuffer


class EventBufferTests(unittest.TestCase):
    def test_records_keep_order_and_ring_limit(self) -> None:
        buffer = EventBuffer(maxlen=2, clock=lambda: 1.0)

        first = buffer.append("default", "picked_up")
        second = buffer.append("default", "shaken")
        third = buffer.append("default", "tilted")

        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.sequence, 2)
        self.assertEqual(third.sequence, 3)
        self.assertEqual(
            [record.event_name for record in buffer.records("default")],
            ["shaken", "tilted"],
        )

    def test_consumer_cursor_advances_and_clear_preserves_buffer(self) -> None:
        buffer = EventBuffer(maxlen=4, clock=lambda: 1.0)
        buffer.append("default", "picked_up")
        buffer.append("default", "shaken")

        first_read = buffer.read("default", "observer")
        second_read = buffer.read("default", "observer")

        self.assertEqual([record.event_name for record in first_read], ["picked_up", "shaken"])
        self.assertEqual(second_read, ())
        self.assertEqual(buffer.cursor_sequence("observer", "default"), 2)

        buffer.clear_cursor("observer", "default")

        replayed = buffer.read("default", "observer")

        self.assertEqual(
            [record.event_name for record in replayed],
            ["picked_up", "shaken"],
        )
        self.assertEqual(len(buffer.records("default")), 2)

    def test_consumer_cursor_limit_advances_to_last_delivered(self) -> None:
        buffer = EventBuffer(maxlen=4, clock=lambda: 1.0)
        buffer.append("default", "one")
        buffer.append("default", "two")
        buffer.append("default", "three")

        limited = buffer.read("default", "observer", limit=2)

        self.assertEqual([record.event_name for record in limited], ["one", "two"])
        self.assertEqual(buffer.cursor_sequence("observer", "default"), 2)
        self.assertEqual(
            [record.event_name for record in buffer.read("default", "observer")],
            ["three"],
        )

    def test_after_sequence_read_advances_consumer_cursor(self) -> None:
        buffer = EventBuffer(maxlen=4, clock=lambda: 1.0)
        buffer.append("default", "one")
        buffer.append("default", "two")
        buffer.append("default", "three")

        after_read = buffer.read("default", "observer", limit=1, after_sequence=1)

        self.assertEqual([record.event_name for record in after_read], ["two"])
        self.assertEqual(buffer.cursor_sequence("observer", "default"), 2)
        self.assertEqual(
            [record.event_name for record in buffer.read("default", "observer")],
            ["three"],
        )

    def test_events_and_cursors_are_separated_per_device(self) -> None:
        buffer = EventBuffer(maxlen=4, clock=lambda: 1.0)
        buffer.append("default", "picked_up")
        buffer.append("desk", "nfc_detected")

        self.assertEqual(
            [record.event_name for record in buffer.read("default", "observer")],
            ["picked_up"],
        )
        self.assertEqual(
            [record.event_name for record in buffer.read("desk", "observer")],
            ["nfc_detected"],
        )
        self.assertEqual(buffer.cursor_sequence("observer", "default"), 1)
        self.assertEqual(buffer.cursor_sequence("observer", "desk"), 2)

    def test_event_fields_are_bounded_to_ros_contract(self) -> None:
        buffer = EventBuffer(maxlen=4, clock=lambda: 1.0)

        record = buffer.append(
            "d" * 40,
            "e" * 40,
            event_id="i" * 40,
            source="s" * 40,
            command_id="c" * 40,
            payload={"value": "x" * 300},
        )

        self.assertEqual(len(record.event_id), 36)
        self.assertEqual(len(record.device_id), 32)
        self.assertEqual(len(record.event_name), 32)
        self.assertEqual(len(record.source), 32)
        self.assertEqual(len(record.command_id), 36)
        self.assertEqual(
            record.payload,
            {"truncated": True, "reason": "payload_json_exceeds_256_bytes"},
        )

    def test_duplicate_incoming_event_id_gets_bridge_unique_id(self) -> None:
        buffer = EventBuffer(maxlen=4, clock=lambda: 1.0)

        first = buffer.append("default", "picked_up", event_id="firmware-reused")
        second = buffer.append("default", "shaken", event_id="firmware-reused")

        self.assertEqual(first.event_id, "firmware-reused")
        self.assertEqual(second.event_id, "evt-00000002")

    def test_duplicate_incoming_event_id_cannot_collide_with_fallback_id(self) -> None:
        buffer = EventBuffer(maxlen=4, clock=lambda: 1.0)

        first = buffer.append("default", "picked_up", event_id="evt-00000002")
        second = buffer.append("default", "shaken", event_id="evt-00000002")

        self.assertEqual(first.event_id, "evt-00000002")
        self.assertEqual(second.event_id, "evt-00000003")

    def test_consumer_cursors_are_bounded_and_expire(self) -> None:
        now = 10.0
        buffer = EventBuffer(
            maxlen=4,
            max_cursors=2,
            cursor_ttl_seconds=5.0,
            clock=lambda: now,
        )
        buffer.append("default", "one")

        buffer.read("default", "first")
        buffer.read("default", "second")
        buffer.read("default", "third")

        self.assertIsNone(buffer.cursor_sequence("first", "default"))
        self.assertEqual(buffer.cursor_sequence("second", "default"), 1)
        self.assertEqual(buffer.cursor_sequence("third", "default"), 1)

        now = 16.0
        buffer.append("default", "two")
        buffer.read("default", "fourth")

        self.assertIsNone(buffer.cursor_sequence("second", "default"))
        self.assertIsNone(buffer.cursor_sequence("third", "default"))
        self.assertEqual(buffer.cursor_sequence("fourth", "default"), 2)


if __name__ == "__main__":
    unittest.main()
