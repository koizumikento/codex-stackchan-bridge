from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_DIR = "firmware/m5stackchan-microros"
DEFAULT_ENV = "stackchan-cores3"
STACKCHAN_MSGS = ROOT / "ros" / "stackchan_msgs"
EXTRA_PACKAGES = ROOT / FIRMWARE_DIR / "extra_packages"
BUILD_MANIFEST = "stackchan-firmware-build.json"
UPLOAD_MANIFEST = "stackchan-firmware-last-upload.json"

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

    if args.command == "plan":
        extra_build_flags = firmware_build_flags(args, parser)
        return run_plan(args, extra_build_flags)

    if args.command == "build":
        extra_build_flags = firmware_build_flags(args, parser)
        command = [
            "run",
            "-d",
            FIRMWARE_DIR,
            "-e",
            args.environment,
        ]
        platformio_config = None
        if extra_build_flags:
            platformio_config = write_platformio_config(None, False, extra_build_flags)
            command.extend(["-c", str(platformio_config)])
        try:
            result = run_platformio(command)
            if result == 0:
                write_build_manifest(args.environment, extra_build_flags)
            return result
        finally:
            if platformio_config is not None:
                platformio_config.unlink(missing_ok=True)

    if args.command == "upload":
        extra_build_flags = firmware_build_flags(args, parser)
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
        if args.upload_speed or args.no_stub or extra_build_flags:
            upload_config = write_platformio_config(
                args.upload_speed,
                args.no_stub,
                extra_build_flags,
            )
            command.extend(["-c", str(upload_config)])
        try:
            result = run_platformio(command)
            if result == 0:
                write_build_manifest(args.environment, extra_build_flags)
                write_upload_manifest(args.environment, extra_build_flags, args.port)
            return result
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

    plan = subparsers.add_parser(
        "plan",
        help="Report whether firmware build/upload work appears necessary.",
    )
    plan.add_argument(
        "-e",
        "--environment",
        default=DEFAULT_ENV,
        help=f"PlatformIO environment to inspect (default: {DEFAULT_ENV}).",
    )
    plan.add_argument(
        "--port",
        help=(
            "Optional serial port used to decide whether the last successful "
            "upload marker matches this device."
        ),
    )
    plan.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable plan output.",
    )
    add_microros_diagnostic_arguments(plan)
    add_calibration_maintenance_arguments(plan)

    build = subparsers.add_parser("build", help="Build firmware with PlatformIO.")
    build.add_argument(
        "-e",
        "--environment",
        default=DEFAULT_ENV,
        help=f"PlatformIO environment to build (default: {DEFAULT_ENV}).",
    )
    add_microros_diagnostic_arguments(build)
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
    add_microros_diagnostic_arguments(upload)
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


def add_microros_diagnostic_arguments(parser: argparse.ArgumentParser) -> None:
    profile = parser.add_mutually_exclusive_group()
    profile.add_argument(
        "--microros-minimal-bringup",
        action="store_true",
        help=(
            "Build a temporary diagnostic firmware that initializes only the "
            "micro-ROS status publisher. This isolates transport/status "
            "publishing from optional services, actions, and telemetry entities."
        ),
    )
    profile.add_argument(
        "--microros-board-init-bringup",
        action="store_true",
        help=(
            "Build a temporary diagnostic firmware that enables selected board "
            "initialization stages before the status-only micro-ROS loop."
        ),
    )
    profile.add_argument(
        "--microros-core-command-bringup",
        action="store_true",
        help=(
            "Build a temporary diagnostic firmware that initializes the status "
            "publisher plus core face, LED, motion, and pose services while "
            "skipping optional events, media actions, and raw telemetry."
        ),
    )
    profile.add_argument(
        "--microros-core-raw-telemetry-bringup",
        action="store_true",
        help=(
            "Build a temporary diagnostic firmware that initializes the core "
            "command profile plus raw telemetry publishers, while still "
            "skipping media actions and audio chunk transport."
        ),
    )
    profile.add_argument(
        "--microros-core-audio-chunk-bringup",
        action="store_true",
        help=(
            "Build a temporary diagnostic firmware that extends the core raw "
            "telemetry profile with the audio chunk publisher/subscriber only."
        ),
    )
    profile.add_argument(
        "--microros-core-capture-audio-bringup",
        action="store_true",
        help=(
            "Build a temporary diagnostic firmware that extends the core raw "
            "telemetry profile with the capture-audio action and chunk publisher."
        ),
    )
    profile.add_argument(
        "--microros-core-capture-camera-bringup",
        action="store_true",
        help=(
            "Build a temporary diagnostic firmware that extends the core raw "
            "telemetry profile with the capture-camera action."
        ),
    )
    profile.add_argument(
        "--microros-core-play-audio-bringup",
        action="store_true",
        help=(
            "Build a temporary diagnostic firmware that extends the core raw "
            "telemetry profile with the play-audio action and chunk subscriber."
        ),
    )
    profile.add_argument(
        "--sensor-input-diagnostics",
        action="store_true",
        help=(
            "Build a firmware-only serial monitor diagnostic for K151 touch, "
            "proximity, light, and power reads. Do not attach the micro-ROS "
            "Agent to the same COM port while this profile is running."
        ),
    )
    profile.add_argument(
        "--motion-diagnostics",
        action="store_true",
        help=(
            "Build a diagnostic firmware that emits bounded motion target/raw "
            "summaries as device events. This is safe to use with the "
            "micro-ROS Agent because it does not write to the serial monitor."
        ),
    )
    parser.add_argument(
        "--board-init-stage",
        type=int,
        choices=range(0, 15),
        metavar="0..14",
        default=0,
        help=(
            "Stage for --microros-board-init-bringup: 0=status only, "
            "1=M5.begin, 2=IO expander, 3=servo UART, 4=servo read, "
            "5=touch, 6=IMU probe, 7=power monitor, 8=LTR553, 9=NFC, "
            "10=IR, 11=audio probes, 12=camera, 13=calibration/servo "
            "health, 14=neutral face."
        ),
    )


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


def firmware_build_flags(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> list[str]:
    flags = calibration_maintenance_build_flags(args, parser)
    if getattr(args, "microros_minimal_bringup", False):
        flags.append("-D STACKCHAN_MICROROS_MINIMAL_BRINGUP=1")
    if getattr(args, "microros_board_init_bringup", False):
        flags.append("-D STACKCHAN_MICROROS_BOARD_INIT_BRINGUP=1")
        flags.append(f"-D STACKCHAN_MICROROS_BOARD_INIT_STAGE={args.board_init_stage}")
    elif getattr(args, "board_init_stage", 0) != 0:
        parser.error("--board-init-stage requires --microros-board-init-bringup")
    if getattr(args, "microros_core_command_bringup", False):
        flags.append("-D STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP=1")
    if getattr(args, "microros_core_raw_telemetry_bringup", False):
        flags.append("-D STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP=1")
        flags.append("-D STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP=1")
    if getattr(args, "microros_core_audio_chunk_bringup", False):
        flags.append("-D STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP=1")
        flags.append("-D STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP=1")
        flags.append("-D STACKCHAN_MICROROS_CORE_AUDIO_CHUNK_BRINGUP=1")
    if getattr(args, "microros_core_capture_audio_bringup", False):
        flags.append("-D STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP=1")
        flags.append("-D STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP=1")
        flags.append("-D STACKCHAN_MICROROS_CORE_CAPTURE_AUDIO_BRINGUP=1")
    if getattr(args, "microros_core_capture_camera_bringup", False):
        flags.append("-D STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP=1")
        flags.append("-D STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP=1")
        flags.append("-D STACKCHAN_MICROROS_CORE_CAPTURE_CAMERA_BRINGUP=1")
    if getattr(args, "microros_core_play_audio_bringup", False):
        flags.append("-D STACKCHAN_MICROROS_CORE_COMMAND_BRINGUP=1")
        flags.append("-D STACKCHAN_MICROROS_CORE_RAW_TELEMETRY_BRINGUP=1")
        flags.append("-D STACKCHAN_MICROROS_CORE_PLAY_AUDIO_BRINGUP=1")
    if getattr(args, "sensor_input_diagnostics", False):
        flags.append("-D STACKCHAN_SERIAL_DIAGNOSTICS=1")
        flags.append("-D STACKCHAN_SENSOR_INPUT_DIAGNOSTICS=1")
    if getattr(args, "motion_diagnostics", False):
        flags.append("-D STACKCHAN_MOTION_DIAGNOSTICS=1")
    return flags


def run_plan(args: argparse.Namespace, extra_build_flags: list[str]) -> int:
    fingerprint = firmware_source_fingerprint(args.environment, extra_build_flags)
    artifact = firmware_artifact(args.environment)
    build_manifest = read_json(firmware_build_manifest_path(args.environment))
    upload_manifest = read_json(firmware_upload_manifest_path(args.environment))
    build_current = (
        artifact.exists()
        and build_manifest.get("fingerprint") == fingerprint
        and build_manifest.get("environment") == args.environment
        and build_manifest.get("extra_build_flags") == extra_build_flags
    )
    upload_current = False
    upload_status = "unknown"
    if args.port:
        upload_current = (
            build_current
            and upload_manifest.get("fingerprint") == fingerprint
            and upload_manifest.get("environment") == args.environment
            and upload_manifest.get("port") == args.port
        )
        upload_status = "current" if upload_current else "upload_recommended"

    reasons: list[str] = []
    if not artifact.exists():
        reasons.append("firmware artifact is missing")
    if not build_current and artifact.exists():
        reasons.append("firmware sources or build flags differ from the last build marker")
    if args.port and not upload_current:
        reasons.append("last successful upload marker is missing or does not match this port/fingerprint")
    if not reasons:
        reasons.append("build artifact and optional upload marker are current")

    plan = {
        "environment": args.environment,
        "port": args.port,
        "artifact": str(artifact.relative_to(ROOT)),
        "artifact_exists": artifact.exists(),
        "fingerprint": fingerprint,
        "extra_build_flags": extra_build_flags,
        "build_required": not build_current,
        "upload_status": upload_status,
        "upload_recommended": bool(args.port and not upload_current),
        "reasons": reasons,
    }
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(f"environment: {plan['environment']}")
        if args.port:
            print(f"port: {args.port}")
        print(f"artifact: {plan['artifact']}")
        print(f"build_required: {str(plan['build_required']).lower()}")
        print(f"upload_status: {upload_status}")
        for reason in reasons:
            print(f"- {reason}")
    return 0


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


def firmware_artifact(environment: str) -> Path:
    return ROOT / FIRMWARE_DIR / ".pio" / "build" / environment / "firmware.bin"


def firmware_build_manifest_path(environment: str) -> Path:
    return ROOT / FIRMWARE_DIR / ".pio" / "build" / environment / BUILD_MANIFEST


def firmware_upload_manifest_path(environment: str) -> Path:
    return ROOT / FIRMWARE_DIR / ".pio" / "build" / environment / UPLOAD_MANIFEST


def write_build_manifest(environment: str, extra_build_flags: list[str]) -> None:
    fingerprint = firmware_source_fingerprint(environment, extra_build_flags)
    manifest = {
        "environment": environment,
        "extra_build_flags": extra_build_flags,
        "fingerprint": fingerprint,
        "artifact": str(firmware_artifact(environment).relative_to(ROOT)),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = firmware_build_manifest_path(environment)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def write_upload_manifest(
    environment: str,
    extra_build_flags: list[str],
    port: str,
) -> None:
    fingerprint = firmware_source_fingerprint(environment, extra_build_flags)
    manifest = {
        "environment": environment,
        "extra_build_flags": extra_build_flags,
        "fingerprint": fingerprint,
        "port": port,
        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = firmware_upload_manifest_path(environment)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def firmware_source_fingerprint(
    environment: str,
    extra_build_flags: list[str],
) -> str:
    digest = hashlib.sha256()
    digest.update(f"environment={environment}".encode("utf-8"))
    digest.update(b"\0")
    for flag in extra_build_flags:
        digest.update(flag.encode("utf-8"))
        digest.update(b"\0")
    for base in (ROOT / FIRMWARE_DIR, STACKCHAN_MSGS):
        for path in sorted(base.rglob("*")):
            if not path.is_file() or should_skip_firmware_fingerprint_file(path):
                continue
            relative = path.relative_to(ROOT).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def should_skip_firmware_fingerprint_file(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    parts = set(relative.parts)
    if parts.intersection(
        {".pio", "build", "install", "log", "tests", "__pycache__", ".pytest_cache"},
    ):
        return True
    if relative.parts[: len(Path(FIRMWARE_DIR, "extra_packages").parts)] == Path(
        FIRMWARE_DIR,
        "extra_packages",
    ).parts:
        return True
    return path.suffix in {".md", ".pyc", ".tmp"}


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
        patched_args = []
        clients_seen = False
        history_seen = False
        stream_history_input_seen = False
        stream_history_output_seen = False
        wait_sets_seen = False
        guard_condition_seen = False
        topic_name_max_seen = False
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
            elif arg.startswith("-DRMW_UXRCE_MAX_WAIT_SETS="):
                patched_args.append("-DRMW_UXRCE_MAX_WAIT_SETS=8")
                wait_sets_seen = True
            elif arg.startswith("-DRMW_UXRCE_MAX_GUARD_CONDITION="):
                patched_args.append("-DRMW_UXRCE_MAX_GUARD_CONDITION=8")
                guard_condition_seen = True
            elif arg.startswith("-DRMW_UXRCE_TOPIC_NAME_MAX_LENGTH="):
                patched_args.append("-DRMW_UXRCE_TOPIC_NAME_MAX_LENGTH=96")
                topic_name_max_seen = True
            elif arg.startswith("-DUCLIENT_CUSTOM_TRANSPORT_MTU=") or arg.startswith(
                "-DUXR_CONFIG_CUSTOM_TRANSPORT_MTU="
            ):
                continue
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
        if not wait_sets_seen:
            patched_args.append("-DRMW_UXRCE_MAX_WAIT_SETS=8")
        if not guard_condition_seen:
            patched_args.append("-DRMW_UXRCE_MAX_GUARD_CONDITION=8")
        if not topic_name_max_seen:
            patched_args.append("-DRMW_UXRCE_TOPIC_NAME_MAX_LENGTH=96")
        data["names"]["rmw_microxrcedds"]["cmake-args"] = patched_args
        client_config = data["names"].setdefault("microxrcedds_client", {})
        client_args = client_config.setdefault("cmake-args", [])
        patched_client_args = []
        client_mtu_seen = False
        for arg in client_args:
            if arg.startswith("-DUCLIENT_CUSTOM_TRANSPORT_MTU="):
                patched_client_args.append("-DUCLIENT_CUSTOM_TRANSPORT_MTU=1024")
                client_mtu_seen = True
            else:
                patched_client_args.append(arg)
        if not client_mtu_seen:
            patched_client_args.append("-DUCLIENT_CUSTOM_TRANSPORT_MTU=1024")
        client_config["cmake-args"] = patched_client_args
        if (
            patched_args == cmake_args
            and patched_client_args == client_args
            and "microxrcedds_client" in data["names"]
        ):
            continue
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

    remove_path = windows_extended_path(path) if os.name == "nt" else str(path)
    for attempt in range(5):
        try:
            shutil.rmtree(remove_path, onerror=make_writable_and_retry)
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


def windows_extended_path(path: Path) -> str:
    resolved = str(path.resolve(strict=False))
    if resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved[2:]
    return "\\\\?\\" + resolved


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
