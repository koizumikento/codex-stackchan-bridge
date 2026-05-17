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


if __name__ == "__main__":
    unittest.main()
