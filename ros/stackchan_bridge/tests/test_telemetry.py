from __future__ import annotations

import unittest

from stackchan_bridge.telemetry import (
    PowerStatusSnapshot,
    PowerTelemetryStore,
    device_topic_for,
    public_topic_for,
)


class MutableClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class TelemetryTests(unittest.TestCase):
    def test_power_status_store_reports_stale_state(self) -> None:
        clock = MutableClock(100.0)
        store = PowerTelemetryStore(stale_after_seconds=5.0, clock=clock)
        snapshot = PowerStatusSnapshot(
            device_id="default",
            voltage_v=4.9,
            current_ma=180.0,
            power_mw=882.0,
            power_source=2,
            charging=True,
            powered=True,
            stamp=100.0,
        )

        store.update(snapshot)
        self.assertEqual(store.get("default"), (snapshot, False))

        clock.now = 106.0
        self.assertEqual(store.get("default"), (snapshot, True))

    def test_power_status_store_uses_host_receipt_time_not_device_stamp(self) -> None:
        clock = MutableClock(100.0)
        store = PowerTelemetryStore(stale_after_seconds=5.0, clock=clock)
        snapshot = PowerStatusSnapshot(device_id="default", voltage_v=4.9, stamp=12.0)

        store.update(snapshot)

        self.assertEqual(store.get("default"), (snapshot, False))

    def test_power_source_names_are_stable(self) -> None:
        self.assertEqual(PowerStatusSnapshot("default", power_source=1).power_source_name, "battery")
        self.assertEqual(PowerStatusSnapshot("default", power_source=2).power_source_name, "usb")
        self.assertEqual(PowerStatusSnapshot("default", power_source=99).power_source_name, "unknown")

    def test_topic_helpers_preserve_device_id(self) -> None:
        self.assertEqual(public_topic_for("desk", "power/status"), "/stackchan/desk/power/status")
        self.assertEqual(device_topic_for("desk", "power/status"), "/stackchan/desk/device/power/status")


if __name__ == "__main__":
    unittest.main()
