from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


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
    def test_bridge_delegates_to_container_when_ros_python_is_unavailable(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("stackchanctl.cli._bridge_python_available", return_value=False),
            patch("stackchanctl.cli.subprocess.run") as subprocess_run,
        ):
            subprocess_run.return_value = SimpleNamespace(
                returncode=0,
                stdout='{"ok": true, "result_state": "ACCEPTED"}\n',
                stderr="",
            )
            code = run_cli(
                ["--backend", "bridge", "observe", "--json"],
                stdout=stdout,
                stderr=stderr,
                env={
                    "XDG_CONFIG_HOME": str(ROOT / ".test-config"),
                    "STACKCHANCTL_SOURCE": "codex_skill",
                },
                command_id_factory=lambda: "cmd-test-0001",
                clock=lambda: FIXED_NOW,
            )

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["result_state"], "ACCEPTED")
        self.assertEqual(stderr.getvalue(), "")
        docker_args = subprocess_run.call_args.args[0]
        self.assertEqual(docker_args[:2], ["docker", "exec"])
        self.assertIn("STACKCHANCTL_BACKEND=bridge", docker_args)
        self.assertIn("STACKCHANCTL_SOURCE=codex_skill", docker_args)
        self.assertIn("stackchan-e2e-live", docker_args)
        self.assertTrue(any("python3 -m stackchanctl" in arg for arg in docker_args))
        self.assertEqual(docker_args[-4:], ["--backend", "bridge", "observe", "--json"])

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

    def test_named_motion_presets_return_deterministic_json(self) -> None:
        for name in ("nod", "shake", "cheerful", "idle", "look-left", "look-right", "look-user"):
            with self.subTest(name=name):
                code, stdout, stderr = run_stackchanctl(
                    ["motion", name, "--json"],
                    {"STACKCHANCTL_BACKEND": "mock"},
                )

                self.assertEqual(code, 0, stderr)
                payload = json.loads(stdout)
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["command"], {"type": "motion", "name": name})
                self.assertEqual(payload["result_state"], "ACCEPTED")

    def test_mood_mock_json_reports_step_summary(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["mood", "done", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result_state"], "ACCEPTED")
        self.assertEqual(payload["command"]["type"], "mood")
        self.assertEqual(payload["command"]["name"], "done")
        self.assertEqual(
            payload["command"]["steps"],
            [
                {"type": "face", "name": "happy"},
                {"type": "led", "pattern": "success"},
                {"type": "motion", "name": "cheerful"},
            ],
        )

    def test_unknown_mood_is_rejected_by_mock_contract(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["mood", "party", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["result_state"], "REJECTED")
        self.assertEqual(payload["error"]["code"], "UNKNOWN_COMMAND")

    def test_demo_mock_json_has_metadata_only_contract(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["demo", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"]["type"], "demo")
        self.assertFalse(payload["command"]["include_say"])
        self.assertFalse(payload["command"]["include_media"])
        steps = {step["name"]: step for step in payload["command"]["steps"]}
        self.assertEqual(steps["say"]["state"], "skipped")
        self.assertEqual(steps["camera.capture"]["state"], "skipped")
        forbidden = json.dumps(payload, ensure_ascii=False).lower()
        self.assertNotIn("pcm", forbidden)
        self.assertNotIn("jpeg", forbidden)
        self.assertNotIn("speech_text", forbidden)

    def test_demo_mock_include_flags_add_bounded_steps(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            [
                "demo",
                "--include-say",
                "--voice",
                "default",
                "--include-media",
                "--output-dir",
                "tmp/demo",
                "--json",
            ],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        steps = {step["name"]: step for step in payload["command"]["steps"]}
        self.assertEqual(steps["say"]["state"], "completed")
        self.assertEqual(steps["say"]["voice_profile"], "default")
        self.assertEqual(steps["say"]["text_length"], 2)
        self.assertEqual(steps["audio.capture"]["output"], str(Path("tmp/demo") / "demo_capture.wav"))
        self.assertEqual(steps["camera.capture"]["output"], str(Path("tmp/demo") / "demo_frame.jpg"))
        self.assertNotIn("はい", stdout)

    def test_say_can_include_expression_hints(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            [
                "say",
                "--face",
                "happy",
                "--motion",
                "cheerful",
                "--after-face",
                "happy",
                "やったよ",
                "--json",
            ],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"]["type"], "say")
        self.assertEqual(payload["command"]["face_hint"], "happy")
        self.assertEqual(payload["command"]["motion_hint"], "cheerful")
        self.assertEqual(payload["command"]["after_face"], "happy")
        self.assertEqual(payload["command"]["text_length"], 4)

    def test_say_rejects_unknown_motion_hint(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["say", "--motion", "spin", "hello", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "UNKNOWN_COMMAND")

    def test_say_rejects_unknown_face_hint(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["say", "--face", "smirk", "hello", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "UNKNOWN_COMMAND")

    def test_say_rejects_unknown_after_face(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["say", "--after-face", "smirk", "hello", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "UNKNOWN_COMMAND")

    def test_named_motion_rejects_extra_positional_args(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "nod", "extra", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("named motion accepts exactly one motion name", stderr)

    def test_motion_pose_mock_json_uses_home_frame_absolute_angles(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "pose", "--pan-deg", "30", "--tilt-deg", "20", "--speed", "500", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"]["type"], "motion.pose")
        self.assertEqual(payload["command"]["frame"], "home")
        self.assertEqual(payload["command"]["pan_deg"], 30.0)
        self.assertEqual(payload["command"]["tilt_deg"], 20.0)
        self.assertEqual(payload["command"]["speed"], 500)

    def test_motion_home_mock_json_is_dedicated_command(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "home", "--speed", "500", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"]["type"], "motion.home")
        self.assertEqual(payload["command"]["frame"], "home")

    def test_motion_status_mock_json_returns_pose(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "status", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["pose"]["frame"], "home")
        self.assertEqual(payload["pose"]["pan_deg"], 0.0)
        self.assertEqual(payload["pose"]["tilt_deg"], 0.0)
        self.assertFalse(payload["pose"]["stale"])

    def test_motion_pose_out_of_range_rejects_without_clamping(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "pose", "--pan-deg", "129", "--tilt-deg", "20", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "SERVO_LIMIT_EXCEEDED")
        self.assertEqual(payload["command"]["pan_deg"], 129.0)

    def test_motion_pose_rejects_vertical_end_stop(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "pose", "--pan-deg", "0", "--tilt-deg", "0", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "SERVO_LIMIT_EXCEEDED")
        self.assertEqual(payload["error"]["message"], "motion pose tilt_deg is outside 5..85")

    def test_motion_status_stale_is_non_success(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--device", "stale_pose", "motion", "status", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "STALE_TELEMETRY")
        self.assertTrue(payload["pose"]["stale"])

    def test_motion_status_calibration_invalid_is_non_success(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--device", "uncalibrated_pose", "motion", "status", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "CALIBRATION_INVALID")

    def test_maintenance_calibration_status_is_human_only_json(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["maintenance", "calibration", "status", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"]["type"], "maintenance.calibration.status")
        self.assertEqual(payload["command"]["store"], "firmware_nvs")
        self.assertFalse(payload["command"]["write"])
        self.assertEqual(payload["metadata"]["source"], "human_cli")

    def test_maintenance_calibration_capture_neutral_requires_confirmation(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["maintenance", "calibration", "capture-neutral", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("maintenance calibration write/reset commands require --confirm", stderr)

    def test_maintenance_calibration_capture_neutral_confirmed(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["maintenance", "calibration", "capture-neutral", "--confirm", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"]["type"], "maintenance.calibration.capture-neutral")
        self.assertTrue(payload["command"]["confirmed"])
        self.assertTrue(payload["command"]["write"])

    def test_maintenance_calibration_reset_confirmed_resets_to_invalid(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["maintenance", "calibration", "reset", "--confirm", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"]["type"], "maintenance.calibration.reset")
        self.assertEqual(payload["command"]["reset_to"], "invalid")
        self.assertFalse(payload["command"]["calibration_valid"])

    def test_maintenance_calibration_rejects_codex_skill_source(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            [
                "--source",
                "codex_skill",
                "maintenance",
                "calibration",
                "status",
                "--json",
            ],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("maintenance calibration commands require source=human_cli", stderr)

    def test_non_finite_motion_pose_is_rejected_by_parser(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "pose", "--pan-deg", "NaN", "--tilt-deg", "20", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("'NaN' must be finite", stderr)

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
        self.assertNotIn("pcm", json.dumps(payload := json.loads(stdout)).lower().replace("pcm_s16le", ""))
        self.assertNotIn("transcript", payload)

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

    def test_audio_mock_failure_matrix_is_structured(self) -> None:
        cases = [
            (
                ["--device", "audio_timeout", "audio", "play", "prompt.wav", "--json"],
                "TIMEOUT",
                "TIMEOUT",
                True,
            ),
            (
                ["--device", "audio_underrun", "audio", "play", "prompt.wav", "--json"],
                "REJECTED",
                "AUDIO_UNDERRUN",
                True,
            ),
            (
                ["--device", "mic_overrun", "audio", "capture", "--seconds", "1", "--output", "mic.wav", "--json"],
                "REJECTED",
                "MIC_OVERRUN",
                True,
            ),
            (
                ["--device", "audio_capture_failed", "audio", "capture", "--seconds", "1", "--output", "mic.wav", "--json"],
                "REJECTED",
                "AUDIO_CAPTURE_FAILED",
                True,
            ),
            (
                ["--device", "audio_malformed", "audio", "capture", "--seconds", "1", "--output", "mic.wav", "--json"],
                "REJECTED",
                "MALFORMED_AUDIO_CHUNK",
                True,
            ),
            (
                ["--device", "audio_disconnected", "audio", "play", "prompt.wav", "--json"],
                "REJECTED",
                "TRANSPORT_DISCONNECTED",
                True,
            ),
            (
                ["--device", "unsupported_audio", "audio", "play", "prompt.wav", "--json"],
                "REJECTED",
                "UNSUPPORTED_FEATURE",
                False,
            ),
        ]

        for args, state, error_code, recoverable in cases:
            with self.subTest(args=args):
                code, stdout, stderr = run_stackchanctl(args, {"STACKCHANCTL_BACKEND": "mock"})
                self.assertEqual(code, 1)
                self.assertEqual(stdout, "")
                payload = json.loads(stderr)
                self.assertEqual(payload["result_state"], state)
                self.assertEqual(payload["error"]["code"], error_code)
                self.assertEqual(payload["error"]["recoverable"], recoverable)
                self.assertNotIn("transcript", stderr)
                self.assertNotIn("raw_audio", stderr)

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
        self.assertNotIn("base64", stdout)
        self.assertNotIn("data", command)

    def test_camera_mock_failure_matrix_is_structured(self) -> None:
        cases = [
            (
                ["--device", "camera_timeout", "camera", "capture", "--output", "frame.jpg", "--json"],
                "TIMEOUT",
                "TIMEOUT",
                True,
            ),
            (
                ["--device", "camera_oversize", "camera", "capture", "--output", "frame.jpg", "--json"],
                "REJECTED",
                "CAMERA_CAPTURE_FAILED",
                True,
            ),
            (
                ["--device", "unsupported_camera", "camera", "capture", "--output", "frame.jpg", "--json"],
                "REJECTED",
                "UNSUPPORTED_FEATURE",
                False,
            ),
        ]

        for args, state, error_code, recoverable in cases:
            with self.subTest(args=args):
                code, stdout, stderr = run_stackchanctl(args, {"STACKCHANCTL_BACKEND": "mock"})
                self.assertEqual(code, 1)
                self.assertEqual(stdout, "")
                payload = json.loads(stderr)
                self.assertEqual(payload["result_state"], state)
                self.assertEqual(payload["error"]["code"], error_code)
                self.assertEqual(payload["error"]["recoverable"], recoverable)
                self.assertNotIn("base64", stderr)
                self.assertNotIn("jpeg_bytes", stderr)

    def test_nfc_wait_mock_json_redacts_tag_logging(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["nfc", "wait", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        command = json.loads(stdout)["command"]
        self.assertEqual(command["type"], "nfc.wait")
        self.assertEqual(command["tag_id_logging"], "redacted")
        self.assertEqual(command["identifier_policy"], "reference")

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

    def test_power_status_unsupported_mock_json_is_structured_error(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--device", "unsupported_power", "power", "status", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertFalse(payload["error"]["recoverable"])

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

    def test_unknown_motion_is_rejected_by_mock_contract(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "spin", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "UNKNOWN_COMMAND")
        self.assertEqual(payload["command"], {"type": "motion", "name": "spin"})

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

    def test_timeout_env_is_used_when_cli_timeout_is_omitted(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["motion", "nod", "--json"],
            {"STACKCHANCTL_BACKEND": "mock", "STACKCHANCTL_TIMEOUT": "0"},
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["result_state"], "TIMEOUT")
        self.assertEqual(payload["error"]["code"], "TIMEOUT")

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

    def test_observe_json_reports_unavailable_capability_without_payloads(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--device", "unsupported_camera", "observe", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        capabilities = {item["name"]: item for item in payload["capabilities"]}
        self.assertEqual(capabilities["camera_snapshot"]["state"], "unavailable")
        self.assertEqual(capabilities["camera_snapshot"]["detail_code"], "UNSUPPORTED_FEATURE")
        self.assertNotIn("image_payload", stdout)
        self.assertNotIn("base64", stdout)

    def test_doctor_mock_json_reports_checks_without_sensitive_payloads(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["doctor", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result_state"], "COMPLETED")
        self.assertEqual(payload["backend"], "mock")
        self.assertEqual(payload["overall_state"], "ok")
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual(checks["connection"]["state"], "ok")
        self.assertEqual(checks["power"]["state"], "ok")
        self.assertEqual(checks["motion_pose"]["state"], "ok")
        forbidden = stdout.lower()
        self.assertNotIn("pcm", forbidden)
        self.assertNotIn("base64", forbidden)
        self.assertNotIn("speech_text", forbidden)
        self.assertNotIn("raw_ir", forbidden)

    def test_doctor_mock_reports_overall_degraded_with_ok_true(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--device", "unsupported_camera", "doctor", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["overall_state"], "degraded")
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual(checks["capability.camera_snapshot"]["state"], "degraded")
        self.assertEqual(checks["capability.camera_snapshot"]["detail_code"], "UNSUPPORTED_FEATURE")

    def test_human_output_is_compact(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["say", "hello"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, "ACCEPTED say device=default command_id=cmd-test-0001\n")

    def test_say_json_reports_voice_profile_without_text(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["say", "--voice", "default", "hello", "--json"],
            {"STACKCHANCTL_BACKEND": "mock"},
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(
            payload["command"],
            {"type": "say", "text_length": 5, "voice_profile": "default"},
        )
        self.assertNotIn("hello", stdout)

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
