from __future__ import annotations

import unittest
import math

from stackchan_bridge.facade import StackChanBridgeFacade
from stackchan_bridge.models import (
    PRIORITY_NORMAL,
    PRIORITY_SAFETY,
    STATE_ACCEPTED,
    STATE_COMPLETED,
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
        created_at="2026-05-16T00:00:00Z",
        priority=priority,
    )


class FacadeTests(unittest.TestCase):
    def test_default_status_is_connected(self) -> None:
        status = facade().get_status("default").status

        self.assertTrue(status.connected)
        self.assertEqual(status.device_id, "default")
        self.assertEqual(status.face, "neutral")
        self.assertEqual(status.last_error.state, STATE_ACCEPTED)
        capabilities = {capability.name: capability for capability in status.capabilities}
        self.assertEqual(capabilities["face"].state, "available")
        self.assertEqual(capabilities["motion"].state, "available")
        self.assertEqual(capabilities["camera_snapshot"].state, "unavailable")
        self.assertEqual(capabilities["camera_snapshot"].detail_code, "UNSUPPORTED_FEATURE")

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
        self.assertEqual(nod.result.state, STATE_COMPLETED)
        self.assertTrue(idle.result.ok)
        self.assertEqual(bridge.get_status("default").status.motion, "idle")

    def test_unknown_face_led_and_motion_are_rejected(self) -> None:
        bridge = facade()

        face = bridge.set_face(meta(), "wink")
        led = bridge.set_led(meta(), "rainbow")
        motion = bridge.run_motion(meta(), "spin")

        for response in (face, led, motion):
            self.assertFalse(response.result.ok)
            self.assertEqual(response.result.error_code, "UNKNOWN_COMMAND")
            self.assertFalse(response.result.recoverable)

    def test_availability_and_safety_priority_precede_unknown_command_validation(self) -> None:
        bridge = facade()

        missing = bridge.set_face(meta("desk"), "wink")
        safety = bridge.run_motion(meta(priority=PRIORITY_SAFETY), "spin")

        self.assertEqual(missing.result.error_code, "DEVICE_NOT_FOUND")
        self.assertEqual(safety.result.error_code, "INVALID_PRIORITY")

    def test_head_pose_validates_and_accepts_for_firmware_routing(self) -> None:
        bridge = facade()

        response = bridge.move_head_pose(meta(), 30.0, 20.0, 500, 0)

        self.assertTrue(response.result.ok)
        self.assertEqual(response.result.state, STATE_ACCEPTED)
        self.assertNotEqual(bridge.get_status("default").status.motion, "pose")

    def test_head_pose_rejects_out_of_range_without_clamping(self) -> None:
        response = facade().move_head_pose(meta(), 129.0, 20.0, 500, 0)

        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "SERVO_LIMIT_EXCEEDED")
        self.assertTrue(response.result.recoverable)

    def test_head_pose_rejects_non_finite_angles(self) -> None:
        response = facade().move_head_pose(meta(), math.nan, 20.0, 500, 0)

        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "SERVO_LIMIT_EXCEEDED")

    def test_head_home_validates_and_accepts_for_firmware_routing(self) -> None:
        bridge = facade()

        response = bridge.home_head_pose(meta(), 500, 0)

        self.assertTrue(response.result.ok)
        self.assertEqual(response.result.state, STATE_ACCEPTED)
        self.assertNotEqual(bridge.get_status("default").status.motion, "home")

    def test_say_accepts_without_claiming_completion(self) -> None:
        bridge = facade()

        self.assertEqual(bridge.say(meta(), "hello").result.state, STATE_ACCEPTED)

    def test_media_actions_remain_unsupported_until_firmware_confirmed_transport_exists(self) -> None:
        bridge = facade()

        self.assertEqual(bridge.play_audio(meta()).result.error_code, "UNSUPPORTED_FEATURE")
        self.assertEqual(
            bridge.capture_audio(meta(), duration_ms=1000).result.error_code,
            "UNSUPPORTED_FEATURE",
        )
        self.assertEqual(
            bridge.capture_camera(meta(), quality=80).result.error_code,
            "UNSUPPORTED_FEATURE",
        )

    def test_media_actions_reject_outside_baseline_without_payloads(self) -> None:
        bridge = facade()

        self.assertEqual(
            bridge.play_audio(meta(), format="mp3").result.error_code,
            "AUDIO_FORMAT_UNSUPPORTED",
        )
        self.assertEqual(
            bridge.capture_audio(meta(), duration_ms=0).result.error_code,
            "AUDIO_CAPTURE_FAILED",
        )
        self.assertEqual(
            bridge.capture_camera(meta(), width=640, height=480).result.error_code,
            "CAMERA_CAPTURE_FAILED",
        )

    def test_unknown_device_returns_device_not_found(self) -> None:
        response = facade().set_face(meta("desk"), "happy")

        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "DEVICE_NOT_FOUND")
        self.assertEqual(response.device_id, "desk")

    def test_configured_non_default_device_accepts_commands(self) -> None:
        bridge = facade(
            DeviceRegistry([DeviceRecord("default"), DeviceRecord("desk")])
        )

        response = bridge.set_face(meta("desk"), "happy")

        self.assertTrue(response.result.ok)
        self.assertEqual(response.device_id, "desk")
        self.assertTrue(bridge.get_status("desk").status.connected)

    def test_disconnected_configured_device_returns_transport_disconnected(self) -> None:
        registry = DeviceRegistry([DeviceRecord("default", connected=False)])
        bridge = facade(registry)

        response = bridge.set_led(meta(), "progress")

        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "TRANSPORT_DISCONNECTED")
        self.assertTrue(response.result.recoverable)

        registry.set_connected("default", True)
        status = bridge.get_status("default").status

        self.assertTrue(status.connected)
        self.assertEqual(status.last_error.error_code, "")

    def test_safety_priority_from_cli_is_rejected(self) -> None:
        bridge = facade()

        response = bridge.run_motion(meta(priority=PRIORITY_SAFETY), "nod")
        status = bridge.get_status("default").status

        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "INVALID_PRIORITY")
        self.assertTrue(status.connected)

    def test_safety_priority_is_rejected_even_when_source_is_spoofed(self) -> None:
        bridge = facade()
        spoofed = CommandMeta(
            device_id="default",
            command_id="cmd-test-0001",
            source="bridge",
            created_at="2026-05-16T00:00:00Z",
            priority=PRIORITY_SAFETY,
        )

        response = bridge.set_led(spoofed, "progress")

        self.assertFalse(response.result.ok)
        self.assertEqual(response.result.error_code, "INVALID_PRIORITY")


if __name__ == "__main__":
    unittest.main()
