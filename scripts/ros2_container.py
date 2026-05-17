from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "/workspaces/codex-stackchan-bridge"
DEFAULT_IMAGE = "codex-stackchan-ros2:jazzy"
ROS_BUILD_COMMAND = (
    "source /opt/ros/jazzy/setup.bash && "
    "colcon build --packages-select stackchan_msgs stackchan_bridge"
)
ROS_SMOKE_COMMAND = (
    f"{ROS_BUILD_COMMAND} && "
    "source install/setup.bash && "
    "python3 scripts/ros2_bridge_smoke.py"
)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    image = args.image or os.environ.get("STACKCHAN_ROS2_IMAGE") or DEFAULT_IMAGE

    if args.command == "build-image":
        return run(["docker", "build", "-f", ".devcontainer/Dockerfile", "-t", image, "."])
    if args.command == "build":
        return docker_run(image, ROS_BUILD_COMMAND)
    if args.command == "smoke":
        command = (
            "source /opt/ros/jazzy/setup.bash && "
            "source install/setup.bash && "
            "python3 scripts/ros2_bridge_smoke.py"
            if args.skip_build
            else ROS_SMOKE_COMMAND
        )
        return docker_run(image, command)
    if args.command == "shell":
        return docker_run(image, "bash", interactive=True)

    parser.error(f"unknown command: {args.command}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ros2_container",
        description="Run the repository ROS 2 Jazzy environment in Docker.",
    )
    parser.add_argument(
        "--image",
        help=f"Docker image tag to use (default: {DEFAULT_IMAGE}).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("build-image", help="Build the ROS 2 Jazzy Docker image.")
    subparsers.add_parser("build", help="Build stackchan ROS packages in Docker.")

    smoke = subparsers.add_parser(
        "smoke",
        help="Build ROS packages and run the no-device bridge smoke test.",
    )
    smoke.add_argument(
        "--skip-build",
        action="store_true",
        help="Run only the smoke test against an existing install/ workspace.",
    )

    subparsers.add_parser("shell", help="Open an interactive shell in the container.")
    return parser


def docker_run(image: str, command: str, *, interactive: bool = False) -> int:
    docker_args = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{ROOT}:{WORKSPACE}",
        "-w",
        WORKSPACE,
    ]
    if interactive:
        docker_args.append("-it")
    docker_args.append(image)
    if interactive:
        docker_args.append(command)
    else:
        docker_args.extend(["bash", "-lc", command])
    return run(docker_args)


def run(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
