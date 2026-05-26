from __future__ import annotations

import argparse
import unittest

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


if __name__ == "__main__":
    unittest.main()
