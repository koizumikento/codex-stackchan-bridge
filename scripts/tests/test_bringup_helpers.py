from __future__ import annotations

import argparse
import unittest
from unittest import mock

from scripts import microros_agent_container


def smoke_args(
    *,
    skip_build: bool = False,
    clean_ros_build: bool = False,
    allow_stale_install: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        skip_build=skip_build,
        clean_ros_build=clean_ros_build,
        allow_stale_install=allow_stale_install,
    )


def bridge_smoke_args(
    *,
    allow_missing_firmware_ready: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        image="test-image",
        skip_build=True,
        clean_ros_build=False,
        allow_stale_install=False,
        disconnect_check=False,
        reconnect_check=False,
        allow_missing_firmware_ready=allow_missing_firmware_ready,
        disconnect_face_command="",
        face_check="",
        say_check="はい",
        say_naturalness_check=False,
        say_voice="default",
        say_face="",
        say_motion="",
        say_after_face="",
        say_operator_listening_verdict="unrecorded",
        say_operator_listening_issue="none",
        led_check=False,
        motion_check="",
        motion_disconnect_check="",
        motion_expected_error="",
        pose_pan_deg=None,
        pose_tilt_deg=None,
        home_check=False,
        soak_seconds=0,
        soak_interval_seconds=1,
        timeout=30,
        pty="/tmp/stackchan-test-pty",
        tcp_host="host.docker.internal",
        tcp_port=11411,
        baud=921600,
        verbose=4,
    )


def bridge_live_args() -> argparse.Namespace:
    return argparse.Namespace(
        image="test-image",
        skip_build=True,
        clean_ros_build=False,
        allow_stale_install=False,
        tcp_host="host.docker.internal",
        tcp_port=11411,
        pty="/tmp/stackchan-test-pty",
        baud=921600,
        verbose=4,
        timeout=190,
        name="stackchan-e2e-live",
        replace=True,
        foreground=False,
        tts_endpoint="http://host.docker.internal:50021",
        disable_tts=False,
        restart_policy="no",
    )


def sensor_sweep_args() -> argparse.Namespace:
    return argparse.Namespace(
        image="test-image",
        skip_build=True,
        clean_ros_build=False,
        allow_stale_install=False,
        tcp_host="host.docker.internal",
        tcp_port=11411,
        pty="/tmp/stackchan-test-pty",
        baud=921600,
        verbose=4,
        timeout=10,
        stimulus_window_seconds=0,
        media_audio_capture_seconds=0.02,
        media_audio_playback_duration_ms=20.0,
        media_audio_playback_frequency=440.0,
        media_audio_playback_amplitude=1200,
        media_audio_playback_wait=True,
        media_camera_quality=50,
        media_mode="all",
        media_playback_only=True,
        skip_media_smoke=False,
    )


def media_overlap_args() -> argparse.Namespace:
    return argparse.Namespace(
        image="test-image",
        skip_build=True,
        clean_ros_build=False,
        allow_stale_install=False,
        tcp_host="host.docker.internal",
        tcp_port=11411,
        pty="/tmp/stackchan-test-pty",
        baud=921600,
        verbose=4,
        timeout=45,
        media_camera_quality=50,
        media_audio_capture_seconds=2.0,
        media_audio_playback_duration_ms=250.0,
        media_audio_playback_frequency=440.0,
        media_audio_playback_amplitude=1200,
        say_text="",
    )


class MicroRosAgentContainerTests(unittest.TestCase):
    def test_default_ros_smoke_build_is_incremental_symlink_install(self) -> None:
        script = microros_agent_container.ros_smoke_setup_script(smoke_args())

        self.assertIn("colcon build", script)
        self.assertIn("--symlink-install", script)
        self.assertNotIn("--cmake-clean-cache", script)
        self.assertNotIn("apt-get", script)

    def test_clean_ros_build_is_explicit(self) -> None:
        script = microros_agent_container.ros_smoke_setup_script(
            smoke_args(clean_ros_build=True),
        )

        self.assertIn("--cmake-clean-cache", script)

    def test_skip_build_uses_stale_guard_without_rebuilding(self) -> None:
        script = microros_agent_container.ros_smoke_setup_script(
            smoke_args(skip_build=True),
        )

        self.assertIn("STALE_GUARD", script)
        self.assertIn(".stackchan_ros_stackchan_msgs_build_stamp", script)
        self.assertIn(".stackchan_ros_stackchan_bridge_build_stamp", script)
        self.assertNotIn("colcon build", script)

    def test_skip_build_and_clean_build_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            microros_agent_container.ros_smoke_setup_script(
                smoke_args(skip_build=True, clean_ros_build=True),
            )

    def test_loaded_audio_probe_chunk_sizes_require_even_values(self) -> None:
        self.assertEqual(
            microros_agent_container.parse_chunk_sizes("32, 64,160"),
            [32, 64, 160],
        )
        with self.assertRaises(ValueError):
            microros_agent_container.parse_chunk_sizes("63")

    def test_audio_tts_smoke_passthrough_includes_adpcm_controls(self) -> None:
        self.assertIn(
            "STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_TTS_LOADED_ADPCM",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_TTS_LOADED_TRANSPORT",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_TTS_LOADED_SPLIT_OVERSIZE",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_ANCHOR_REPEATS",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_ANCHOR_SERVICE_AFTER_PASSES",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOADED_MAX_DECODED_BYTES",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_TTS_PROGRESSIVE_TEXT_SEGMENTS",
            microros_agent_container.ENV_PASSTHROUGH,
        )
        self.assertIn(
            "STACKCHAN_TTS_PROGRESSIVE_TEXT_SEGMENT_MAX_CHARS",
            microros_agent_container.ENV_PASSTHROUGH,
        )

    def test_bridge_smoke_preserves_early_firmware_ready_observation(self) -> None:
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_bridge_smoke(bridge_smoke_args())

        command = docker_run.call_args.args[1]
        self.assertIn("firmware_ready_seen=0", command)
        self.assertIn("--- connected observe wait ---", command)
        self.assertIn("STACKCHAN_BRIDGE_CONNECTED_OBSERVE_SEEN=", command)
        self.assertIn('if [ "$bridge_connected_seen_result" -eq 0 ]; then', command)
        self.assertIn('if [ "$status_connected_result" -eq 0 ]; then', command)
        self.assertIn("STACKCHAN_BRIDGE_STATUS_CONNECTED_VIA_OBSERVE=", command)
        self.assertIn('firmware_ready_seen=1', command)
        self.assertIn('STACKCHAN_BRIDGE_FIRMWARE_READY_SEEN=$firmware_ready_seen', command)
        self.assertIn('[ "$firmware_ready_seen" = "1" ] || result=1', command)
        self.assertNotIn('[ "$firmware_ready_result" -eq 0 ] || result=1', command)

    def test_bridge_smoke_uses_balanced_tts_defaults(self) -> None:
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_bridge_smoke(bridge_smoke_args())

        command = docker_run.call_args.args[1]
        self.assertIn("STACKCHAN_TTS_SPEED_SCALE:-1.0", command)
        self.assertIn("STACKCHAN_TTS_PRE_PHONEME_LENGTH:-0.03", command)
        self.assertIn("STACKCHAN_TTS_POST_PHONEME_LENGTH:-0.03", command)
        self.assertIn("STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD:-256", command)
        self.assertIn("STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS:-30.0", command)

    def test_bridge_smoke_passes_say_expression_hints(self) -> None:
        args = bridge_smoke_args()
        args.say_face = "happy"
        args.say_motion = "cheerful"
        args.say_after_face = "happy"
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_bridge_smoke(args)

        command = docker_run.call_args.args[1]
        self.assertIn("say --voice default --face happy --motion cheerful --after-face happy", command)
        self.assertIn('STACKCHAN_BRIDGE_SAY_FACE_HINT_SEEN=', command)
        self.assertIn('STACKCHAN_BRIDGE_SAY_MOTION_HINT_SEEN=', command)
        self.assertIn('STACKCHAN_BRIDGE_SAY_AFTER_FACE_SEEN=', command)

    def test_bridge_smoke_marks_say_operator_listening_gate(self) -> None:
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_bridge_smoke(bridge_smoke_args())

        command = docker_run.call_args.args[1]
        self.assertIn("STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=", command)
        self.assertIn("STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_REQUIRED=1", command)
        self.assertIn(
            "STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_CHECKS="
            "intelligible,volume_ok,no_truncation,no_phrase_chop,wait_acceptable",
            command,
        )
        self.assertIn("STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_VERDICT=unrecorded", command)
        self.assertIn("STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_ISSUE=none", command)

    def test_bridge_smoke_can_use_default_say_naturalness_candidate(self) -> None:
        args = bridge_smoke_args()
        args.say_check = ""
        args.say_naturalness_check = True
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_bridge_smoke(args)

        command = docker_run.call_args.args[1]
        self.assertIn(microros_agent_container.DEFAULT_SAY_NATURALNESS_CHECK_TEXT, command)
        self.assertIn(
            "say --voice default --face happy --motion cheerful --after-face happy",
            command,
        )
        self.assertIn("STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_REQUIRED=1", command)
        self.assertIn(
            "STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_PASS_RERUN_HINT=uv run "
            "--no-project python scripts/microros_agent_container.py "
            "tcp-pty-bridge-smoke",
            command,
        )
        self.assertIn("--say-naturalness-check --say-operator-listening-verdict pass", command)

    def test_bridge_smoke_does_not_print_pass_hint_for_arbitrary_say_text(self) -> None:
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_bridge_smoke(bridge_smoke_args())

        command = docker_run.call_args.args[1]
        self.assertNotIn("STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_PASS_RERUN_HINT", command)

    def test_bridge_smoke_can_record_operator_listening_verdict(self) -> None:
        args = bridge_smoke_args()
        args.say_operator_listening_verdict = "pass"
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_bridge_smoke(args)

        command = docker_run.call_args.args[1]
        self.assertIn("STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_VERDICT=pass", command)
        self.assertIn("STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_ISSUE=none", command)
        self.assertIn("STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_REQUIRED=1", command)

    def test_bridge_smoke_can_record_operator_listening_failure_issue(self) -> None:
        args = bridge_smoke_args()
        args.say_operator_listening_verdict = "fail"
        args.say_operator_listening_issue = "wait"
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_bridge_smoke(args)

        command = docker_run.call_args.args[1]
        self.assertIn("STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_VERDICT=fail", command)
        self.assertIn("STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_ISSUE=wait", command)

    def test_bridge_smoke_rejects_failed_operator_verdict_without_issue(self) -> None:
        args = bridge_smoke_args()
        args.say_operator_listening_verdict = "fail"
        with self.assertRaises(SystemExit):
            microros_agent_container.run_tcp_pty_bridge_smoke(args)

    def test_bridge_smoke_rejects_unrecorded_operator_verdict_with_issue(self) -> None:
        args = bridge_smoke_args()
        args.say_operator_listening_issue = "wait"
        with self.assertRaises(SystemExit):
            microros_agent_container.run_tcp_pty_bridge_smoke(args)

    def test_bridge_smoke_rejects_pass_operator_verdict_with_issue(self) -> None:
        args = bridge_smoke_args()
        args.say_operator_listening_verdict = "pass"
        args.say_operator_listening_issue = "wait"
        with self.assertRaises(SystemExit):
            microros_agent_container.run_tcp_pty_bridge_smoke(args)

    def test_bridge_live_starts_named_container_for_host_cli_delegate(self) -> None:
        args = bridge_live_args()
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_bridge_live(args)

        command = docker_run.call_args.args[1]
        kwargs = docker_run.call_args.kwargs
        self.assertEqual(kwargs["name"], "stackchan-e2e-live")
        self.assertTrue(kwargs["replace"])
        self.assertTrue(kwargs["detach"])
        self.assertTrue(kwargs["mount_workspace"])
        self.assertEqual(kwargs["workdir"], microros_agent_container.WORKSPACE)
        self.assertIn("STACKCHAN_BRIDGE_LIVE_READY=1", command)
        self.assertIn("stackchan_bridge_node", command)
        self.assertIn("micro_ros_agent serial", command)
        self.assertIn("wait -n", command)
        self.assertIn("tts_enabled:=true", command)

    def test_sensor_sweep_walks_media_terminal_events_after_pre_command_cursor(self) -> None:
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_sensor_sweep(sensor_sweep_args())

        command = docker_run.call_args.args[1]
        self.assertIn("json_cursor()", command)
        self.assertIn("audio_play_before_event_id=", command)
        self.assertIn(
            'wait_media_action_terminal "$audio_play_command_id" "audio_playback_action" 10 "$audio_play_before_event_id"',
            command,
        )
        self.assertIn('events next --after "$after_event_id" --json', command)
        self.assertIn('after_event_id="$next_after_event_id"', command)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_TIMEOUT_SETTLED_SEEN=", command)
        self.assertIn('[ "$audio_play_timeout_settled_result" -ne 0 ]', command)

    def test_sensor_sweep_exposes_focused_camera_media_mode(self) -> None:
        args = sensor_sweep_args()
        args.media_playback_only = False
        args.media_mode = "camera-only"

        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_sensor_sweep(args)

        command = docker_run.call_args.args[1]
        self.assertIn('media_mode="camera-only"', command)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_MEDIA_MODE=$media_mode", command)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_SKIPPED=1", command)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED=1", command)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OUTPUT_BYTES=", command)
        self.assertIn(
            "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_FIRMWARE_BUSY_SEEN=",
            command,
        )
        self.assertIn(
            "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_CAMERA_FAILED_SEEN=",
            command,
        )

    def test_sensor_sweep_exposes_focused_audio_capture_media_mode(self) -> None:
        args = sensor_sweep_args()
        args.media_playback_only = False
        args.media_mode = "audio-capture-only"

        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_sensor_sweep(args)

        command = docker_run.call_args.args[1]
        self.assertIn('media_mode="audio-capture-only"', command)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_SKIPPED=1", command)
        self.assertIn("STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OUTPUT_BYTES=", command)
        self.assertIn(
            "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_FIRMWARE_BUSY_SEEN=",
            command,
        )
        self.assertIn("STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED=1", command)

    def test_sensor_sweep_legacy_playback_only_flag_overrides_media_mode(self) -> None:
        args = sensor_sweep_args()
        args.media_playback_only = True
        args.media_mode = "camera-only"

        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_sensor_sweep(args)

        command = docker_run.call_args.args[1]
        self.assertIn('media_mode="playback-only"', command)

    def test_media_overlap_matrix_requires_standard_capabilities(self) -> None:
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_media_overlap_matrix(
                media_overlap_args()
            )

        command = docker_run.call_args.args[1]
        self.assertIn("STACKCHAN_MEDIA_OVERLAP_STANDARD_READY=", command)
        self.assertIn('"audio_playback","audio_capture","camera_snapshot"', command)
        self.assertIn("STACKCHAN_MEDIA_OVERLAP_ABORTED_PROFILE_OR_CONNECTION=1", command)
        self.assertNotIn("STACKCHAN_SENSOR_SWEEP_MEDIA_MODE", command)

    def test_media_overlap_matrix_runs_intentional_overlap_cases(self) -> None:
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_media_overlap_matrix(
                media_overlap_args()
            )

        command = docker_run.call_args.args[1]
        camera_index = command.index("=== camera-overlap ===")
        playback_index = command.index("=== audio-playback-overlap non-wait ===")
        playback_wait_index = command.index("=== audio-playback wait baseline ===")
        capture_index = command.index("=== audio-capture-overlap ===")
        self.assertLess(camera_index, playback_index)
        self.assertLess(playback_index, playback_wait_index)
        self.assertLess(playback_wait_index, capture_index)
        self.assertIn(
            "classify_json CAMERA_OVERLAP_SECOND",
            command,
        )
        self.assertIn("classify_json CAMERA_DURING_AUDIO_CAPTURE", command)
        self.assertIn("classify_json CAMERA_AFTER_AUDIO_PLAY_NOWAIT", command)


if __name__ == "__main__":
    unittest.main()
