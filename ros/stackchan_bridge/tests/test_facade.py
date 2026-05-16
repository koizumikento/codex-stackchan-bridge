from __future__ import annotations

import unittest

from stackchan_bridge.facade import StackChanBridgeFacade
from stackchan_bridge.models import (
    PRIORITY_NORMAL,
    PRIORITY_SAFETY,
    STATE_ACCEPTED,
    CommandMeta,
)
from stackchan_bridge.registry import DeviceRecord, DeviceRegistry


class NullLogger:
    def log(self, *_args: object, **_kwargs: object) -> None:
        return None


def facade(registry: DeviceRegistry | None = None) -> StackChanBridgeFacade:
    return StackChanBridgeFacade(registry=registry, logger=NullLogger())


def meta(device_id: str = "default", priority: int = PRIORITY_NORMAL) -> CommandMeta:
    return CommandMeta(
        device_id=device_id,
        command_id="cmd-test-0001",
        source="human_cli",
        priority=priority,
    )


class FacadeTests(unittest.TestCase):
    def test_default_status_is_connected(self) -> None:
        status = facade().get_status("default").status

        self.assertTrue(status.connected)
        self.assertEqual(status.device_id, "default")
        self.assertEqual(status.face, "neutral")
        self.assertEqual(status.last_error.state, STATE_ACCEPTED)

    def test_face_set_records_command_id_and_face(self) -> None:
        bridge = facade()

        response = bridge.set_face(meta(), "happy")
        status = bridge.get_status("default").status

        self.assertTrue(response.result.ok)
        self.assertEqual(response.command_id, "cmd-test-0001")
        self.assertEqual(status.face, "happy")
        self.assertEqual(status.last_command_id, "cmd-test-0001")

    def test_led_set_accepts_known_pattern(self) -> None:
        response = facade().set_led(meta(), "progress")

        self.assertTrue(response.result.ok)
        self.assertEqual(response.device_id, "default")

    def test_motion_accepts_nod_and_idle(self) -> None:
        bridge = facade()

        nod = bridge.run_motion(meta(), "nod")
        idle = bridge.run_motion(meta(), "idle")

        self.assertTrue(nod.result.ok)
        self.assertTrue(idle.result.ok)
        self.assertEqual(bridge.get_status("default").status.motion, "idle")

    def test_unknown_device_returns_device_not_found(self) -> None:
        response = facade().set_face(meta("desk"), "happy")

        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "DEVICE_NOT_FOUND")
        self.assertEqual(response.device_id, "desk")

    def test_disconnected_configured_device_returns_transport_disconnected(self) -> None:
        bridge = facade(
            DeviceRegistry([DeviceRecord("default", connected=False)])
        )

        response = bridge.set_led(meta(), "progress")

        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "TRANSPORT_DISCONNECTED")
        self.assertTrue(response.result.recoverable)

    def test_safety_priority_from_cli_is_rejected(self) -> None:
        response = facade().run_motion(meta(priority=PRIORITY_SAFETY), "nod")

        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "INVALID_PRIORITY")


if __name__ == "__main__":
    unittest.main()
