from __future__ import annotations

import unittest
from types import SimpleNamespace

from stackchan_bridge.ros_node import _meta_from_ros, _normalize_device_ids


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


if __name__ == "__main__":
    unittest.main()
