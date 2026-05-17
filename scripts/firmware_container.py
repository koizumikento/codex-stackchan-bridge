from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "/workspaces/codex-stackchan-bridge"
DEFAULT_IMAGE = "codex-stackchan-firmware:platformio"
FIRMWARE_DIR = "firmware/m5stackchan-microros"
DEFAULT_ENV = "stackchan-cores3"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    image = args.image or os.environ.get("STACKCHAN_FIRMWARE_IMAGE") or DEFAULT_IMAGE

    if args.command == "build-image":
        return run(
            [
                "docker",
                "build",
                "-f",
                ".devcontainer/Dockerfile.firmware",
                "-t",
                image,
                ".",
            ]
        )
    if args.command == "build":
        environment = args.environment or DEFAULT_ENV
        return docker_run(
            image,
            f"pio run -d {FIRMWARE_DIR} -e {environment}",
        )
    if args.command == "shell":
        return docker_run(image, "bash", interactive=True)

    parser.error(f"unknown command: {args.command}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="firmware_container",
        description="Run firmware PlatformIO tasks in Docker.",
    )
    parser.add_argument(
        "--image",
        help=f"Docker image tag to use (default: {DEFAULT_IMAGE}).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "build-image",
        help="Build the firmware PlatformIO Docker image.",
    )

    build = subparsers.add_parser(
        "build",
        help="Run PlatformIO build-only check in Docker.",
    )
    build.add_argument(
        "-e",
        "--environment",
        default=DEFAULT_ENV,
        help=f"PlatformIO environment to build (default: {DEFAULT_ENV}).",
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
