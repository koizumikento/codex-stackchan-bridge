from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "/workspaces/codex-stackchan-bridge"
DEFAULT_IMAGE = "codex-stackchan-firmware:platformio"
FIRMWARE_DIR = "firmware/m5stackchan-microros"
DEFAULT_ENV = "stackchan-cores3"
STACKCHAN_MSGS = ROOT / "ros" / "stackchan_msgs"
EXTRA_PACKAGES = ROOT / FIRMWARE_DIR / "extra_packages"
PIP_CONSTRAINTS = "scripts/firmware_pip_constraints.txt"


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
    needs_cache_refresh = sync_stackchan_msgs()
    patch_microros_platformio_meta()
    if needs_cache_refresh and not interactive:
        command = (
            f"rm -rf {WORKSPACE}/{FIRMWARE_DIR}/.pio/libdeps/*/micro_ros_platformio/build "
            f"&& {command}"
        )
    docker_args = [
        "docker",
        "run",
        "--rm",
        "-e",
        f"PIP_CONSTRAINT={WORKSPACE}/{PIP_CONSTRAINTS}",
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


def sync_stackchan_msgs() -> bool:
    fingerprint = stackchan_msgs_fingerprint()
    target = EXTRA_PACKAGES / "stackchan_msgs"
    EXTRA_PACKAGES.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    ignore = shutil.ignore_patterns(
        "build",
        "install",
        "log",
        "__pycache__",
        "*.pyc",
        ".pytest_cache",
    )
    shutil.copytree(STACKCHAN_MSGS, target, ignore=ignore)
    return microros_cache_needs_refresh(fingerprint)


def stackchan_msgs_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(STACKCHAN_MSGS.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(STACKCHAN_MSGS).as_posix()
        if relative.startswith(("build/", "install/", "log/")):
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    for path in (
        ROOT / FIRMWARE_DIR / "platformio.ini",
        ROOT / FIRMWARE_DIR / "microros_stackchan.meta",
    ):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def microros_cache_needs_refresh(fingerprint: str) -> bool:
    marker = EXTRA_PACKAGES / ".stackchan_msgs.sha256"
    libdeps = ROOT / FIRMWARE_DIR / ".pio" / "libdeps"
    if (
        marker.exists()
        and marker.read_text().strip() == fingerprint
        and microros_cache_has_stackchan_msgs(libdeps)
    ):
        return False

    marker.write_text(f"{fingerprint}\n")
    return libdeps.exists()


def patch_microros_platformio_meta() -> None:
    libdeps = ROOT / FIRMWARE_DIR / ".pio" / "libdeps"
    if not libdeps.exists():
        return
    for meta in libdeps.glob("*/micro_ros_platformio/metas/colcon.meta"):
        data = json.loads(meta.read_text())
        cmake_args = data["names"]["rmw_microxrcedds"]["cmake-args"]
        patched_args = []
        clients_seen = False
        history_seen = False
        stream_history_input_seen = False
        stream_history_output_seen = False
        services_seen = False
        publishers_seen = False
        subscriptions_seen = False
        for arg in cmake_args:
            if arg.startswith("-DRMW_UXRCE_MAX_SERVICES="):
                patched_args.append("-DRMW_UXRCE_MAX_SERVICES=16")
                services_seen = True
            elif arg.startswith("-DRMW_UXRCE_MAX_PUBLISHERS="):
                patched_args.append("-DRMW_UXRCE_MAX_PUBLISHERS=20")
                publishers_seen = True
            elif arg.startswith("-DRMW_UXRCE_MAX_SUBSCRIPTIONS="):
                patched_args.append("-DRMW_UXRCE_MAX_SUBSCRIPTIONS=4")
                subscriptions_seen = True
            elif arg.startswith("-DRMW_UXRCE_MAX_CLIENTS="):
                patched_args.append("-DRMW_UXRCE_MAX_CLIENTS=8")
                clients_seen = True
            elif arg.startswith("-DRMW_UXRCE_MAX_HISTORY="):
                patched_args.append("-DRMW_UXRCE_MAX_HISTORY=16")
                history_seen = True
            elif arg.startswith("-DRMW_UXRCE_STREAM_HISTORY_INPUT="):
                patched_args.append("-DRMW_UXRCE_STREAM_HISTORY_INPUT=8")
                stream_history_input_seen = True
            elif arg.startswith("-DRMW_UXRCE_STREAM_HISTORY_OUTPUT="):
                patched_args.append("-DRMW_UXRCE_STREAM_HISTORY_OUTPUT=8")
                stream_history_output_seen = True
            else:
                patched_args.append(arg)
        if not services_seen:
            patched_args.append("-DRMW_UXRCE_MAX_SERVICES=16")
        if not publishers_seen:
            patched_args.append("-DRMW_UXRCE_MAX_PUBLISHERS=20")
        if not subscriptions_seen:
            patched_args.append("-DRMW_UXRCE_MAX_SUBSCRIPTIONS=4")
        if not clients_seen:
            patched_args.append("-DRMW_UXRCE_MAX_CLIENTS=8")
        if not history_seen:
            patched_args.append("-DRMW_UXRCE_MAX_HISTORY=16")
        if not stream_history_input_seen:
            patched_args.append("-DRMW_UXRCE_STREAM_HISTORY_INPUT=8")
        if not stream_history_output_seen:
            patched_args.append("-DRMW_UXRCE_STREAM_HISTORY_OUTPUT=8")
        if patched_args == cmake_args:
            continue
        data["names"]["rmw_microxrcedds"]["cmake-args"] = patched_args
        meta.write_text(json.dumps(data, indent=4) + "\n")


def microros_cache_has_stackchan_msgs(libdeps: Path) -> bool:
    micro_ros_dirs = list(libdeps.glob("*/micro_ros_platformio"))
    if not micro_ros_dirs:
        return True
    return all(
        (micro_ros / "build" / "libmicroros" / "include" / "stackchan_msgs").exists()
        and (micro_ros / "build" / "libmicroros" / "libmicroros.a").exists()
        for micro_ros in micro_ros_dirs
    )


def remove_tree(path: Path) -> None:
    ensure_microros_build_cache_path(path)
    shutil.rmtree(path, ignore_errors=True)
    if path.exists() and os.name == "nt":
        env = os.environ.copy()
        env["STACKCHAN_REMOVE_PATH"] = str(path)
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "$p = $env:STACKCHAN_REMOVE_PATH; "
                    "if ($p) { Remove-Item -LiteralPath $p -Recurse -Force }"
                ),
            ],
            cwd=ROOT,
            env=env,
            check=False,
        )


def ensure_microros_build_cache_path(path: Path) -> None:
    root = ROOT.resolve()
    resolved = path.resolve(strict=False)
    relative = resolved.relative_to(root)
    expected_prefix = Path(FIRMWARE_DIR) / ".pio" / "libdeps"
    if not relative.parts[: len(expected_prefix.parts)] == expected_prefix.parts:
        raise RuntimeError(f"refusing to remove path outside firmware libdeps: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
