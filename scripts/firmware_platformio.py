from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_DIR = "firmware/m5stackchan-microros"
DEFAULT_ENV = "stackchan-cores3"
STACKCHAN_MSGS = ROOT / "ros" / "stackchan_msgs"
EXTRA_PACKAGES = ROOT / FIRMWARE_DIR / "extra_packages"

UV_PLATFORMIO = [
    "uv",
    "run",
    "--no-project",
    "--with",
    "platformio",
    "--with",
    "pip",
    "--with",
    "pyyaml",
    "--with",
    "catkin-pkg",
    "--with",
    "lark-parser",
    "--with",
    "empy==3.3.4",
    "--with",
    "colcon-common-extensions",
    "--with",
    "importlib-resources",
    "platformio",
]


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "build":
        calibration_flags = calibration_maintenance_build_flags(args, parser)
        command = [
            "run",
            "-d",
            FIRMWARE_DIR,
            "-e",
            args.environment,
        ]
        platformio_config = None
        if calibration_flags:
            platformio_config = write_platformio_config(None, False, calibration_flags)
            command.extend(["-c", str(platformio_config)])
        try:
            return run_platformio(command)
        finally:
            if platformio_config is not None:
                platformio_config.unlink(missing_ok=True)

    if args.command == "upload":
        calibration_flags = calibration_maintenance_build_flags(args, parser)
        command = [
            "run",
            "-d",
            FIRMWARE_DIR,
            "-e",
            args.environment,
            "-t",
            "upload",
            "--upload-port",
            args.port,
        ]
        upload_config = None
        if args.upload_speed or args.no_stub or calibration_flags:
            upload_config = write_platformio_config(
                args.upload_speed,
                args.no_stub,
                calibration_flags,
            )
            command.extend(["-c", str(upload_config)])
        try:
            return run_platformio(command)
        finally:
            if upload_config is not None:
                upload_config.unlink(missing_ok=True)

    if args.command == "monitor":
        return run_platformio(
            [
                "device",
                "monitor",
                "-d",
                FIRMWARE_DIR,
                "-e",
                args.environment,
                "--port",
                args.port,
                "--baud",
                str(args.baud),
            ]
        )

    parser.error(f"unknown command: {args.command}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="firmware_platformio",
        description=(
            "Run firmware PlatformIO tasks through uv with the Python packages "
            "required by micro_ros_platformio."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build firmware with PlatformIO.")
    build.add_argument(
        "-e",
        "--environment",
        default=DEFAULT_ENV,
        help=f"PlatformIO environment to build (default: {DEFAULT_ENV}).",
    )
    add_calibration_maintenance_arguments(build)

    upload = subparsers.add_parser("upload", help="Upload firmware with PlatformIO.")
    upload.add_argument(
        "--port",
        required=True,
        help="Serial port to upload to, for example COM3 or /dev/ttyACM0.",
    )
    upload.add_argument(
        "-e",
        "--environment",
        default=DEFAULT_ENV,
        help=f"PlatformIO environment to upload (default: {DEFAULT_ENV}).",
    )
    upload.add_argument(
        "--upload-speed",
        type=int,
        help="Override PlatformIO upload speed.",
    )
    upload.add_argument(
        "--no-stub",
        action="store_true",
        help="Pass --no-stub to esptool through PlatformIO upload_flags.",
    )
    add_calibration_maintenance_arguments(upload)

    monitor = subparsers.add_parser(
        "monitor",
        help="Open the PlatformIO serial monitor.",
    )
    monitor.add_argument(
        "--port",
        required=True,
        help="Serial port to monitor, for example COM3 or /dev/ttyACM0.",
    )
    monitor.add_argument(
        "-e",
        "--environment",
        default=DEFAULT_ENV,
        help=f"PlatformIO environment to monitor (default: {DEFAULT_ENV}).",
    )
    monitor.add_argument(
        "--baud",
        type=int,
        default=921600,
        help="Serial monitor baud rate (default: 921600).",
    )

    return parser


def add_calibration_maintenance_arguments(parser: argparse.ArgumentParser) -> None:
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--calibration-maintenance-seed",
        action="store_true",
        help=(
            "Build a one-off operator maintenance firmware that writes a "
            "validated calibration seed to firmware NVS on boot."
        ),
    )
    action.add_argument(
        "--calibration-maintenance-reset",
        action="store_true",
        help=(
            "Build a one-off operator maintenance firmware that removes the "
            "calibration record from firmware NVS on boot."
        ),
    )
    parser.add_argument(
        "--confirm-calibration-maintenance",
        action="store_true",
        help=(
            "Required with calibration maintenance seed/reset to acknowledge "
            "the operator-only NVS write/reset path."
        ),
    )
    parser.add_argument(
        "--calibration-home-x",
        type=int,
        default=0,
        help="Seed home X angle in degrees, bounded by firmware safety limits.",
    )
    parser.add_argument(
        "--calibration-home-y",
        type=int,
        default=0,
        help="Seed home Y angle in degrees, bounded by firmware safety limits.",
    )
    parser.add_argument(
        "--calibration-correction-x",
        type=int,
        default=0,
        help="Seed X correction in degrees, bounded by firmware safety limits.",
    )
    parser.add_argument(
        "--calibration-correction-y",
        type=int,
        default=0,
        help="Seed Y correction in degrees, bounded by firmware safety limits.",
    )


def calibration_maintenance_build_flags(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> list[str]:
    if not getattr(args, "calibration_maintenance_seed", False) and not getattr(
        args,
        "calibration_maintenance_reset",
        False,
    ):
        return []

    if not getattr(args, "confirm_calibration_maintenance", False):
        parser.error(
            "--confirm-calibration-maintenance is required with calibration "
            "maintenance seed/reset"
        )

    if getattr(args, "calibration_maintenance_reset", False):
        return [
            "-D STACKCHAN_CALIBRATION_MAINTENANCE_ENABLE=1",
            "-D STACKCHAN_CALIBRATION_MAINTENANCE_RESET=1",
        ]

    calibration_ranges = {
        "calibration_home_x": (-45, 45),
        "calibration_home_y": (-30, 30),
        "calibration_correction_x": (-30, 30),
        "calibration_correction_y": (-30, 30),
    }
    for name, (minimum, maximum) in calibration_ranges.items():
        value = getattr(args, name)
        if value < minimum or value > maximum:
            parser.error(
                f"--{name.replace('_', '-')} must be between {minimum} and {maximum}"
            )

    corrected_x = args.calibration_home_x + args.calibration_correction_x
    corrected_y = args.calibration_home_y + args.calibration_correction_y
    if corrected_x < -45 or corrected_x > 45:
        parser.error("calibration home X plus correction X must stay between -45 and 45")
    if corrected_y < -30 or corrected_y > 30:
        parser.error("calibration home Y plus correction Y must stay between -30 and 30")

    return [
        "-D STACKCHAN_CALIBRATION_MAINTENANCE_ENABLE=1",
        "-D STACKCHAN_CALIBRATION_MAINTENANCE_SEED=1",
        f"-D STACKCHAN_CALIBRATION_SEED_HOME_X={args.calibration_home_x}",
        f"-D STACKCHAN_CALIBRATION_SEED_HOME_Y={args.calibration_home_y}",
        f"-D STACKCHAN_CALIBRATION_SEED_CORRECTION_X={args.calibration_correction_x}",
        f"-D STACKCHAN_CALIBRATION_SEED_CORRECTION_Y={args.calibration_correction_y}",
    ]


def run_platformio(args: list[str]) -> int:
    sync_stackchan_msgs()
    patch_microros_platformio_meta()
    env = os.environ.copy()
    env["PIP_CONSTRAINT"] = str(ROOT / "scripts" / "firmware_pip_constraints.txt")
    completed = subprocess.run(
        UV_PLATFORMIO + args,
        cwd=ROOT,
        env=env,
        check=False,
    )
    return int(completed.returncode)


def write_platformio_config(
    upload_speed: int | None,
    no_stub: bool,
    extra_build_flags: list[str],
) -> Path:
    source = ROOT / FIRMWARE_DIR / "platformio.ini"
    lines = source.read_text().splitlines()
    output: list[str] = []
    inserted_upload_speed = upload_speed is None
    inserted_upload_flags = not no_stub
    inserted_build_flags = not extra_build_flags
    in_target_env = False
    in_target_build_flags = False
    for line in lines:
        stripped = line.strip()
        if (
            in_target_build_flags
            and stripped
            and not line.startswith((" ", "\t"))
        ):
            for flag in extra_build_flags:
                output.append(f"    {flag}")
            inserted_build_flags = True
            in_target_build_flags = False
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_target_env:
                if in_target_build_flags:
                    for flag in extra_build_flags:
                        output.append(f"    {flag}")
                    inserted_build_flags = True
                    in_target_build_flags = False
                if not inserted_build_flags:
                    output.append("build_flags =")
                    for flag in extra_build_flags:
                        output.append(f"    {flag}")
                    inserted_build_flags = True
                if not inserted_upload_speed:
                    output.append(f"upload_speed = {upload_speed}")
                    inserted_upload_speed = True
                if not inserted_upload_flags:
                    output.append("upload_flags = --no-stub")
                    inserted_upload_flags = True
            in_target_env = stripped == f"[env:{DEFAULT_ENV}]"
        if in_target_env and stripped.startswith("upload_speed"):
            if not inserted_upload_speed:
                output.append(f"upload_speed = {upload_speed}")
                inserted_upload_speed = True
            continue
        if in_target_env and stripped.startswith("upload_flags"):
            if not inserted_upload_flags:
                output.append("upload_flags = --no-stub")
                inserted_upload_flags = True
            continue
        if in_target_env and stripped.startswith("build_flags"):
            output.append(line)
            in_target_build_flags = True
            continue
        output.append(line)
    if in_target_env:
        if in_target_build_flags:
            for flag in extra_build_flags:
                output.append(f"    {flag}")
            inserted_build_flags = True
        if not inserted_build_flags:
            output.append("build_flags =")
            for flag in extra_build_flags:
                output.append(f"    {flag}")
        if not inserted_upload_speed:
            output.append(f"upload_speed = {upload_speed}")
        if not inserted_upload_flags:
            output.append("upload_flags = --no-stub")

    handle = tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        suffix=".ini",
        prefix="stackchan-platformio-",
    )
    with handle:
        handle.write("\n".join(output))
        handle.write("\n")
    return Path(handle.name)


def sync_stackchan_msgs() -> None:
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
    refresh_microros_cache_if_needed(fingerprint)


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


def refresh_microros_cache_if_needed(fingerprint: str) -> None:
    marker = EXTRA_PACKAGES / ".stackchan_msgs.sha256"
    libdeps = ROOT / FIRMWARE_DIR / ".pio" / "libdeps"
    if (
        marker.exists()
        and marker.read_text().strip() == fingerprint
        and microros_cache_has_stackchan_msgs(libdeps)
    ):
        return

    if not libdeps.exists():
        marker.write_text(f"{fingerprint}\n")
        return

    for micro_ros in libdeps.glob("*/micro_ros_platformio"):
        remove_tree(micro_ros / "build")
    marker.write_text(f"{fingerprint}\n")


def patch_microros_platformio_meta() -> None:
    libdeps = ROOT / FIRMWARE_DIR / ".pio" / "libdeps"
    if not libdeps.exists():
        return
    for meta in libdeps.glob("*/micro_ros_platformio/metas/colcon.meta"):
        data = json.loads(meta.read_text())
        cmake_args = data["names"]["rmw_microxrcedds"]["cmake-args"]
        patched_args = [
            "-DRMW_UXRCE_MAX_SERVICES=3"
            if arg.startswith("-DRMW_UXRCE_MAX_SERVICES=")
            else arg
            for arg in cmake_args
        ]
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
    if not path.exists():
        return

    for attempt in range(5):
        try:
            shutil.rmtree(path, onerror=make_writable_and_retry)
        except OSError:
            pass
        if not path.exists():
            return
        if os.name == "nt":
            env = os.environ.copy()
            env["STACKCHAN_REMOVE_PATH"] = str(path)
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "$p = $env:STACKCHAN_REMOVE_PATH; "
                        "if ($p) { "
                        "Remove-Item -LiteralPath $p -Recurse -Force "
                        "-ErrorAction SilentlyContinue "
                        "}"
                    ),
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            if not path.exists():
                return
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "$p = $env:STACKCHAN_REMOVE_PATH; "
                        "if ($p -and [System.IO.Directory]::Exists($p)) { "
                        "try { [System.IO.Directory]::Delete($p, $true) } catch { } "
                        "}"
                    ),
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            if not path.exists():
                return
        if attempt < 4:
            time.sleep(0.5)

    raise RuntimeError(f"failed to remove micro-ROS build cache: {path}")


def make_writable_and_retry(function, path: str, _exc_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    try:
        function(path)
    except OSError:
        pass


def ensure_microros_build_cache_path(path: Path) -> None:
    root = ROOT.resolve()
    resolved = path.resolve(strict=False)
    relative = resolved.relative_to(root)
    expected_prefix = Path(FIRMWARE_DIR) / ".pio" / "libdeps"
    if not relative.parts[: len(expected_prefix.parts)] == expected_prefix.parts:
        raise RuntimeError(f"refusing to remove path outside firmware libdeps: {path}")
    parts = relative.parts
    if "micro_ros_platformio" not in parts:
        raise RuntimeError(f"refusing to remove non-micro-ROS cache path: {path}")
    micro_ros_index = parts.index("micro_ros_platformio")
    if len(parts) <= micro_ros_index + 1 or parts[micro_ros_index + 1] != "build":
        raise RuntimeError(f"refusing to remove non-build micro-ROS path: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
