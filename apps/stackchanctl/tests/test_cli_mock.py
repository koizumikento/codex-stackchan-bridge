from __future__ import annotations

import io
import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stackchanctl.cli import run_cli  # noqa: E402


FIXED_NOW = datetime(2026, 5, 16, 0, 0, tzinfo=UTC)


def run_stackchanctl(argv: list[str], env: dict[str, str] | None = None):
    stdout = io.StringIO()
    stderr = io.StringIO()
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


if __name__ == "__main__":
    unittest.main()
