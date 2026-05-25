from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import wave
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stackchanctl.backends.bridge import (  # noqa: E402
    BridgeBackend,
    BridgeBackendError,
    BridgeBackendTimeout,
    BridgeCommandResponse,
    RclpyBridgeClient,
    _copy_created_at,
    _normalize_action_response,
    _payload_from_json,
    _power_status_from_ros,
    _read_audio_playback_pcm,
)
from stackchanctl.backends import bridge as bridge_module  # noqa: E402
from stackchanctl.cli import run_cli  # noqa: E402
from stackchanctl.contract import (  # noqa: E402
    CapabilityStatus,
    DeviceStatus,
    ErrorDetail,
    EventListResult,
    PowerStatusResult,
    ResultState,
    TranscriptResult,
)


FIXED_NOW = datetime(2026, 5, 16, 0, 0, tzinfo=UTC)


class FakeBridgeClient:
    def __init__(self, *, timeout: bool = False) -> None:
        self.timeout = timeout
        self.get_status_args = None
        self.list_events_args = None
        self.next_event_args = None
        self.clear_events_args = None
        self.power_status_args = None
        self.move_head_pose_args = None
        self.home_head_pose_args = None
        self.say_args = None
        self.play_audio_args = None
        self.capture_audio_args = None
        self.capture_camera_args = None

    def get_status(self, meta, timeout: float) -> DeviceStatus:
        if self.timeout:
            raise BridgeBackendTimeout()
        self.get_status_args = (meta.device_id, meta.command_id, meta.source, timeout)
        return DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
            firmware_version="bridge-test",
            capabilities=(
                CapabilityStatus("face", "available"),
                CapabilityStatus(
                    "camera_snapshot",
                    "unavailable",
                    detail_code="UNSUPPORTED_FEATURE",
                ),
            ),
        )

    def set_face(self, meta, name: str, timeout: float) -> BridgeCommandResponse:
        return self._accepted()

    def set_led(self, meta, pattern: str, timeout: float) -> BridgeCommandResponse:
        return self._accepted()

    def run_motion(
        self, meta, name: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        if self.timeout:
            raise BridgeBackendTimeout()
        return BridgeCommandResponse(
            ok=True,
            result_state=ResultState.COMPLETED if wait else ResultState.ACCEPTED,
        )

    def move_head_pose(
        self,
        meta,
        pan_deg: float,
        tilt_deg: float,
        speed: int,
        duration_ms: int,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        self.move_head_pose_args = (
            meta.device_id,
            pan_deg,
            tilt_deg,
            speed,
            duration_ms,
            wait,
            timeout,
        )
        return BridgeCommandResponse(
            ok=True,
            result_state=ResultState.COMPLETED if wait else ResultState.ACCEPTED,
        )

    def home_head_pose(
        self,
        meta,
        speed: int,
        duration_ms: int,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        self.home_head_pose_args = (
            meta.device_id,
            speed,
            duration_ms,
            wait,
            timeout,
        )
        return BridgeCommandResponse(
            ok=True,
            result_state=ResultState.COMPLETED if wait else ResultState.ACCEPTED,
        )

    def say(
        self, meta, text: str, voice: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        self.say_args = (meta.device_id, text, voice, wait, timeout)
        return BridgeCommandResponse(
            ok=True,
            result_state=ResultState.COMPLETED if wait else ResultState.ACCEPTED,
        )

    def play_audio(
        self, meta, path: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        self.play_audio_args = (meta.device_id, path, wait, timeout)
        return self._unsupported_media()

    def capture_audio(
        self,
        meta,
        seconds: float,
        output: str,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        self.capture_audio_args = (meta.device_id, seconds, output, wait, timeout)
        return self._unsupported_media()

    def capture_camera(
        self, meta, output: str, quality: int, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        self.capture_camera_args = (meta.device_id, output, quality, wait, timeout)
        return self._unsupported_media()

    def list_events(
        self, meta, limit: int, since_event_id: str | None, timeout: float
    ) -> EventListResult:
        self.list_events_args = (meta.device_id, limit, since_event_id, timeout)
        return self._unsupported_events(meta.device_id)

    def next_event(
        self,
        meta,
        consumer_id: str,
        after_event_id: str | None,
        timeout: float,
    ) -> EventListResult:
        self.next_event_args = (meta.device_id, consumer_id, after_event_id, timeout)
        return self._unsupported_events(meta.device_id)

    def clear_events(self, meta, consumer_id: str, timeout: float) -> EventListResult:
        self.clear_events_args = (meta.device_id, consumer_id, timeout)
        return self._unsupported_events(meta.device_id)

    def get_transcript(
        self, meta, utterance_id: str | None, timeout: float
    ) -> TranscriptResult:
        return TranscriptResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=meta.device_id,
            utterance_id=utterance_id,
            transcript=None,
            confidence=None,
            expires_at=None,
            error=ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="bridge facade does not implement transcripts yet",
                recoverable=False,
            ),
        )

    def get_power_status(self, meta, timeout: float) -> PowerStatusResult:
        self.power_status_args = (meta.device_id, meta.command_id, timeout)
        return PowerStatusResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=meta.device_id,
            voltage_v=4.9,
            current_ma=180.0,
            power_mw=882.0,
            percentage=None,
            power_source="usb",
            charging=True,
            powered=True,
            low_battery=False,
            brownout_risk=False,
            stale=False,
            stamp="2026-05-16T00:00:00Z",
            meta=meta,
        )

    @staticmethod
    def _accepted() -> BridgeCommandResponse:
        return BridgeCommandResponse(ok=True, result_state=ResultState.ACCEPTED)

    @staticmethod
    def _unsupported_media() -> BridgeCommandResponse:
        return BridgeCommandResponse(
            ok=False,
            result_state=ResultState.REJECTED,
            error=ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="bridge facade does not implement media transport yet",
                recoverable=False,
            ),
        )

    @staticmethod
    def _unsupported_events(device_id: str) -> EventListResult:
        return EventListResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=device_id,
            events=[],
            meta=None,
            error=ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="bridge facade does not implement event buffer yet",
                recoverable=False,
            ),
        )


def run_stackchanctl(argv: list[str], client: FakeBridgeClient):
    stdout = io.StringIO()
    stderr = io.StringIO()
    original = bridge_module.RclpyBridgeClient
    bridge_module.RclpyBridgeClient = lambda: client
    try:
        code = run_cli(
            argv,
            stdout=stdout,
            stderr=stderr,
            env={"XDG_CONFIG_HOME": str(ROOT / ".test-config")},
            command_id_factory=lambda: "cmd-test-0001",
            clock=lambda: FIXED_NOW,
        )
    finally:
        bridge_module.RclpyBridgeClient = original
    return code, stdout.getvalue(), stderr.getvalue()


class BridgeBackendTests(unittest.TestCase):
    def test_bridge_observe_json_uses_client_status(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "observe", "--json"],
            client,
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["device_id"], "default")
        self.assertEqual(payload["device_state"], "idle")
        self.assertEqual(payload["firmware_version"], "bridge-test")
        capabilities = {item["name"]: item for item in payload["capabilities"]}
        self.assertEqual(capabilities["face"]["state"], "available")
        self.assertEqual(capabilities["camera_snapshot"]["detail_code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(payload["command_id"], "cmd-test-0001")
        self.assertEqual(payload["metadata"]["source"], "human_cli")
        self.assertEqual(
            client.get_status_args,
            ("default", "cmd-test-0001", "human_cli", 5.0),
        )

    def test_bridge_face_json_matches_mock_shape(self) -> None:
        bridge_backend = BridgeBackend(FakeBridgeClient())
        self.assertIsNotNone(bridge_backend)

        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "face", "happy", "--json"],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["result_state"], "ACCEPTED")
        self.assertEqual(payload["command"], {"type": "face", "name": "happy"})
        self.assertEqual(payload["metadata"]["device_id"], "default")

    def test_bridge_motion_wait_can_complete(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "motion", "nod", "--wait", "--json"],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["result_state"], "COMPLETED")

    def test_bridge_motion_pose_passes_absolute_pose_to_client(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "motion",
                "pose",
                "--pan-deg",
                "30",
                "--tilt-deg",
                "20",
                "--speed",
                "500",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"]["type"], "motion.pose")
        self.assertEqual(
            client.move_head_pose_args,
            ("default", 30.0, 20.0, 500, 0, False, 5.0),
        )
        self.assertIsNone(client.home_head_pose_args)

    def test_bridge_motion_home_uses_home_client_not_pose_zero_alias(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "motion",
                "home",
                "--speed",
                "500",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"]["type"], "motion.home")
        self.assertEqual(client.home_head_pose_args, ("default", 500, 0, False, 5.0))
        self.assertIsNone(client.move_head_pose_args)

    def test_bridge_maintenance_calibration_is_unsupported_until_firmware_service_exists(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "maintenance",
                "calibration",
                "reset",
                "--confirm",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["command"]["type"], "maintenance.calibration.reset")
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertTrue(payload["error"]["recoverable"])
        self.assertIsNone(client.move_head_pose_args)
        self.assertIsNone(client.home_head_pose_args)

    def test_bridge_say_wait_can_complete(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "say", "--voice", "default", "hello", "--wait", "--json"],
            client,
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["result_state"], "COMPLETED")
        self.assertEqual(
            payload["command"],
            {"type": "say", "text_length": 5, "voice_profile": "default"},
        )
        self.assertEqual(client.say_args, ("default", "hello", "default", True, 5.0))

    def test_created_at_is_copied_to_ros_time(self) -> None:
        class Stamp:
            sec = 0
            nanosec = 0

        stamp = Stamp()
        _copy_created_at(stamp, "2026-05-16T00:00:01Z")

        self.assertEqual(stamp.sec, 1778889601)
        self.assertEqual(stamp.nanosec, 0)

    def test_bridge_timeout_maps_to_recoverable_structured_error(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "motion", "nod", "--json"],
            FakeBridgeClient(timeout=True),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["result_state"], "TIMEOUT")
        self.assertEqual(payload["error"]["code"], "TIMEOUT")
        self.assertTrue(payload["error"]["recoverable"])

    def test_bridge_audio_play_is_unsupported_until_firmware_transport_exists(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "audio", "play", "prompt.wav", "--json"],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["result_state"], "REJECTED")
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(
            payload["command"],
            {
                "type": "audio.play",
                "path": "prompt.wav",
                "format": "pcm_s16le",
                "sample_rate": 16000,
                "channels": 1,
                "chunk_ms": 20,
                "max_chunk_ms": 40,
            },
        )
        self.assertEqual(client.play_audio_args, ("default", "prompt.wav", False, 5.0))

    def test_bridge_media_rejects_safety_priority_before_unsupported_feature(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "--priority",
                "SAFETY",
                "audio",
                "play",
                "prompt.wav",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "INVALID_PRIORITY")
        self.assertIsNone(client.play_audio_args)

    def test_bridge_audio_capture_is_unsupported_until_firmware_transport_exists(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "audio",
                "capture",
                "--seconds",
                "1.5",
                "--output",
                "mic.wav",
                "--wait",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["result_state"], "REJECTED")
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(payload["command"]["type"], "audio.capture")
        self.assertEqual(payload["command"]["output"], "mic.wav")
        self.assertEqual(payload["command"]["format"], "pcm_s16le")
        self.assertEqual(payload["command"]["sample_rate"], 16000)
        self.assertEqual(client.capture_audio_args, ("default", 1.5, "mic.wav", True, 5.0))

    def test_bridge_camera_capture_is_unsupported_until_firmware_transport_exists(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "camera",
                "capture",
                "--output",
                "frame.jpg",
                "--quality",
                "80",
                "--wait",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["result_state"], "REJECTED")
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(payload["command"]["type"], "camera.capture")
        self.assertEqual(payload["command"]["format"], "jpeg")
        self.assertEqual(payload["command"]["width"], 320)
        self.assertEqual(payload["command"]["height"], 240)
        self.assertEqual(payload["command"]["quality"], 80)
        self.assertEqual(payload["command"]["max_payload_bytes"], 98304)
        self.assertEqual(client.capture_camera_args, ("default", "frame.jpg", 80, True, 5.0))

    def test_bridge_events_list_passes_since_event_to_client(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "events",
                "list",
                "--since-event",
                "evt-1",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["device_id"], "default")
        self.assertEqual(payload["events"], [])
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(client.list_events_args, ("default", 32, "evt-1", 5.0))

    def test_bridge_events_next_and_clear_pass_consumer_cursor_args(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "--source",
                "codex_skill",
                "events",
                "next",
                "--after",
                "evt-1",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(client.next_event_args, ("default", "codex_skill", "evt-1", 5.0))

        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "--source",
                "codex_skill",
                "events",
                "clear",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(client.clear_events_args, ("default", "codex_skill", 5.0))

    def test_bridge_payload_json_rejects_invalid_and_non_object_payloads(self) -> None:
        cases = [
            "raw_ir_code=0xDEADBEEF tag_id=04AABB",
            '"raw_ir_code=0xDEADBEEF tag_id=04AABB"',
            '["raw_ir_code=0xDEADBEEF", "tag_id=04AABB"]',
        ]

        for payload_json in cases:
            with self.subTest(payload_json=payload_json):
                payload = _payload_from_json(payload_json)

                self.assertTrue(payload["truncated"])
                self.assertEqual(payload["reason"], "payload_json_invalid")
                self.assertNotIn("0xDEADBEEF", str(payload))
                self.assertNotIn("04AABB", str(payload))

    def test_bridge_payload_json_redacts_sensitive_object_fields(self) -> None:
        payload = _payload_from_json(
            '{"raw_ir_code":"0xDEADBEEF","tag_id":"04AABB","protocol_dump":"NEC raw",'
            '"speech_text":"hello","asr_transcript":"open the window",'
            '"full_transcript":"turn the light on","utterance_text":"hello again",'
            '"utterance_id":"mock-utt-001","nested":{"remote_code":"volume_up"},"level":3}'
        )

        self.assertEqual(payload["raw_ir_code"], "<redacted>")
        self.assertEqual(payload["tag_id"], "<redacted>")
        self.assertEqual(payload["protocol_dump"], "<redacted>")
        self.assertEqual(payload["speech_text"], "<redacted>")
        self.assertEqual(payload["asr_transcript"], "<redacted>")
        self.assertEqual(payload["full_transcript"], "<redacted>")
        self.assertEqual(payload["utterance_text"], "<redacted>")
        self.assertEqual(payload["utterance_id"], "mock-utt-001")
        self.assertEqual(payload["nested"]["remote_code"], "<redacted>")
        self.assertEqual(payload["level"], 3)
        self.assertNotIn("0xDEADBEEF", str(payload))
        self.assertNotIn("04AABB", str(payload))
        self.assertNotIn("open the window", str(payload))
        self.assertNotIn("turn the light on", str(payload))
        self.assertNotIn("hello again", str(payload))

    def test_bridge_payload_json_redacts_valid_object_secrets_and_images(self) -> None:
        payload = _payload_from_json(
            '{"api_key":"sk-test-123","authorization":"Bearer abc","frame":"base64-image",'
            '"token":"tok","level":3}'
        )

        self.assertEqual(payload["api_key"], "<redacted>")
        self.assertEqual(payload["authorization"], "<redacted>")
        self.assertEqual(payload["frame"], "<redacted>")
        self.assertEqual(payload["token"], "<redacted>")
        self.assertEqual(payload["level"], 3)
        self.assertNotIn("sk-test-123", str(payload))
        self.assertNotIn("Bearer abc", str(payload))
        self.assertNotIn("base64-image", str(payload))

    def test_bridge_speech_transcript_is_unsupported_until_service_exists(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "speech",
                "transcript",
                "u-1",
                "--json",
            ],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["device_id"], "default")
        self.assertEqual(payload["utterance_id"], "u-1")
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")

    def test_bridge_power_status_uses_client_shape(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "power", "status", "--json"],
            client,
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["power"]["power_source"], "usb")
        self.assertEqual(payload["power"]["voltage_v"], 4.9)
        self.assertEqual(client.power_status_args, ("default", "cmd-test-0001", 5.0))

    def test_bridge_power_status_stale_error_matches_cli_shape(self) -> None:
        class StalePowerClient(FakeBridgeClient):
            def get_power_status(self, meta, timeout: float) -> PowerStatusResult:
                return PowerStatusResult(
                    ok=False,
                    result_state=ResultState.REJECTED,
                    device_id=meta.device_id,
                    voltage_v=None,
                    current_ma=None,
                    power_mw=None,
                    percentage=None,
                    power_source="usb",
                    charging=False,
                    powered=False,
                    low_battery=False,
                    brownout_risk=False,
                    stale=True,
                    meta=meta,
                    error=ErrorDetail(
                        code="STALE_TELEMETRY",
                        message="power telemetry is stale",
                        recoverable=True,
                    ),
                )

        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "power", "status", "--json"],
            StalePowerClient(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "STALE_TELEMETRY")
        self.assertTrue(payload["error"]["recoverable"])
        self.assertTrue(payload["power"]["stale"])

    def test_bridge_power_status_unsupported_error_matches_cli_shape(self) -> None:
        class UnsupportedPowerClient(FakeBridgeClient):
            def get_power_status(self, meta, timeout: float) -> PowerStatusResult:
                return PowerStatusResult(
                    ok=False,
                    result_state=ResultState.REJECTED,
                    device_id=meta.device_id,
                    voltage_v=None,
                    current_ma=None,
                    power_mw=None,
                    percentage=None,
                    power_source="unknown",
                    charging=False,
                    powered=False,
                    low_battery=False,
                    brownout_risk=False,
                    meta=meta,
                    error=ErrorDetail(
                        code="UNSUPPORTED_FEATURE",
                        message="power telemetry has not been received",
                        recoverable=False,
                    ),
                )

        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "power", "status", "--json"],
            UnsupportedPowerClient(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertFalse(payload["error"]["recoverable"])
        self.assertFalse(payload["power"]["stale"])

    def test_bridge_power_status_ros_nan_maps_to_json_null(self) -> None:
        meta = SimpleNamespace(device_id="default")
        result = SimpleNamespace(ok=True, state=2, error_code="", message="", recoverable=False)
        status = SimpleNamespace(
            device_id="default",
            stamp=SimpleNamespace(sec=1778889600, nanosec=0),
            voltage_v=float("nan"),
            current_ma=float("nan"),
            power_mw=882.0,
            percentage=float("nan"),
            power_source=2,
            charging=True,
            powered=True,
            low_battery=False,
            brownout_risk=False,
            fault_code="",
        )

        converted = _power_status_from_ros(meta, result, status, stale=False)

        self.assertIsNone(converted.voltage_v)
        self.assertIsNone(converted.current_ma)
        self.assertIsNone(converted.percentage)
        self.assertEqual(converted.power_mw, 882.0)

    def test_non_wait_action_normalizes_success_after_facade_validation(self) -> None:
        response = _normalize_action_response(
            BridgeCommandResponse(ok=True, result_state=ResultState.COMPLETED),
            wait=False,
        )

        self.assertEqual(response.result_state, ResultState.ACCEPTED)

    def test_rclpy_action_waits_for_facade_result_when_not_waiting(self) -> None:
        action = FakeActionClient()
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy()
        client._node = object()
        client._action_client_type = lambda node, action_type, action_name: action

        response = client._send_action_goal(
            object,
            "/stackchan/default/cmd/say",
            object(),
            wait=False,
            timeout=1.0,
        )

        self.assertTrue(response.ok)
        self.assertEqual(response.result_state, ResultState.ACCEPTED)
        self.assertTrue(action.goal_handle.result_requested)

    def test_run_motion_waits_for_facade_result_when_not_waiting(self) -> None:
        action = FakeActionClient()
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy()
        client._node = object()
        client._action_client_type = lambda node, action_type, action_name: action
        client._run_motion_type = FakeRunMotion

        response = client.run_motion(
            SimpleNamespace(
                device_id="default",
                command_id="cmd-test-0001",
                source="test",
                created_at="2026-05-16T00:00:00Z",
                priority=SimpleNamespace(value="NORMAL"),
            ),
            "nod",
            wait=False,
            timeout=1.0,
        )

        self.assertTrue(response.ok)
        self.assertEqual(response.result_state, ResultState.ACCEPTED)
        self.assertTrue(action.goal_handle.result_requested)

    def test_play_audio_publishes_pcm_chunks_after_goal_acceptance(self) -> None:
        action = FakeActionClient()
        node = FakeNode()
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy()
        client._node = node
        client._action_client_type = action
        client._play_audio_type = FakePlayAudio
        client._audio_chunk_type = FakeAudioChunk
        client._audio_chunk_publishers = {}
        client._audio_playback_sleep = lambda seconds: None
        client.get_status = lambda meta, timeout: DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
            last_error=None,
            capabilities=(CapabilityStatus("audio_playback", "available"),),
        )
        pcm = bytes([1, 2]) * 700
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(pcm)

            response = client.play_audio(
                SimpleNamespace(
                    device_id="default",
                    command_id="cmd-audio-0001",
                    source="test",
                    created_at="2026-05-16T00:00:00Z",
                    priority=SimpleNamespace(value="NORMAL"),
                ),
                str(path),
                wait=False,
                timeout=1.0,
            )

        self.assertTrue(response.ok)
        self.assertEqual(response.result_state, ResultState.ACCEPTED)
        self.assertEqual(action.action_name, "/stackchan/default/cmd/audio/play")
        self.assertEqual(action.last_goal.sample_rate, 16000)
        self.assertEqual(action.last_goal.channels, 1)
        self.assertFalse(action.last_goal.first_chunk_present)
        self.assertEqual(action.last_goal.first_chunk_sequence, 0)
        self.assertEqual(action.last_goal.first_chunk_pcm, b"")
        publisher = node.publishers["/stackchan/default/cmd/audio/chunks"]
        self.assertEqual(len(publisher.messages), 3)
        self.assertEqual(b"".join(message.pcm for message in publisher.messages), pcm)
        self.assertEqual([message.sequence for message in publisher.messages], [0, 1, 2])
        self.assertTrue(all(message.direction == 1 for message in publisher.messages))

    def test_play_audio_can_put_first_chunk_in_goal_for_diagnostics(self) -> None:
        action = FakeActionClient()
        node = FakeNode()
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy()
        client._node = node
        client._action_client_type = action
        client._play_audio_type = FakePlayAudio
        client._audio_chunk_type = FakeAudioChunk
        client._audio_chunk_publishers = {}
        client._audio_playback_sleep = lambda seconds: None
        client.get_status = lambda meta, timeout: DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
            last_error=None,
            capabilities=(CapabilityStatus("audio_playback", "available"),),
        )
        pcm = bytes([1, 2]) * 700
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(pcm)

            with patch.dict(
                "os.environ",
                {"STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES": "320"},
            ):
                response = client.play_audio(
                    SimpleNamespace(
                        device_id="default",
                        command_id="cmd-audio-first-goal",
                        source="test",
                        created_at="2026-05-16T00:00:00Z",
                        priority=SimpleNamespace(value="NORMAL"),
                    ),
                    str(path),
                    wait=False,
                    timeout=1.0,
                )

        self.assertTrue(response.ok)
        self.assertTrue(action.last_goal.first_chunk_present)
        self.assertEqual(action.last_goal.first_chunk_sequence, 0)
        self.assertEqual(action.last_goal.first_chunk_pcm, pcm[:320])
        publisher = node.publishers["/stackchan/default/cmd/audio/chunks"]
        self.assertEqual(len(publisher.messages), 2)
        self.assertEqual(
            b"".join(message.pcm for message in publisher.messages),
            pcm[320:],
        )
        self.assertEqual([message.sequence for message in publisher.messages], [1, 2])

    def test_play_audio_can_use_smaller_transport_chunks_for_diagnostics(self) -> None:
        action = FakeActionClient()
        node = FakeNode()
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy()
        client._node = node
        client._action_client_type = action
        client._play_audio_type = FakePlayAudio
        client._audio_chunk_type = FakeAudioChunk
        client._audio_chunk_publishers = {}
        client._audio_playback_sleep = lambda seconds: None
        client.get_status = lambda meta, timeout: DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
            last_error=None,
            capabilities=(CapabilityStatus("audio_playback", "available"),),
        )
        pcm = bytes(range(128)) * 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(pcm)

            with patch.dict(
                "os.environ",
                {
                    "STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES": "64",
                    "STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES": "64",
                },
            ):
                response = client.play_audio(
                    SimpleNamespace(
                        device_id="default",
                        command_id="cmd-audio-small-chunks",
                        source="test",
                        created_at="2026-05-16T00:00:00Z",
                        priority=SimpleNamespace(value="NORMAL"),
                    ),
                    str(path),
                    wait=False,
                    timeout=1.0,
                )

        self.assertTrue(response.ok)
        self.assertEqual(action.last_goal.first_chunk_pcm, pcm[:64])
        publisher = node.publishers["/stackchan/default/cmd/audio/chunks"]
        self.assertEqual(len(publisher.messages), 3)
        self.assertEqual([message.sequence for message in publisher.messages], [1, 2, 3])
        self.assertEqual([len(message.pcm) for message in publisher.messages], [64, 64, 64])
        self.assertEqual(
            b"".join(message.pcm for message in publisher.messages),
            pcm[64:],
        )

    def test_bridge_backend_audio_chunk_qos_is_best_effort(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "stackchanctl"
            / "backends"
            / "bridge.py"
        ).read_text()

        self.assertIn("self._audio_chunk_qos = QoSProfile(depth=8)", source)
        self.assertIn(
            "self._audio_chunk_qos.reliability = ReliabilityPolicy.BEST_EFFORT",
            source,
        )

    def test_play_audio_waits_for_chunk_subscription_before_publishing(self) -> None:
        action = FakeActionClient()
        node = FakeNode()
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy()
        client._node = node
        client._action_client_type = action
        client._play_audio_type = FakePlayAudio
        client._audio_chunk_type = FakeAudioChunk
        client._audio_chunk_publishers = {}
        sleeps = []
        client._audio_playback_sleep = lambda seconds: sleeps.append(seconds)
        client.get_status = lambda meta, timeout: DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
            last_error=None,
            capabilities=(CapabilityStatus("audio_playback", "available"),),
        )
        pcm = bytes([1, 2]) * 480
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(pcm)

            response = client.play_audio(
                SimpleNamespace(
                    device_id="default",
                    command_id="cmd-audio-0003",
                    source="test",
                    created_at="2026-05-16T00:00:00Z",
                    priority=SimpleNamespace(value="NORMAL"),
                ),
                str(path),
                wait=False,
                timeout=1.0,
            )

        self.assertTrue(response.ok)
        self.assertEqual(len(node.publishers["/stackchan/default/cmd/audio/chunks"].messages), 2)
        self.assertGreaterEqual(len(sleeps), 2)

    def test_play_audio_keeps_unsupported_capability_before_file_read(self) -> None:
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client.get_status = lambda meta, timeout: DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
            last_error=None,
            capabilities=(CapabilityStatus("audio_playback", "unavailable"),),
        )

        response = client.play_audio(
            SimpleNamespace(
                device_id="default",
                command_id="cmd-audio-0002",
                source="test",
                created_at="2026-05-16T00:00:00Z",
                priority=SimpleNamespace(value="NORMAL"),
            ),
            "missing.wav",
            wait=False,
            timeout=1.0,
        )

        self.assertFalse(response.ok)
        self.assertEqual(response.error.code, "UNSUPPORTED_FEATURE")

    def test_audio_playback_wav_rejects_non_baseline_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(b"\x00\x00" * 8)

            with self.assertRaises(BridgeBackendError) as captured:
                _read_audio_playback_pcm(str(path))

        self.assertEqual(captured.exception.code, "UNSUPPORTED_FEATURE")
        self.assertFalse(captured.exception.recoverable)

    def test_capture_audio_writes_wav_from_matching_chunks(self) -> None:
        action = FakeActionClient()
        node = FakeNode()
        chunks = [bytes([1, 0]) * 320, bytes([2, 0]) * 320]

        def emit_capture_chunks(node, future) -> None:
            if not isinstance(future.result(), SimpleNamespace):
                return
            for sequence, pcm in enumerate(chunks):
                message = FakeAudioChunk()
                message.device_id = "default"
                message.command_id = "cmd-capture-0001"
                message.direction = 2
                message.sequence = sequence
                message.format = 1
                message.sample_rate = 16000
                message.channels = 1
                message.pcm = pcm
                node.emit_audio_chunk(message)

        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy(on_spin=emit_capture_chunks)
        client._node = node
        client._action_client_type = action
        client._capture_audio_type = FakeCaptureAudio
        client._audio_chunk_type = FakeAudioChunk
        client.get_status = lambda meta, timeout: DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
            last_error=None,
            capabilities=(CapabilityStatus("audio_capture", "available"),),
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "mic.wav"
            response = client.capture_audio(
                SimpleNamespace(
                    device_id="default",
                    command_id="cmd-capture-0001",
                    source="test",
                    created_at="2026-05-16T00:00:00Z",
                    priority=SimpleNamespace(value="NORMAL"),
                ),
                1.0,
                str(output),
                wait=True,
                timeout=1.0,
            )
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.readframes(wav.getnframes()), b"".join(chunks))

        self.assertTrue(response.ok)
        self.assertEqual(response.result_state, ResultState.COMPLETED)
        self.assertEqual(action.action_name, "/stackchan/default/cmd/audio/capture")
        self.assertEqual(action.last_goal.duration_ms, 1000)
        self.assertEqual(node.subscriptions, [])

    def test_capture_audio_rejects_completed_action_without_chunks(self) -> None:
        action = FakeActionClient()
        node = FakeNode()
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy()
        client._node = node
        client._action_client_type = action
        client._capture_audio_type = FakeCaptureAudio
        client._audio_chunk_type = FakeAudioChunk
        client.get_status = lambda meta, timeout: DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
            last_error=None,
            capabilities=(CapabilityStatus("audio_capture", "available"),),
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "mic.wav"
            response = client.capture_audio(
                SimpleNamespace(
                    device_id="default",
                    command_id="cmd-capture-0002",
                    source="test",
                    created_at="2026-05-16T00:00:00Z",
                    priority=SimpleNamespace(value="NORMAL"),
                ),
                1.0,
                str(output),
                wait=True,
                timeout=1.0,
            )
            self.assertFalse(output.exists())

        self.assertFalse(response.ok)
        self.assertEqual(response.error.code, "AUDIO_CAPTURE_FAILED")
        self.assertEqual(node.subscriptions, [])

    def test_capture_camera_writes_jpeg_payload_to_output_file(self) -> None:
        jpeg = b"\xff\xd8stackchan\xff\xd9"
        action = FakeActionClient(
            action_result=SimpleNamespace(
                result=SimpleNamespace(
                    ok=True,
                    state=2,
                    error_code="",
                    message="",
                    recoverable=False,
                ),
                image=SimpleNamespace(format="jpeg", data=jpeg),
            )
        )
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy()
        client._node = object()
        client._action_client_type = action
        client._capture_camera_type = FakeCaptureCamera
        client.get_status = lambda meta, timeout: DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
            last_error=None,
            capabilities=(CapabilityStatus("camera_snapshot", "available"),),
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "frame.jpg"
            response = client.capture_camera(
                SimpleNamespace(
                    device_id="default",
                    command_id="cmd-camera-0001",
                    source="test",
                    created_at="2026-05-16T00:00:00Z",
                    priority=SimpleNamespace(value="NORMAL"),
                ),
                str(output),
                80,
                wait=True,
                timeout=1.0,
            )
            self.assertEqual(output.read_bytes(), jpeg)

        self.assertTrue(response.ok)
        self.assertEqual(response.result_state, ResultState.COMPLETED)
        self.assertEqual(action.action_name, "/stackchan/default/cmd/camera/capture")
        self.assertEqual(action.last_goal.format, "jpeg")
        self.assertEqual(action.last_goal.width, 320)
        self.assertEqual(action.last_goal.height, 240)
        self.assertEqual(action.last_goal.quality, 80)

    def test_non_wait_action_preserves_facade_rejection(self) -> None:
        response = _normalize_action_response(
            BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=ErrorDetail(
                    code="INVALID_PRIORITY",
                    message="rejected",
                    recoverable=False,
                ),
            ),
            wait=False,
        )

        self.assertFalse(response.ok)
        self.assertEqual(response.error.code, "INVALID_PRIORITY")

    def test_bridge_rejection_keeps_cli_error_shape(self) -> None:
        class RejectingClient(FakeBridgeClient):
            def set_face(self, meta, name: str, timeout: float) -> BridgeCommandResponse:
                return BridgeCommandResponse(
                    ok=False,
                    result_state=ResultState.REJECTED,
                    error=ErrorDetail(
                        code="TRANSPORT_DISCONNECTED",
                        message="device is disconnected",
                        recoverable=True,
                    ),
                )

        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "face", "happy", "--json"],
            RejectingClient(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "TRANSPORT_DISCONNECTED")
        self.assertTrue(payload["error"]["recoverable"])


class FakeRclpy:
    def __init__(self, on_spin=None) -> None:
        self.on_spin = on_spin

    def spin_until_future_complete(self, node, future, timeout_sec: float) -> None:
        del timeout_sec
        if self.on_spin is not None:
            self.on_spin(node, future)
        future.completed = True


class FakeFuture:
    def __init__(self, result) -> None:
        self._result = result
        self.completed = False

    def done(self) -> bool:
        return self.completed

    def result(self):
        return self._result


class FakeGoalHandle:
    accepted = True

    def __init__(self, action_result=None) -> None:
        self.result_requested = False
        self.action_result = action_result or SimpleNamespace(
            result=SimpleNamespace(
                ok=True,
                state=2,
                error_code="",
                message="",
                recoverable=False,
            )
        )

    def get_result_async(self):
        self.result_requested = True
        return FakeFuture(SimpleNamespace(result=self.action_result))


class FakeActionClient:
    def __init__(self, action_result=None) -> None:
        self.goal_handle = FakeGoalHandle(action_result)
        self.action_name = None
        self.last_goal = None

    def __call__(self, node, action_type, action_name):
        del node, action_type
        self.action_name = action_name
        return self

    def wait_for_server(self, timeout_sec: float) -> bool:
        del timeout_sec
        return True

    def send_goal_async(self, goal):
        self.last_goal = goal
        return FakeFuture(self.goal_handle)


class FakeRunMotion:
    class Goal:
        def __init__(self) -> None:
            self.meta = SimpleNamespace(created_at=SimpleNamespace())
            self.name = ""
            self.intensity = 0.0
            self.duration_ms = 0


class FakePlayAudio:
    class Goal:
        def __init__(self) -> None:
            self.meta = SimpleNamespace(created_at=SimpleNamespace())
            self.format = ""
            self.sample_rate = 0
            self.channels = 0
            self.first_chunk_present = False
            self.first_chunk_sequence = 0
            self.first_chunk_pcm = b""
            self.face_hint = ""
            self.motion_hint = ""


class FakeCaptureAudio:
    class Goal:
        def __init__(self) -> None:
            self.meta = SimpleNamespace(created_at=SimpleNamespace())
            self.format = ""
            self.sample_rate = 0
            self.channels = 0
            self.duration_ms = 0


class FakeCaptureCamera:
    class Goal:
        def __init__(self) -> None:
            self.meta = SimpleNamespace(created_at=SimpleNamespace())
            self.format = ""
            self.width = 0
            self.height = 0
            self.quality = 0


class FakeAudioChunk:
    def __init__(self) -> None:
        self.device_id = ""
        self.command_id = ""
        self.direction = 0
        self.sequence = 0
        self.format = 0
        self.sample_rate = 0
        self.channels = 0
        self.pcm = b""


class FakePublisher:
    def __init__(self) -> None:
        self.messages = []

    def publish(self, message) -> None:
        self.messages.append(message)


class FakeNode:
    def __init__(self) -> None:
        self.publishers = {}
        self.subscriptions = []

    def create_publisher(self, message_type, topic: str, depth: int):
        del message_type, depth
        publisher = FakePublisher()
        self.publishers[topic] = publisher
        return publisher

    def create_subscription(self, message_type, topic: str, callback, depth: int):
        del message_type, depth
        subscription = SimpleNamespace(topic=topic, callback=callback)
        self.subscriptions.append(subscription)
        return subscription

    def destroy_subscription(self, subscription) -> bool:
        if subscription in self.subscriptions:
            self.subscriptions.remove(subscription)
        return True

    def emit_audio_chunk(self, message) -> None:
        for subscription in list(self.subscriptions):
            subscription.callback(message)


if __name__ == "__main__":
    unittest.main()
