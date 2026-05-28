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
        say_voice="default",
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

    def test_bridge_smoke_preserves_early_firmware_ready_observation(self) -> None:
        with mock.patch.object(
            microros_agent_container,
            "docker_run",
            return_value=0,
        ) as docker_run:
            microros_agent_container.run_tcp_pty_bridge_smoke(bridge_smoke_args())

        command = docker_run.call_args.args[1]
        self.assertIn("firmware_ready_seen=0", command)
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
        self.assertIn("STACKCHAN_TTS_SPEED_SCALE:-1.6", command)
        self.assertIn("STACKCHAN_TTS_PRE_PHONEME_LENGTH:-0.03", command)
        self.assertIn("STACKCHAN_TTS_POST_PHONEME_LENGTH:-0.03", command)
        self.assertIn("STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD:-256", command)
        self.assertIn("STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS:-30.0", command)


if __name__ == "__main__":
    unittest.main()
