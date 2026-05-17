from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stackchanctl import cli as cli_module  # noqa: E402
from stackchanctl.cli import run_cli  # noqa: E402
from stackchanctl.contract import DeviceStatus  # noqa: E402


FIXED_NOW = datetime(2026, 5, 16, 0, 0, tzinfo=UTC)


def run_stackchanctl(argv: list[str], env: dict[str, str] | None = None):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        code = run_cli(
            argv,
            stdout=stdout,
            stderr=stderr,
            env={"XDG_CONFIG_HOME": str(ROOT / ".test-config"), **(env or {})},
            command_id_factory=lambda: "cmd-test-0001",
            clock=lambda: FIXED_NOW,
        )
    return code, stdout.getvalue(), stderr.getvalue()


class MockCliTests(unittest.TestCase):
    def test_mock_face_json_matches_fixture(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["face", "happy", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        expected = json.loads((ROOT / "tests" / "fixtures" / "face_happy_accepted.json").read_text())
        self.assertEqual(json.loads(stdout), expected)
        self.assertEqual(stderr, "")

    def test_global_options_work_after_command(self) -> None:
        code, stdout, stderr = run_stackchanctl(["face", "happy", "--backend", "mock", "--json"])

        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["result_state"], "ACCEPTED")

    def test_device_env_override_is_used_in_metadata(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["led", "progress", "--json"],
            {"STACKCHANCTL_BACKEND": "mock", "STACKCHANCTL_DEVICE": "desk"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["device_id"], "desk")
        self.assertEqual(payload["metadata"]["device_id"], "desk")

    def test_source_env_override_is_used_in_metadata(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["face", "thinking", "--json"],
            {"STACKCHANCTL_BACKEND": "mock", "STACKCHANCTL_SOURCE": "codex_skill"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["metadata"]["source"], "codex_skill")

    def test_wait_returns_completed_when_supported(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "nod", "--wait", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["result_state"], "COMPLETED")

    def test_audio_play_mock_json_has_chunk_contract(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["audio", "play", "prompt.wav", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        command = json.loads(stdout)["command"]
        self.assertEqual(command["type"], "audio.play")
        self.assertEqual(command["format"], "pcm_s16le")
        self.assertEqual(command["sample_rate"], 16000)
        self.assertEqual(command["channels"], 1)
        self.assertEqual(command["chunk_ms"], 20)
        self.assertEqual(command["max_chunk_ms"], 40)

    def test_audio_capture_mock_json_has_output_contract(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["audio", "capture", "--seconds", "2.5", "--output", "mic.wav", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        command = json.loads(stdout)["command"]
        self.assertEqual(command["type"], "audio.capture")
        self.assertEqual(command["seconds"], 2.5)
        self.assertEqual(command["output"], "mic.wav")

    def test_camera_capture_mock_json_has_payload_contract(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["camera", "capture", "--output", "frame.jpg", "--quality", "75", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        command = json.loads(stdout)["command"]
        self.assertEqual(command["type"], "camera.capture")
        self.assertEqual(command["format"], "jpeg")
        self.assertEqual(command["width"], 320)
        self.assertEqual(command["height"], 240)
        self.assertEqual(command["max_payload_bytes"], 98304)

    def test_nfc_wait_mock_json_redacts_tag_logging(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["nfc", "wait", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        command = json.loads(stdout)["command"]
        self.assertEqual(command["type"], "nfc.wait")
        self.assertEqual(command["tag_id_logging"], "redacted")

    def test_imu_stream_mock_json_is_separate_from_status(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["imu", "stream", "--hz", "20", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        command = json.loads(stdout)["command"]
        self.assertEqual(command["type"], "imu.stream")
        self.assertEqual(command["topic"], "imu/raw")
        self.assertFalse(command["status_field"])

    def test_events_list_mock_json_matches_fixture(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["events", "list", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        expected = json.loads((ROOT / "tests" / "fixtures" / "events_list_default.json").read_text())
        self.assertEqual(json.loads(stdout), expected)

    def test_events_next_mock_json_returns_single_event(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["events", "next", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["device_id"], "default")
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["event_name"], "picked_up")
        self.assertEqual(payload["events"][0]["event_id"], "mock-event-0001")
        self.assertEqual(payload["events"][0]["source"], "firmware")
        self.assertEqual(payload["cursor"], "mock-event-0001")
        self.assertEqual(payload["command_id"], "cmd-test-0001")
        self.assertEqual(payload["metadata"]["source"], "human_cli")

    def test_events_next_mock_json_empty_after_last_event_is_ok(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["events", "next", "--after", "mock-event-0002", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["events"], [])
        self.assertIsNone(payload["cursor"])

    def test_events_tail_mock_json_uses_count(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["events", "tail", "--limit", "1", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["event_name"], "transcript_ready")

    def test_events_clear_mock_json_empty_events_are_ok(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["events", "clear", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["device_id"], "default")
        self.assertEqual(payload["events"], [])
        self.assertIsNone(payload["cursor"])

    def test_speech_transcript_mock_json_matches_fixture(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["speech", "transcript", "mock-utt-001", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        expected = json.loads(
            (ROOT / "tests" / "fixtures" / "speech_transcript_default.json").read_text()
        )
        self.assertEqual(json.loads(stdout), expected)

    def test_speech_transcript_missing_json_is_structured_error(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["speech", "transcript", "missing", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["result_state"], "REJECTED")
        self.assertEqual(payload["command_id"], "cmd-test-0001")
        self.assertEqual(payload["error"]["code"], "TRANSCRIPT_NOT_FOUND")

    def test_power_status_mock_json_is_strict_and_deterministic(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["power", "status", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result_state"], "COMPLETED")
        self.assertEqual(payload["device_id"], "default")
        self.assertEqual(payload["power"]["power_source"], "usb")
        self.assertTrue(payload["power"]["charging"])
        self.assertIsNone(payload["power"]["percentage"])
        self.assertEqual(payload["command_id"], "cmd-test-0001")

    def test_power_status_stale_mock_json_is_structured_error(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--device", "stale_power", "power", "status", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "STALE_TELEMETRY")
        self.assertTrue(payload["error"]["recoverable"])
        self.assertTrue(payload["power"]["stale"])

    def test_camera_quality_failure_is_recoverable(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["camera", "capture", "--output", "frame.jpg", "--quality", "99", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "CAMERA_CAPTURE_FAILED")
        self.assertTrue(payload["error"]["recoverable"])

    def test_cli_safety_priority_is_rejected_with_structured_error(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["face", "happy", "--priority", "SAFETY", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["result_state"], "REJECTED")
        self.assertEqual(payload["error"]["code"], "INVALID_PRIORITY")
        self.assertFalse(payload["error"]["recoverable"])

    def test_unknown_face_is_rejected_by_mock_contract(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["face", "angry", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "UNKNOWN_COMMAND")

    def test_timeout_state_is_structured_and_recoverable(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "nod", "--timeout", "0", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["result_state"], "TIMEOUT")
        self.assertEqual(payload["error"]["code"], "TIMEOUT")
        self.assertTrue(payload["error"]["recoverable"])

    def test_non_finite_timeout_is_rejected_by_parser(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "nod", "--timeout", "NaN", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("'NaN' must be finite", stderr)

    def test_non_finite_audio_seconds_is_rejected_by_parser(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["audio", "capture", "--seconds", "NaN", "--output", "mic.wav", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("'NaN' must be finite", stderr)

    def test_non_finite_imu_hz_is_rejected_by_parser(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["imu", "stream", "--hz", "Infinity", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("'Infinity' must be finite", stderr)

    def test_observe_json_matches_fixture(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["observe", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        expected = json.loads((ROOT / "tests" / "fixtures" / "observe_default.json").read_text())
        self.assertEqual(json.loads(stdout), expected)

    def test_human_output_is_compact(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["say", "hello"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, "ACCEPTED say device=default command_id=cmd-test-0001\n")

    def test_cli_closes_backend_when_supported(self) -> None:
        class ClosingBackend:
            def __init__(self) -> None:
                self.closed = False

            def execute(self, request):
                return DeviceStatus(
                    device_id=request.meta.device_id,
                    connected=True,
                    device_state="idle",
                    face="neutral",
                )

            def close(self) -> None:
                self.closed = True

        backend = ClosingBackend()
        original_create_backend = cli_module.create_backend
        cli_module.create_backend = lambda name: backend
        try:
            code, stdout, stderr = run_stackchanctl(
                ["observe", "--json"],
                {"STACKCHANCTL_BACKEND": "mock"},
            )
        finally:
            cli_module.create_backend = original_create_backend

        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["device_state"], "idle")
        self.assertTrue(backend.closed)

    def test_cli_close_failure_is_reported_without_overriding_result(self) -> None:
        class BadCloseBackend:
            def execute(self, request):
                return DeviceStatus(
                    device_id=request.meta.device_id,
                    connected=True,
                    device_state="idle",
                    face="neutral",
                )

            def close(self) -> None:
                raise RuntimeError("close failed")

        original_create_backend = cli_module.create_backend
        cli_module.create_backend = lambda name: BadCloseBackend()
        try:
            code, stdout, stderr = run_stackchanctl(
                ["observe", "--json"],
                {"STACKCHANCTL_BACKEND": "mock"},
            )
        finally:
            cli_module.create_backend = original_create_backend

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["device_state"], "idle")
        self.assertIn("stackchanctl backend close error: close failed", stderr)


if __name__ == "__main__":
    unittest.main()
