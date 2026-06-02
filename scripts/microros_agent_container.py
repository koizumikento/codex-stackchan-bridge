from __future__ import annotations

import argparse
import os
import shlex
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "/workspaces/codex-stackchan-bridge"
DEFAULT_IMAGE = "codex-stackchan-microros-agent:jazzy"
DEFAULT_DOCKERFILE = ".devcontainer/Dockerfile.microros-agent"
DEFAULT_BAUD = 921600
DEFAULT_TCP_HOST = "host.docker.internal"
DEFAULT_TCP_PORT = 11411
DEFAULT_PTY = "/tmp/stackchan-tty"
DEFAULT_EVENT_TOPIC = "/stackchan/default/device/events"
DEFAULT_PUBLIC_EVENT_TOPIC = "/stackchan/default/events"
DEFAULT_EVENT_TYPE = "stackchan_msgs/msg/StackChanEvent"
DEFAULT_SAY_NATURALNESS_CHECK_TEXT = "詳しく話すよ。中で分けて待ちを減らすよ。"
ENV_PASSTHROUGH = (
    "STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES",
    "STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES",
    "STACKCHAN_AUDIO_PLAYBACK_LOAD_CHUNK_BYTES",
    "STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES",
    "STACKCHAN_AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS",
    "STACKCHAN_AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS",
    "STACKCHAN_AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS",
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC",
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC",
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC",
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS",
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC",
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES",
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_ANCHOR_REPEATS",
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_ANCHOR_SERVICE_AFTER_PASSES",
    "STACKCHAN_AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES",
    "STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOADED_MAX_DECODED_BYTES",
    "STACKCHAN_AUDIO_PLAYBACK_BUFFER_MAX_CHUNKS",
    "STACKCHAN_AUDIO_PLAYBACK_PULL_ONLY",
    "STACKCHAN_TTS_LOADED_PLAYBACK",
    "STACKCHAN_TTS_LOADED_ADPCM",
    "STACKCHAN_TTS_LOADED_TRANSPORT",
    "STACKCHAN_TTS_LOADED_SPLIT_OVERSIZE",
    "STACKCHAN_TTS_LOADED_AUDIO_SPLIT_TARGET_DECODED_BYTES",
    "STACKCHAN_TTS_PROGRESSIVE_TEXT_SEGMENTS",
    "STACKCHAN_TTS_PROGRESSIVE_TEXT_SEGMENT_MAX_CHARS",
    "STACKCHAN_TTS_ENDPOINT",
    "STACKCHAN_TTS_POST_PHONEME_LENGTH",
    "STACKCHAN_TTS_PRE_PHONEME_LENGTH",
    "STACKCHAN_TTS_SAMPLE_RATE",
    "STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS",
    "STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD",
    "STACKCHAN_TTS_SPEED_SCALE",
)
ROS_BUILD_STAMP = f"{WORKSPACE}/install/.stackchan_ros_build_stamp"
ROS_MSGS_BUILD_STAMP = f"{WORKSPACE}/install/.stackchan_ros_stackchan_msgs_build_stamp"
ROS_BRIDGE_BUILD_STAMP = (
    f"{WORKSPACE}/install/.stackchan_ros_stackchan_bridge_build_stamp"
)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "build-image":
        return run(
            [
                "docker",
                "build",
                "-f",
                DEFAULT_DOCKERFILE,
                "-t",
                args.image,
                ".",
            ]
        )
    if args.command == "tcp-pty":
        return run_tcp_pty(args)
    if args.command == "tcp-pty-event-echo":
        return run_tcp_pty_event_echo(args)
    if args.command == "tcp-pty-sensor-sweep":
        return run_tcp_pty_sensor_sweep(args)
    if args.command == "tcp-pty-media-overlap-matrix":
        return run_tcp_pty_media_overlap_matrix(args)
    if args.command == "tcp-pty-loaded-audio-probe":
        return run_tcp_pty_loaded_audio_probe(args)
    if args.command == "tcp-pty-bridge-smoke":
        return run_tcp_pty_bridge_smoke(args)
    if args.command == "serial":
        return run_serial(args)

    parser.error(f"unknown command: {args.command}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="microros_agent_container",
        description="Run the micro-ROS Agent container for StackChan bring-up.",
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"Agent image to use (default: {DEFAULT_IMAGE}).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "build-image",
        help="Build the repo micro-ROS Agent image with ABI-aligned ROS 2 deps.",
    )

    tcp_pty = subparsers.add_parser(
        "tcp-pty",
        help="Connect to a host serial TCP bridge and expose it to Agent as a PTY.",
    )
    tcp_pty.add_argument("--tcp-host", default=DEFAULT_TCP_HOST)
    tcp_pty.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    tcp_pty.add_argument("--pty", default=DEFAULT_PTY)
    tcp_pty.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    tcp_pty.add_argument("--verbose", type=int, default=6)

    tcp_pty_echo = subparsers.add_parser(
        "tcp-pty-event-echo",
        help=(
            "Run Agent and ros2 topic echo in the same container against a "
            "host serial TCP bridge."
        ),
    )
    tcp_pty_echo.add_argument("--tcp-host", default=DEFAULT_TCP_HOST)
    tcp_pty_echo.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    tcp_pty_echo.add_argument("--pty", default=DEFAULT_PTY)
    tcp_pty_echo.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    tcp_pty_echo.add_argument("--verbose", type=int, default=6)
    tcp_pty_echo.add_argument("--topic", default=DEFAULT_EVENT_TOPIC)
    tcp_pty_echo.add_argument("--message-type", default=DEFAULT_EVENT_TYPE)
    tcp_pty_echo.add_argument("--timeout", type=int, default=35)

    tcp_pty_sweep = subparsers.add_parser(
        "tcp-pty-sensor-sweep",
        help=(
            "Run Agent, stackchan_bridge, and topic/CLI probes for K151 "
            "sensor, telemetry, event, and redaction validation."
        ),
    )
    tcp_pty_sweep.add_argument("--tcp-host", default=DEFAULT_TCP_HOST)
    tcp_pty_sweep.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    tcp_pty_sweep.add_argument("--pty", default=DEFAULT_PTY)
    tcp_pty_sweep.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    tcp_pty_sweep.add_argument("--verbose", type=int, default=4)
    tcp_pty_sweep.add_argument("--timeout", type=int, default=6)
    tcp_pty_sweep.add_argument(
        "--stimulus-window-seconds",
        type=int,
        default=0,
        help=(
            "Optional manual stimulus window before event classification. Use it "
            "to touch/release the touch surface, move near/far from the proximity "
            "sensor, change light, pick up/tilt/shake the device, present/remove "
            "NFC tags, or press IR remote buttons while the Agent and bridge are "
            "connected."
        ),
    )
    tcp_pty_sweep.add_argument(
        "--media-audio-capture-seconds",
        type=float,
        default=0.02,
        help="Audio capture duration used by the hardware media smoke.",
    )
    tcp_pty_sweep.add_argument(
        "--media-audio-playback-duration-ms",
        type=float,
        default=20.0,
        help="Playback sine duration used by the hardware media smoke.",
    )
    tcp_pty_sweep.add_argument(
        "--media-audio-playback-frequency",
        type=float,
        default=440.0,
        help="Playback sine frequency used by the hardware media smoke.",
    )
    tcp_pty_sweep.add_argument(
        "--media-audio-playback-amplitude",
        type=int,
        default=1200,
        help="Playback sine amplitude used by the hardware media smoke.",
    )
    tcp_pty_sweep.add_argument(
        "--media-audio-playback-wait",
        action="store_true",
        help=(
            "Pass --wait to stackchanctl audio play so the smoke reports the "
            "firmware-owned terminal playback result instead of CLI handoff."
        ),
    )
    tcp_pty_sweep.add_argument(
        "--media-camera-quality",
        type=int,
        default=50,
        help="JPEG quality used by the hardware camera smoke.",
    )
    tcp_pty_sweep.add_argument(
        "--media-mode",
        choices=("all", "playback-only", "audio-capture-only", "camera-only"),
        default="all",
        help=(
            "Select which hardware media smoke checks to run. Use focused modes "
            "when validating camera or microphone behavior after a prior media "
            "action may still be settling."
        ),
    )
    tcp_pty_sweep.add_argument(
        "--media-playback-only",
        action="store_true",
        help=(
            "Run only the audio playback portion of the hardware media smoke. "
            "Use for focused speaker/playback diagnostics so a timed-out "
            "playback action is not followed by capture or camera commands."
        ),
    )
    tcp_pty_sweep.add_argument(
        "--skip-media-smoke",
        action="store_true",
        help=(
            "Skip audio playback, audio capture, and camera smoke checks. Use "
            "for focused sensor/event sweeps where media behavior is not under "
            "test."
        ),
    )
    tcp_pty_sweep.add_argument(
        "--skip-build",
        action="store_true",
        help="Use the existing install/ workspace instead of rebuilding ROS packages.",
    )
    add_ros_smoke_build_arguments(tcp_pty_sweep)

    tcp_pty_overlap = subparsers.add_parser(
        "tcp-pty-media-overlap-matrix",
        help=(
            "Run intentional media overlap checks against the standard/full "
            "firmware. This validates FIRMWARE_BUSY classification and is not "
            "a focused bring-up smoke."
        ),
    )
    tcp_pty_overlap.add_argument("--tcp-host", default=DEFAULT_TCP_HOST)
    tcp_pty_overlap.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    tcp_pty_overlap.add_argument("--pty", default=DEFAULT_PTY)
    tcp_pty_overlap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    tcp_pty_overlap.add_argument("--verbose", type=int, default=4)
    tcp_pty_overlap.add_argument("--timeout", type=int, default=45)
    tcp_pty_overlap.add_argument("--media-camera-quality", type=int, default=50)
    tcp_pty_overlap.add_argument(
        "--media-audio-capture-seconds",
        type=float,
        default=2.0,
        help="Audio capture duration used for intentional overlap checks.",
    )
    tcp_pty_overlap.add_argument(
        "--media-audio-playback-duration-ms",
        type=float,
        default=250.0,
        help="Playback sine duration used for intentional overlap checks.",
    )
    tcp_pty_overlap.add_argument(
        "--media-audio-playback-frequency",
        type=float,
        default=440.0,
    )
    tcp_pty_overlap.add_argument(
        "--media-audio-playback-amplitude",
        type=int,
        default=1200,
    )
    tcp_pty_overlap.add_argument(
        "--say-text",
        default="",
        help="Optional short text for a say-overlap check. Leave empty to skip TTS.",
    )
    tcp_pty_overlap.add_argument(
        "--skip-build",
        action="store_true",
        help="Use the existing install/ workspace instead of rebuilding ROS packages.",
    )
    add_ros_smoke_build_arguments(tcp_pty_overlap)

    tcp_pty_audio_probe = subparsers.add_parser(
        "tcp-pty-loaded-audio-probe",
        help=(
            "Run Agent and directly probe the firmware LoadAudioChunk service "
            "against a host serial TCP bridge."
        ),
    )
    tcp_pty_audio_probe.add_argument("--tcp-host", default=DEFAULT_TCP_HOST)
    tcp_pty_audio_probe.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    tcp_pty_audio_probe.add_argument("--pty", default=DEFAULT_PTY)
    tcp_pty_audio_probe.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    tcp_pty_audio_probe.add_argument("--verbose", type=int, default=4)
    tcp_pty_audio_probe.add_argument("--timeout", type=int, default=30)
    tcp_pty_audio_probe.add_argument(
        "--chunk-bytes",
        default="32,64,160",
        help="Comma-separated even chunk byte sizes to probe.",
    )
    tcp_pty_audio_probe.add_argument(
        "--total-bytes",
        type=int,
        default=160,
        help="Total silent PCM bytes to load for each chunk size.",
    )
    tcp_pty_audio_probe.add_argument(
        "--chunk-timeout",
        type=float,
        default=5.0,
        help="Seconds to wait for each LoadAudioChunk response.",
    )
    tcp_pty_audio_probe.add_argument(
        "--play-action",
        action="store_true",
        help="After a successful load, send PlayAudio with the same command_id.",
    )
    tcp_pty_audio_probe.add_argument(
        "--skip-build",
        action="store_true",
        help="Use the existing install/ workspace instead of rebuilding ROS packages.",
    )
    add_ros_smoke_build_arguments(tcp_pty_audio_probe)

    tcp_pty_bridge = subparsers.add_parser(
        "tcp-pty-bridge-smoke",
        help=(
            "Run Agent, stackchan_bridge, and stackchanctl in the same container "
            "against a host serial TCP bridge."
        ),
    )
    tcp_pty_bridge.add_argument("--tcp-host", default=DEFAULT_TCP_HOST)
    tcp_pty_bridge.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    tcp_pty_bridge.add_argument("--pty", default=DEFAULT_PTY)
    tcp_pty_bridge.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    tcp_pty_bridge.add_argument("--verbose", type=int, default=6)
    tcp_pty_bridge.add_argument("--timeout", type=int, default=35)
    tcp_pty_bridge.add_argument(
        "--skip-build",
        action="store_true",
        help="Use the existing install/ workspace instead of rebuilding ROS packages.",
    )
    add_ros_smoke_build_arguments(tcp_pty_bridge)
    tcp_pty_bridge.add_argument(
        "--disconnect-check",
        action="store_true",
        help="Stop the Agent after the connected smoke and verify liveness timeout.",
    )
    tcp_pty_bridge.add_argument(
        "--reconnect-check",
        action="store_true",
        help=(
            "After the disconnect check, restart the Agent and verify the bridge "
            "returns to connected."
        ),
    )
    tcp_pty_bridge.add_argument(
        "--disconnect-face-command",
        default="",
        help=(
            "While the Agent is disconnected, try this face command and verify "
            "it is rejected instead of being queued for reconnect."
        ),
    )
    tcp_pty_bridge.add_argument(
        "--face-check",
        default="",
        help="Set this face through stackchanctl and verify observe reports it.",
    )
    tcp_pty_bridge.add_argument(
        "--say-check",
        default="",
        help="Run this text through stackchanctl say with local TTS enabled.",
    )
    tcp_pty_bridge.add_argument(
        "--say-naturalness-check",
        action="store_true",
        help=(
            "Use the current compact detailed-speech listening candidate for "
            "--say-check, with default expression hints when unset."
        ),
    )
    tcp_pty_bridge.add_argument(
        "--say-voice",
        default="default",
        help="Bridge-owned voice profile used by --say-check.",
    )
    tcp_pty_bridge.add_argument(
        "--say-face",
        default="",
        help="Face hint passed to stackchanctl say during --say-check.",
    )
    tcp_pty_bridge.add_argument(
        "--say-motion",
        default="",
        help="Motion hint passed to stackchanctl say during --say-check.",
    )
    tcp_pty_bridge.add_argument(
        "--say-after-face",
        default="",
        help="After-speech face hint passed to stackchanctl say during --say-check.",
    )
    tcp_pty_bridge.add_argument(
        "--say-operator-listening-verdict",
        choices=("unrecorded", "pass", "fail"),
        default="unrecorded",
        help=(
            "Record the human listening verdict for a say check. This does not "
            "change transport checks; use pass only after the operator heard "
            "intelligible, untruncated, natural speech with acceptable waiting."
        ),
    )
    tcp_pty_bridge.add_argument(
        "--say-operator-listening-issue",
        choices=(
            "none",
            "unintelligible",
            "volume",
            "truncation",
            "phrase_chop",
            "wait",
            "expression_timing",
            "other",
        ),
        default="none",
        help=(
            "Bounded issue category for a failed say listening verdict. Use "
            "none with unrecorded/pass, and a specific issue with fail."
        ),
    )
    tcp_pty_bridge.add_argument(
        "--allow-missing-firmware-ready",
        action="store_true",
        help=(
            "Do not fail the smoke when firmware_ready is absent. Use this only "
            "for diagnostic firmware profiles that intentionally skip the "
            "firmware event publisher."
        ),
    )
    tcp_pty_bridge.add_argument(
        "--led-check",
        action="store_true",
        help="Run progress, success, and off LED commands through stackchanctl.",
    )
    tcp_pty_bridge.add_argument(
        "--motion-check",
        default="",
        help="Run this named motion through stackchanctl during the bridge smoke.",
    )
    tcp_pty_bridge.add_argument(
        "--motion-disconnect-check",
        default="",
        help=(
            "Run this named motion, stop the Agent immediately after acceptance, "
            "then verify disconnect and reconnect recovery."
        ),
    )
    tcp_pty_bridge.add_argument(
        "--motion-expected-error",
        default="",
        help=(
            "Treat this structured error code as the expected motion result "
            "instead of requiring command success."
        ),
    )
    tcp_pty_bridge.add_argument(
        "--pose-pan-deg",
        type=float,
        default=None,
        help="Run motion pose with this pan angle during the bridge smoke.",
    )
    tcp_pty_bridge.add_argument(
        "--pose-tilt-deg",
        type=float,
        default=None,
        help="Run motion pose with this tilt angle during the bridge smoke.",
    )
    tcp_pty_bridge.add_argument(
        "--home-check",
        action="store_true",
        help="Run motion home during the bridge smoke and verify pose returns to home.",
    )
    tcp_pty_bridge.add_argument(
        "--soak-seconds",
        type=int,
        default=0,
        help="Keep Agent and bridge running and periodically observe for this many seconds.",
    )
    tcp_pty_bridge.add_argument(
        "--soak-interval-seconds",
        type=int,
        default=30,
        help="Seconds between soak observe checks.",
    )

    serial = subparsers.add_parser(
        "serial",
        help="Run Agent against a Linux serial device directly mounted in Docker.",
    )
    serial.add_argument("--dev", required=True, help="Container serial device path.")
    serial.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    serial.add_argument("--verbose", type=int, default=6)

    return parser


def add_ros_smoke_build_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--clean-ros-build",
        action="store_true",
        help=(
            "Run colcon with --cmake-clean-cache. By default the same-container "
            "smoke uses an incremental symlink install build."
        ),
    )
    parser.add_argument(
        "--allow-stale-install",
        action="store_true",
        help=(
            "Allow --skip-build even when ROS source files are newer than the "
            "last smoke build stamp. Use only for diagnostics."
        ),
    )


def parse_chunk_sizes(raw_value: str) -> list[int]:
    chunk_sizes: list[int] = []
    for part in raw_value.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        value = int(stripped)
        if value <= 0:
            raise ValueError("chunk sizes must be positive")
        if value % 2:
            raise ValueError("chunk sizes must be even PCM byte counts")
        chunk_sizes.append(value)
    if not chunk_sizes:
        raise ValueError("at least one chunk size is required")
    return chunk_sizes


def ros_smoke_setup_script(args: argparse.Namespace) -> str:
    if args.skip_build and args.clean_ros_build:
        raise SystemExit("--clean-ros-build cannot be combined with --skip-build")
    stale_allowed = "1" if args.allow_stale_install else "0"
    clean_arg = "--cmake-clean-cache" if args.clean_ros_build else ""
    clean_build_dirs = "1" if args.clean_ros_build else "0"
    colcon_required = "0" if args.skip_build else "1"
    if args.skip_build:
        build_or_guard_script = f"""
phase_start "skip-build stale install guard" STALE_GUARD
stale_status=0
stale_allowable=0
if [ ! -f {WORKSPACE}/install/setup.bash ]; then
  echo "install/setup.bash is missing; rerun without --skip-build" >&2
  stale_status=1
elif [ ! -f {ROS_MSGS_BUILD_STAMP} ] || [ ! -f {ROS_BRIDGE_BUILD_STAMP} ]; then
  echo "ROS package build stamps are missing; rerun without --skip-build once to create fresh incremental install stamps" >&2
  stale_status=1
  stale_allowable=1
else
  stale_paths=$(find ros/stackchan_msgs \\
    \\( -path '*/__pycache__/*' -o -name '*.pyc' -o -path '*/.pytest_cache/*' \\) -prune \\
    -o -type f -newer {ROS_MSGS_BUILD_STAMP} -print | head -n 20)
  bridge_stale_paths=$(find ros/stackchan_bridge \\
    \\( -path '*/__pycache__/*' -o -name '*.pyc' -o -path '*/.pytest_cache/*' \\) -prune \\
    -o -type f -newer {ROS_BRIDGE_BUILD_STAMP} -print | head -n 20)
  if [ -n "$bridge_stale_paths" ]; then
    stale_paths="${{stale_paths}}${{stale_paths:+
}}$bridge_stale_paths"
  fi
  if [ -n "$stale_paths" ]; then
    echo "ROS sources are newer than the last smoke build stamp; rerun without --skip-build before trusting this smoke:" >&2
    printf '%s\\n' "$stale_paths" >&2
    stale_status=1
    stale_allowable=1
  fi
fi
if [ "$stale_status" -ne 0 ] && [ "$stale_allowable" = "1" ] && [ "{stale_allowed}" = "1" ]; then
  echo "WARNING: continuing with stale install because --allow-stale-install was set" >&2
  stale_status=0
fi
phase_end "$stale_status"
[ "$stale_status" -eq 0 ] || exit "$stale_status"
"""
    else:
        build_or_guard_script = f"""
phase_start "ROS package build" ROS_BUILD
if [ "{clean_build_dirs}" = "1" ] || [ ! -f {ROS_BUILD_STAMP} ]; then
  echo "resetting ROS package build dirs before symlink-install transition"
  rm -rf build/stackchan_msgs build/stackchan_bridge
fi
msgs_changed=0
bridge_changed=0
if [ "{clean_build_dirs}" = "1" ] || [ ! -f {ROS_MSGS_BUILD_STAMP} ]; then
  msgs_changed=1
elif find ros/stackchan_msgs \\
  \\( -path '*/__pycache__/*' -o -name '*.pyc' -o -path '*/.pytest_cache/*' \\) -prune \\
  -o -type f -newer {ROS_MSGS_BUILD_STAMP} -print -quit | grep -q .; then
  msgs_changed=1
fi
if [ "{clean_build_dirs}" = "1" ] || [ ! -f {ROS_BRIDGE_BUILD_STAMP} ]; then
  bridge_changed=1
elif find ros/stackchan_bridge \\
  \\( -path '*/__pycache__/*' -o -name '*.pyc' -o -path '*/.pytest_cache/*' \\) -prune \\
  -o -type f -newer {ROS_BRIDGE_BUILD_STAMP} -print -quit | grep -q .; then
  bridge_changed=1
fi
packages=""
if [ "$msgs_changed" = "1" ]; then
  packages="stackchan_msgs stackchan_bridge"
elif [ "$bridge_changed" = "1" ]; then
  packages="stackchan_bridge"
fi
if [ -z "$packages" ]; then
  echo "ROS package sources are unchanged; keeping existing symlink install"
  build_status=0
else
  echo "building ROS packages: $packages"
  colcon build --base-paths ros/stackchan_msgs ros/stackchan_bridge --packages-select $packages --symlink-install {clean_arg}
  build_status=$?
fi
if [ "$build_status" -eq 0 ]; then
  mkdir -p {WORKSPACE}/install
  if [ "$msgs_changed" = "1" ]; then
    touch {ROS_MSGS_BUILD_STAMP}
  fi
  if [ "$msgs_changed" = "1" ] || [ "$bridge_changed" = "1" ]; then
    touch {ROS_BRIDGE_BUILD_STAMP}
  fi
  touch {ROS_BUILD_STAMP}
fi
phase_end "$build_status"
[ "$build_status" -eq 0 ] || exit "$build_status"
"""
    return f"""
phase_times_file=/tmp/stackchan-smoke-phase-times.log
: > "$phase_times_file"
phase_start_epoch=0
phase_slug=""
phase_start() {{
  phase_label="$1"
  phase_slug="$2"
  phase_start_epoch=$(date +%s)
  echo "--- phase: $phase_label ---"
}}
phase_end() {{
  phase_result="$1"
  phase_end_epoch=$(date +%s)
  phase_seconds=$((phase_end_epoch - phase_start_epoch))
  echo "STACKCHAN_SMOKE_PHASE_${{phase_slug}}_SECONDS=$phase_seconds" | tee -a "$phase_times_file"
  return "$phase_result"
}}
print_phase_summary() {{
  echo "--- smoke phase timing summary ---"
  cat "$phase_times_file" 2>/dev/null || true
}}

phase_start "dependency/setup check" SETUP_CHECK
source /opt/ros/jazzy/setup.bash
source /uros_ws/install/local_setup.bash
setup_status=0
for command_name in socat python3 ros2; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "missing required command '$command_name'; rebuild the Agent smoke image with: uv run --no-project python scripts/microros_agent_container.py build-image" >&2
    setup_status=1
  fi
done
if [ "{colcon_required}" = "1" ] && ! command -v colcon >/dev/null 2>&1; then
  echo "missing required command 'colcon'; rebuild the Agent smoke image with: uv run --no-project python scripts/microros_agent_container.py build-image" >&2
  setup_status=1
fi
phase_end "$setup_status"
[ "$setup_status" -eq 0 ] || exit "$setup_status"

{build_or_guard_script}
source {WORKSPACE}/install/setup.bash
"""


def run_tcp_pty(args: argparse.Namespace) -> int:
    command = f"""
set -e
command -v socat >/dev/null 2>&1 || {{
  echo "missing required command 'socat'; rebuild the Agent smoke image with: uv run --no-project python scripts/microros_agent_container.py build-image" >&2
  exit 1
}}
source /opt/ros/jazzy/setup.bash
source /uros_ws/install/local_setup.bash
socat -d -d pty,raw,echo=0,link={args.pty} tcp:{args.tcp_host}:{args.tcp_port} &
socat_pid=$!
trap 'kill $socat_pid 2>/dev/null || true' EXIT
for i in $(seq 1 50); do
  [ -e {args.pty} ] && break
  sleep 0.1
done
ls -l {args.pty}
ros2 run micro_ros_agent micro_ros_agent serial --dev {args.pty} -b {args.baud} -v{args.verbose}
"""
    return docker_run(args.image, command)


def run_tcp_pty_event_echo(args: argparse.Namespace) -> int:
    command = f"""
set -e
command -v socat >/dev/null 2>&1 || {{
  echo "missing required command 'socat'; rebuild the Agent smoke image with: uv run --no-project python scripts/microros_agent_container.py build-image" >&2
  exit 1
}}
source /opt/ros/jazzy/setup.bash
source /uros_ws/install/local_setup.bash
source {WORKSPACE}/install/setup.bash
socat -d -d pty,raw,echo=0,link={args.pty} tcp:{args.tcp_host}:{args.tcp_port} 2>/tmp/stackchan-socat.log &
socat_pid=$!
agent_pid=
echo_pid=
trap 'kill $echo_pid $agent_pid $socat_pid 2>/dev/null || true' EXIT
for i in $(seq 1 50); do
  [ -e {args.pty} ] && break
  sleep 0.1
done
timeout {args.timeout} ros2 topic echo --once {args.topic} {args.message_type} --qos-reliability reliable >/tmp/stackchan-event-echo.log 2>&1 &
echo_pid=$!
sleep 0.2
ros2 run micro_ros_agent micro_ros_agent serial --dev {args.pty} -b {args.baud} -v{args.verbose} >/tmp/stackchan-agent.log 2>&1 &
agent_pid=$!
wait $echo_pid
echo_result=$?
cat /tmp/stackchan-event-echo.log || true
echo STACKCHAN_EVENT_ECHO_EXIT=$echo_result
echo "--- micro-ROS Agent tail ---"
tail -n 120 /tmp/stackchan-agent.log || true
echo "--- socat tail ---"
tail -n 60 /tmp/stackchan-socat.log || true
exit $echo_result
"""
    return docker_run(
        args.image,
        command,
        mount_workspace=True,
        workdir=WORKSPACE,
    )


def run_tcp_pty_sensor_sweep(args: argparse.Namespace) -> int:
    setup_script = ros_smoke_setup_script(args)
    playback_duration_ms = max(1.0, float(args.media_audio_playback_duration_ms))
    playback_frequency = max(1.0, float(args.media_audio_playback_frequency))
    playback_amplitude = min(30000, max(1, int(args.media_audio_playback_amplitude)))
    media_mode = (
        "playback-only"
        if args.media_playback_only
        else getattr(args, "media_mode", "all")
    )
    audio_play_wait_arg = "--wait" if args.media_audio_playback_wait else ""
    command = f"""
set +e
{setup_script}
export PYTHONPATH={WORKSPACE}/apps/stackchanctl/src:$PYTHONPATH
bridge_node={WORKSPACE}/install/stackchan_bridge/lib/stackchan_bridge/stackchan_bridge_node
result=0
socat -d -d pty,raw,echo=0,link={args.pty} tcp:{args.tcp_host}:{args.tcp_port} 2>/tmp/stackchan-socat.log &
socat_pid=$!
agent_pid=
bridge_pid=
cleanup() {{
  cleanup_start=$(date +%s)
  kill $bridge_pid $agent_pid $socat_pid 2>/dev/null || true
  cleanup_end=$(date +%s)
  echo "STACKCHAN_SMOKE_PHASE_TEARDOWN_SECONDS=$((cleanup_end - cleanup_start))" | tee -a "$phase_times_file"
  print_phase_summary
}}
trap cleanup EXIT
phase_start "serial PTY setup" PTY_SETUP
for i in $(seq 1 50); do
  [ -e {args.pty} ] && break
  sleep 0.1
done
phase_end 0
phase_start "bridge startup" BRIDGE_STARTUP
"$bridge_node" >/tmp/stackchan-bridge.log 2>&1 &
bridge_pid=$!
for i in $(seq 1 80); do
  ros2 service list | grep -q '^/stackchan/default/cmd/get_status$' && break
  sleep 0.25
done
phase_end 0
phase_start "micro-ROS Agent startup" AGENT_STARTUP
ros2 run micro_ros_agent micro_ros_agent serial --dev {args.pty} -b {args.baud} -v{args.verbose} >/tmp/stackchan-agent.log 2>&1 &
agent_pid=$!
sleep 6
phase_end 0
phase_start "smoke checks" SMOKE_CHECKS

run_topic_once() {{
  slug="$1"
  topic="$2"
  message_type="$3"
  out="/tmp/stackchan-sensor-$slug.log"
  echo "--- topic $slug $topic ---"
  timeout {args.timeout} ros2 topic echo --once "$topic" "$message_type" >"$out" 2>&1
  topic_result=$?
  cat "$out" || true
  echo "STACKCHAN_SENSOR_SWEEP_TOPIC_${{slug}}_EXIT=$topic_result"
  if [ "$topic_result" -eq 0 ]; then
    echo "STACKCHAN_SENSOR_SWEEP_TOPIC_${{slug}}_SAMPLE_SEEN=1"
  else
    echo "STACKCHAN_SENSOR_SWEEP_TOPIC_${{slug}}_SAMPLE_SEEN=0"
  fi
}}

run_live_stimulus_capture() {{
  window="$1"
  if [ "$window" -le 0 ]; then
    return
  fi
  echo "--- live stimulus topic capture (${{window}}s) ---"
  echo "Apply touch, proximity, light, power, IMU, NFC, and IR/remote stimuli now. Normal logs/events will be redaction-scanned afterwards."
  touch_live=/tmp/stackchan-live-touch.log
  proximity_live=/tmp/stackchan-live-proximity.log
  light_live=/tmp/stackchan-live-light.log
  power_live=/tmp/stackchan-live-power.log
  events_live=/tmp/stackchan-live-events.log
  rm -f "$touch_live" "$proximity_live" "$light_live" "$power_live" "$events_live"

  timeout "$window" ros2 topic echo /stackchan/default/device/touch/state stackchan_msgs/msg/TouchState >"$touch_live" 2>&1 &
  touch_pid=$!
  timeout "$window" ros2 topic echo /stackchan/default/device/proximity/raw stackchan_msgs/msg/ProximityRaw >"$proximity_live" 2>&1 &
  proximity_pid=$!
  timeout "$window" ros2 topic echo /stackchan/default/device/light/raw stackchan_msgs/msg/LightRaw >"$light_live" 2>&1 &
  light_pid=$!
  timeout "$window" ros2 topic echo /stackchan/default/device/power/status stackchan_msgs/msg/PowerStatus >"$power_live" 2>&1 &
  power_pid=$!
  timeout "$window" ros2 topic echo /stackchan/default/device/events stackchan_msgs/msg/StackChanEvent >"$events_live" 2>&1 &
  events_pid=$!

  wait "$touch_pid" "$proximity_pid" "$light_pid" "$power_pid" "$events_pid" 2>/dev/null || true

  echo "--- live touch samples ---"
  cat "$touch_live" || true
  echo "--- live proximity samples ---"
  cat "$proximity_live" || true
  echo "--- live light samples ---"
  cat "$light_live" || true
  echo "--- live power samples ---"
  cat "$power_live" || true
  echo "--- live event samples ---"
  cat "$events_live" || true

  grep -Eq 'zone_mask: [1-9]|- [1-9][0-9]*' "$touch_live"
  touch_active_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_LIVE_TOUCH_ACTIVE_SEEN=$([ "$touch_active_result" -eq 0 ] && echo 1 || echo 0)"
  grep -Eq 'raw: [1-9][0-9]*|signal: 0[.][0-9]*[1-9]' "$proximity_live"
  proximity_nonzero_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_LIVE_PROXIMITY_NONZERO_SEEN=$([ "$proximity_nonzero_result" -eq 0 ] && echo 1 || echo 0)"
  grep -Eq 'raw: [1-9][0-9]*|illuminance_lux: [1-9][0-9]*|illuminance_lux: 0[.][0-9]*[1-9]' "$light_live"
  light_nonzero_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_LIVE_LIGHT_NONZERO_SEEN=$([ "$light_nonzero_result" -eq 0 ] && echo 1 || echo 0)"
  grep -Eq 'voltage_v:|power_source:' "$power_live"
  power_sample_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_LIVE_POWER_SAMPLE_SEEN=$([ "$power_sample_result" -eq 0 ] && echo 1 || echo 0)"
  grep -Eq 'event_name:' "$events_live"
  event_sample_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_LIVE_EVENT_SAMPLE_SEEN=$([ "$event_sample_result" -eq 0 ] && echo 1 || echo 0)"
}}

run_power_status() {{
  echo "--- stackchanctl power status ---"
  power_output=""
  power_result=1
  for i in $(seq 1 8); do
    power_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} power status --json 2>&1)
    power_result=$?
    [ "$power_result" -eq 0 ] && break
    sleep 1
  done
  printf '%s\n' "$power_output"
  echo "STACKCHAN_SENSOR_SWEEP_POWER_STATUS_EXIT=$power_result"
  printf '%s\n' "$power_output" | grep -q '"code":'
  power_error_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_POWER_STATUS_STRUCTURED_ERROR_SEEN=$([ "$power_error_result" -eq 0 ] && echo 1 || echo 0)"
}}

json_command_id() {{
  python3 -c 'import json,sys; raw=sys.stdin.read(); start=raw.find("{{"); end=raw.rfind("}}"); data=json.loads(raw[start:end+1]) if start >= 0 and end >= start else dict(); print(data.get("command_id") or (data.get("metadata") or dict()).get("command_id") or "")' 2>/dev/null
}}

json_cursor() {{
  python3 -c 'import json,sys; raw=sys.stdin.read(); start=raw.find("{{"); end=raw.rfind("}}"); data=json.loads(raw[start:end+1]) if start >= 0 and end >= start else dict(); print(data.get("cursor") or "")' 2>/dev/null
}}

media_action_terminal_seen() {{
  command_id="$1"
  event_name="$2"
  python3 -c 'import json,sys; cmd=sys.argv[1]; name=sys.argv[2]; raw=sys.stdin.read(); start=raw.find("{{"); end=raw.rfind("}}"); data=json.loads(raw[start:end+1]) if start >= 0 and end >= start else dict(); stages=("goal_failed","goal_succeeded","goal_response_busy","result_ready","result_response_sent"); events=data.get("events") or list(); sys.exit(0 if any(e.get("command_id") == cmd and e.get("event_name") == name and ((e.get("payload") or dict()).get("stage") in stages) for e in events) else 1)' "$command_id" "$event_name"
}}

wait_media_action_terminal() {{
  command_id="$1"
  event_name="$2"
  timeout_sec="$3"
  after_event_id="${{4:-}}"
  consumer_id="media-settle-$command_id"
  if [ -z "$command_id" ]; then
    echo "STACKCHAN_SENSOR_SWEEP_MEDIA_SETTLE_COMMAND_ID_PRESENT=0"
    return 1
  fi
  echo "STACKCHAN_SENSOR_SWEEP_MEDIA_SETTLE_COMMAND_ID_PRESENT=1"
  deadline=$(( $(date +%s) + timeout_sec ))
  while [ "$(date +%s)" -le "$deadline" ]; do
    if [ -n "$after_event_id" ]; then
      settle_events_output=$(python3 -m stackchanctl --backend bridge --timeout 5 --source "$consumer_id" events next --after "$after_event_id" --json 2>&1)
    else
      settle_events_output=$(python3 -m stackchanctl --backend bridge --timeout 5 --source "$consumer_id" events next --json 2>&1)
    fi
    printf '%s\n' "$settle_events_output" | media_action_terminal_seen "$command_id" "$event_name"
    settle_seen=$?
    if [ "$settle_seen" -eq 0 ]; then
      echo "STACKCHAN_SENSOR_SWEEP_MEDIA_SETTLE_TERMINAL_SEEN=1"
      return 0
    fi
    next_after_event_id=$(printf '%s\n' "$settle_events_output" | json_cursor)
    if [ -n "$next_after_event_id" ]; then
      after_event_id="$next_after_event_id"
    else
      sleep 1
    fi
  done
  echo "STACKCHAN_SENSOR_SWEEP_MEDIA_SETTLE_TERMINAL_SEEN=0"
  return 1
}}

run_media_smoke() {{
  media_mode="{media_mode}"
  echo "STACKCHAN_SENSOR_SWEEP_MEDIA_MODE=$media_mode"
  echo "STACKCHAN_SENSOR_SWEEP_MEDIA_PLAYBACK_ONLY=$([ "$media_mode" = "playback-only" ] && echo 1 || echo 0)"
  mic_wav=$(mktemp /tmp/stackchan-mic-XXXXXX.wav)
  frame_jpg=$(mktemp /tmp/stackchan-frame-XXXXXX.jpg)
  media_active_after_playback=0

  run_audio_play_smoke() {{
    prompt_wav=$(mktemp /tmp/stackchan-prompt-XXXXXX.wav)
    python3 - "$prompt_wav" <<'PY'
import math
import sys
import wave

sample_rate = 16000
duration_ms = {playback_duration_ms}
frequency = {playback_frequency}
amplitude = {playback_amplitude}
sample_count = max(1, int(sample_rate * duration_ms / 1000.0))
samples = bytearray()
for index in range(sample_count):
    value = int(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
    samples.extend(int(value).to_bytes(2, "little", signed=True))
with wave.open(sys.argv[1], "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    wav.writeframes(bytes(samples))
PY

    echo "--- stackchanctl audio play smoke ---"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_SKIPPED=0"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_PROMPT_MS={playback_duration_ms}"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_PROMPT_FREQUENCY={playback_frequency}"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_PROMPT_AMPLITUDE={playback_amplitude}"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_WAIT=$([ -n "{audio_play_wait_arg}" ] && echo 1 || echo 0)"
    audio_play_before_events=$(python3 -m stackchanctl --backend bridge --timeout 5 events list --limit 1 --json 2>&1)
    audio_play_before_event_id=$(printf '%s\n' "$audio_play_before_events" | json_cursor)
    audio_play_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} audio play {audio_play_wait_arg} "$prompt_wav" --json 2>&1)
    audio_play_result=$?
    rm -f "$prompt_wav"
    printf '%s\n' "$audio_play_output"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_EXIT=$audio_play_result"
    audio_play_command_id=$(printf '%s\n' "$audio_play_output" | json_command_id)
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_COMMAND_ID_PRESENT=$([ -n "$audio_play_command_id" ] && echo 1 || echo 0)"
    printf '%s\n' "$audio_play_output" | grep -Eq '"code": *"UNSUPPORTED_FEATURE"'
    audio_play_unsupported_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_UNSUPPORTED_SEEN=$([ "$audio_play_unsupported_result" -eq 0 ] && echo 1 || echo 0)"
    printf '%s\n' "$audio_play_output" | grep -Eq '"code": *"FIRMWARE_BUSY"'
    audio_play_firmware_busy_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_FIRMWARE_BUSY_SEEN=$([ "$audio_play_firmware_busy_result" -eq 0 ] && echo 1 || echo 0)"
    printf '%s\n' "$audio_play_output" | grep -Eq '"ok": *true'
    audio_play_ok_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_OK_SEEN=$([ "$audio_play_ok_result" -eq 0 ] && echo 1 || echo 0)"
    printf '%s\n' "$audio_play_output" | grep -Eqi '"result_state": *"timeout"|"code": *"TIMEOUT"'
    audio_play_timeout_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_TIMEOUT_SEEN=$([ "$audio_play_timeout_result" -eq 0 ] && echo 1 || echo 0)"
    audio_play_settle_result=0
    audio_play_timeout_settled_result=1
    audio_play_settled_result=1
    if [ -n "$audio_play_command_id" ] &&
       [ "$audio_play_unsupported_result" -ne 0 ] &&
       [ "$audio_play_firmware_busy_result" -ne 0 ]; then
      wait_media_action_terminal "$audio_play_command_id" "audio_playback_action" {max(10, int(args.timeout))} "$audio_play_before_event_id"
      audio_play_settle_result=$?
      [ "$audio_play_settle_result" -eq 0 ] && audio_play_settled_result=0
      if [ "$audio_play_timeout_result" -eq 0 ] && [ "$audio_play_settle_result" -eq 0 ]; then
        audio_play_timeout_settled_result=0
      fi
    fi
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_SETTLE_EXIT=$audio_play_settle_result"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_SETTLED_SEEN=$([ "$audio_play_settled_result" -eq 0 ] && echo 1 || echo 0)"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_TIMEOUT_SETTLED_SEEN=$([ "$audio_play_timeout_settled_result" -eq 0 ] && echo 1 || echo 0)"
    if [ "$audio_play_unsupported_result" -ne 0 ] &&
       [ "$audio_play_ok_result" -ne 0 ] &&
       [ "$audio_play_timeout_settled_result" -ne 0 ]; then
      result=1
    fi
    if [ "$audio_play_unsupported_result" -ne 0 ] &&
       [ "$audio_play_firmware_busy_result" -ne 0 ] &&
       [ "$audio_play_settled_result" -ne 0 ]; then
      media_active_after_playback=1
      result=1
    fi
  }}

  run_audio_capture_smoke() {{
    echo "--- stackchanctl audio capture smoke ---"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED=0"
    audio_capture_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} audio capture --seconds {max(0.001, float(args.media_audio_capture_seconds))} --output "$mic_wav" --json 2>&1)
    audio_capture_result=$?
    audio_capture_bytes=$([ -s "$mic_wav" ] && wc -c < "$mic_wav" || echo 0)
    rm -f "$mic_wav"
    printf '%s\n' "$audio_capture_output"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_EXIT=$audio_capture_result"
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OUTPUT_BYTES=$audio_capture_bytes"
    printf '%s\n' "$audio_capture_output" | grep -Eq '"code": *"UNSUPPORTED_FEATURE"'
    audio_capture_unsupported_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_UNSUPPORTED_SEEN=$([ "$audio_capture_unsupported_result" -eq 0 ] && echo 1 || echo 0)"
    printf '%s\n' "$audio_capture_output" | grep -Eq '"code": *"MIC_OVERRUN"'
    audio_capture_mic_overrun_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_MIC_OVERRUN_SEEN=$([ "$audio_capture_mic_overrun_result" -eq 0 ] && echo 1 || echo 0)"
    printf '%s\n' "$audio_capture_output" | grep -Eq '"code": *"FIRMWARE_BUSY"'
    audio_capture_firmware_busy_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_FIRMWARE_BUSY_SEEN=$([ "$audio_capture_firmware_busy_result" -eq 0 ] && echo 1 || echo 0)"
    printf '%s\n' "$audio_capture_output" | grep -Eq '"ok": *true'
    audio_capture_ok_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OK_SEEN=$([ "$audio_capture_ok_result" -eq 0 ] && echo 1 || echo 0)"
    if [ "$audio_capture_unsupported_result" -ne 0 ] &&
       [ "$audio_capture_mic_overrun_result" -ne 0 ] &&
       [ "$audio_capture_ok_result" -ne 0 ]; then
      result=1
    fi
  }}

  run_camera_capture_smoke() {{
    echo "--- stackchanctl camera capture smoke ---"
    echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED=0"
    camera_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} camera capture --output "$frame_jpg" --quality {min(95, max(1, int(args.media_camera_quality)))} --json 2>&1)
    camera_result=$?
    camera_bytes=$([ -s "$frame_jpg" ] && wc -c < "$frame_jpg" || echo 0)
    rm -f "$frame_jpg"
    printf '%s\n' "$camera_output"
    echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_EXIT=$camera_result"
    echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OUTPUT_BYTES=$camera_bytes"
    printf '%s\n' "$camera_output" | grep -Eq '"code": *"UNSUPPORTED_FEATURE"'
    camera_unsupported_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_UNSUPPORTED_SEEN=$([ "$camera_unsupported_result" -eq 0 ] && echo 1 || echo 0)"
    printf '%s\n' "$camera_output" | grep -Eq '"code": *"CAMERA_CAPTURE_FAILED"'
    camera_capture_failed_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_CAMERA_FAILED_SEEN=$([ "$camera_capture_failed_result" -eq 0 ] && echo 1 || echo 0)"
    printf '%s\n' "$camera_output" | grep -Eq '"code": *"FIRMWARE_BUSY"'
    camera_firmware_busy_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_FIRMWARE_BUSY_SEEN=$([ "$camera_firmware_busy_result" -eq 0 ] && echo 1 || echo 0)"
    printf '%s\n' "$camera_output" | grep -Eq '"ok": *true'
    camera_ok_result=$?
    echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=$([ "$camera_ok_result" -eq 0 ] && echo 1 || echo 0)"
    if [ "$camera_unsupported_result" -ne 0 ] &&
       [ "$camera_capture_failed_result" -ne 0 ] &&
       [ "$camera_ok_result" -ne 0 ]; then
      result=1
    fi
  }}

  case "$media_mode" in
    playback-only)
      run_audio_play_smoke
      rm -f "$mic_wav" "$frame_jpg"
      echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED=1"
      echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED_DUE_TO_ACTIVE_MEDIA=0"
      echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED=1"
      echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED_DUE_TO_ACTIVE_MEDIA=0"
      ;;
    audio-capture-only)
      echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_SKIPPED=1"
      run_audio_capture_smoke
      rm -f "$frame_jpg"
      echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED=1"
      echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED_DUE_TO_ACTIVE_MEDIA=0"
      ;;
    camera-only)
      echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_SKIPPED=1"
      rm -f "$mic_wav"
      echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED=1"
      echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED_DUE_TO_ACTIVE_MEDIA=0"
      run_camera_capture_smoke
      ;;
    *)
      run_audio_play_smoke
      if [ "$media_active_after_playback" -eq 1 ]; then
        rm -f "$mic_wav" "$frame_jpg"
        echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED=1"
        echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED_DUE_TO_ACTIVE_MEDIA=1"
        echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED=1"
        echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED_DUE_TO_ACTIVE_MEDIA=1"
      else
        echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED_DUE_TO_ACTIVE_MEDIA=0"
        run_audio_capture_smoke
        echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED_DUE_TO_ACTIVE_MEDIA=0"
        run_camera_capture_smoke
      fi
      ;;
  esac
}}

echo "--- stackchanctl observe ---"
observe_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json 2>&1)
observe_result=$?
printf '%s\n' "$observe_output"
echo "STACKCHAN_SENSOR_SWEEP_OBSERVE_EXIT=$observe_result"
[ "$observe_result" -eq 0 ] || result=1
printf '%s\n' "$observe_output" | grep -Eq '"touch"|"proximity"|"light"|"raw"|"nfc"|"ir"|"audio_payload"|"image_payload"|"pcm"'
observe_raw_result=$?
echo "STACKCHAN_SENSOR_SWEEP_OBSERVE_RAW_TELEMETRY_SEEN=$([ "$observe_raw_result" -eq 0 ] && echo 1 || echo 0)"
[ "$observe_raw_result" -ne 0 ] || result=1

echo "--- stackchan topics ---"
ros2 topic list -t | grep stackchan || true
echo "--- stackchan services ---"
ros2 service list -t | grep stackchan || true

stimulus_window_ran=0
if [ "{max(0, int(args.stimulus_window_seconds))}" -gt 0 ]; then
  stimulus_window_ran=1
  echo "--- manual hardware stimulus window ({max(0, int(args.stimulus_window_seconds))}s) ---"
  run_live_stimulus_capture {max(0, int(args.stimulus_window_seconds))}
fi
echo "STACKCHAN_EVENT_STIMULUS_WINDOW_RAN=$stimulus_window_ran"

run_topic_once "device_touch" "/stackchan/default/device/touch/state" "stackchan_msgs/msg/TouchState"
run_topic_once "public_touch" "/stackchan/default/touch/state" "stackchan_msgs/msg/TouchState"
run_topic_once "device_imu_raw" "/stackchan/default/device/imu/raw" "stackchan_msgs/msg/ImuRaw"
run_topic_once "public_imu_raw" "/stackchan/default/imu/raw" "stackchan_msgs/msg/ImuRaw"
run_topic_once "device_proximity" "/stackchan/default/device/proximity/raw" "stackchan_msgs/msg/ProximityRaw"
run_topic_once "public_proximity" "/stackchan/default/proximity/raw" "stackchan_msgs/msg/ProximityRaw"
run_topic_once "device_light" "/stackchan/default/device/light/raw" "stackchan_msgs/msg/LightRaw"
run_topic_once "public_light" "/stackchan/default/light/raw" "stackchan_msgs/msg/LightRaw"
run_topic_once "device_power" "/stackchan/default/device/power/status" "stackchan_msgs/msg/PowerStatus"
run_topic_once "public_power" "/stackchan/default/power/status" "stackchan_msgs/msg/PowerStatus"
run_power_status
if [ "{1 if args.skip_media_smoke else 0}" -eq 1 ]; then
  echo "--- media smoke skipped ---"
  echo "STACKCHAN_SENSOR_SWEEP_MEDIA_SMOKE_SKIPPED=1"
else
  echo "STACKCHAN_SENSOR_SWEEP_MEDIA_SMOKE_SKIPPED=0"
  run_media_smoke
fi
run_topic_once "device_events" "/stackchan/default/device/events" "stackchan_msgs/msg/StackChanEvent"
run_topic_once "public_events" "/stackchan/default/events" "stackchan_msgs/msg/StackChanEvent"

echo "--- stackchanctl events list ---"
events_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} events list --limit 25 --json 2>&1)
events_result=$?
printf '%s\n' "$events_output"
echo "STACKCHAN_SENSOR_SWEEP_EVENTS_EXIT=$events_result"
[ "$events_result" -eq 0 ] || result=1

classify_event_stimulus() {{
  slug="$1"
  pattern="$2"
  if printf '%s\n' "$events_output" | grep -Eq "$pattern"; then
    echo "STACKCHAN_EVENT_STIMULUS_${{slug}}_STATUS=PASS"
    echo "STACKCHAN_EVENT_STIMULUS_${{slug}}_EVENT_SEEN=1"
  elif [ "$stimulus_window_ran" -eq 0 ]; then
    echo "STACKCHAN_EVENT_STIMULUS_${{slug}}_STATUS=NOT_RUN"
    echo "STACKCHAN_EVENT_STIMULUS_${{slug}}_EVENT_SEEN=0"
  else
    echo "STACKCHAN_EVENT_STIMULUS_${{slug}}_STATUS=UNAVAILABLE"
    echo "STACKCHAN_EVENT_STIMULUS_${{slug}}_EVENT_SEEN=0"
  fi
}}

classify_event_stimulus "BUTTON" '"button_pressed"|"button_released"|"button_held"'
classify_event_stimulus "IMU" '"picked_up"|"placed_down"|"shaken"|"tilted"|"face_up"|"face_down"'
classify_event_stimulus "TOUCH" '"touched"|"touch_released"|"touch_held"'
classify_event_stimulus "PROXIMITY" '"proximity_near"|"proximity_clear"'
classify_event_stimulus "LIGHT" '"light_changed"|"dark_detected"|"bright_detected"'
classify_event_stimulus "POWER" '"battery_low"|"battery_recovered"|"charging_started"|"charging_stopped"|"power_source_changed"|"brownout_risk"|"power_fault"'
classify_event_stimulus "NFC" '"nfc_detected"|"nfc_removed"|"nfc_read_failed"'
classify_event_stimulus "IR" '"remote_button_pressed"|"remote_button_released"|"remote_button_held"|"remote_command_received"|"ir_transmit_started"|"ir_transmit_finished"|"ir_transmit_failed"'

printf '%s\n' "$events_output" | grep -Eq 'nfc_tag_id|tag_id|uid|ir_code|raw_ir|raw_remote|remote_code|pcm|image|jpeg|base64|speech_text|transcript_text'
events_sensitive_result=$?
echo "STACKCHAN_SENSOR_SWEEP_EVENTS_SENSITIVE_PAYLOAD_SEEN=$([ "$events_sensitive_result" -eq 0 ] && echo 1 || echo 0)"
[ "$events_sensitive_result" -ne 0 ] || result=1

echo "--- normal log redaction scan ---"
cat /tmp/stackchan-bridge.log /tmp/stackchan-agent.log /tmp/stackchan-socat.log 2>/dev/null | grep -Ei 'nfc_tag_id|tag_id|uid|ir_code|raw_ir|raw_remote|remote_code|pcm|image|jpeg|base64|speech_text|transcript_text'
log_sensitive_result=$?
echo "STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=$([ "$log_sensitive_result" -eq 0 ] && echo 1 || echo 0)"
[ "$log_sensitive_result" -ne 0 ] || result=1

echo "--- bridge tail ---"
tail -n 120 /tmp/stackchan-bridge.log || true
echo "--- micro-ROS Agent tail ---"
tail -n 120 /tmp/stackchan-agent.log || true
echo "--- socat tail ---"
tail -n 60 /tmp/stackchan-socat.log || true
phase_end "$result"
exit $result
"""
    return docker_run(
        args.image,
        command,
        mount_workspace=True,
        workdir=WORKSPACE,
    )


def run_tcp_pty_media_overlap_matrix(args: argparse.Namespace) -> int:
    setup_script = ros_smoke_setup_script(args)
    capture_seconds = max(0.25, float(args.media_audio_capture_seconds))
    playback_duration_ms = max(20.0, float(args.media_audio_playback_duration_ms))
    playback_frequency = max(1.0, float(args.media_audio_playback_frequency))
    playback_amplitude = min(30000, max(1, int(args.media_audio_playback_amplitude)))
    camera_quality = min(95, max(1, int(args.media_camera_quality)))
    say_text = shlex.quote(str(args.say_text).strip())
    say_enabled = "1" if str(args.say_text).strip() else "0"
    command = f"""
set +e
{setup_script}
export PYTHONPATH={WORKSPACE}/apps/stackchanctl/src:$PYTHONPATH
bridge_node={WORKSPACE}/install/stackchan_bridge/lib/stackchan_bridge/stackchan_bridge_node
result=0
socat -d -d pty,raw,echo=0,link={args.pty} tcp:{args.tcp_host}:{args.tcp_port} 2>/tmp/stackchan-overlap-socat.log &
socat_pid=$!
agent_pid=
bridge_pid=
cleanup() {{
  cleanup_start=$(date +%s)
  kill $bridge_pid $agent_pid $socat_pid 2>/dev/null || true
  cleanup_end=$(date +%s)
  echo "STACKCHAN_MEDIA_OVERLAP_PHASE_TEARDOWN_SECONDS=$((cleanup_end - cleanup_start))" | tee -a "$phase_times_file"
  echo "--- media action gate lines ---"
  grep -E "firmware media action|FIRMWARE_BUSY|camera capture|audio playback|audio capture" /tmp/stackchan-overlap-bridge.log 2>/dev/null || true
  echo "--- micro-ROS Agent session lines ---"
  grep -E "session established|create_client|server stopped" /tmp/stackchan-overlap-agent.log 2>/dev/null || true
  echo "--- bridge tail ---"
  tail -n 160 /tmp/stackchan-overlap-bridge.log 2>/dev/null || true
  echo "--- micro-ROS Agent tail ---"
  tail -n 100 /tmp/stackchan-overlap-agent.log 2>/dev/null || true
  echo "--- socat tail ---"
  tail -n 60 /tmp/stackchan-overlap-socat.log 2>/dev/null || true
  print_phase_summary
}}
trap cleanup EXIT

phase_start "serial PTY setup" PTY_SETUP
for i in $(seq 1 50); do
  [ -e {args.pty} ] && break
  sleep 0.1
done
phase_end 0

phase_start "bridge startup" BRIDGE_STARTUP
"$bridge_node" >/tmp/stackchan-overlap-bridge.log 2>&1 &
bridge_pid=$!
for i in $(seq 1 80); do
  ros2 service list | grep -q '^/stackchan/default/cmd/get_status$' && break
  sleep 0.25
done
phase_end 0

phase_start "micro-ROS Agent startup" AGENT_STARTUP
ros2 run micro_ros_agent micro_ros_agent serial --dev {args.pty} -b {args.baud} -v{args.verbose} >/tmp/stackchan-overlap-agent.log 2>&1 &
agent_pid=$!
sleep 6
phase_end 0

phase_start "media overlap matrix" MEDIA_OVERLAP

json_command_id() {{
  python3 -c 'import json,sys; raw=sys.stdin.read(); start=raw.find("{{"); end=raw.rfind("}}"); data=json.loads(raw[start:end+1]) if start >= 0 and end >= start else dict(); print(data.get("command_id") or (data.get("metadata") or dict()).get("command_id") or "")' 2>/dev/null
}}

classify_json() {{
  slug="$1"
  file="$2"
  grep -Eq '"ok": *true' "$file"
  ok_result=$?
  grep -Eq '"code": *"FIRMWARE_BUSY"' "$file"
  busy_result=$?
  grep -Eq '"code": *"UNSUPPORTED_FEATURE"' "$file"
  unsupported_result=$?
  grep -Eqi '"result_state": *"timeout"|"code": *"TIMEOUT"' "$file"
  timeout_result=$?
  command_id=$(cat "$file" | json_command_id)
  echo "STACKCHAN_MEDIA_OVERLAP_${{slug}}_OK=$([ "$ok_result" -eq 0 ] && echo 1 || echo 0)"
  echo "STACKCHAN_MEDIA_OVERLAP_${{slug}}_FIRMWARE_BUSY=$([ "$busy_result" -eq 0 ] && echo 1 || echo 0)"
  echo "STACKCHAN_MEDIA_OVERLAP_${{slug}}_UNSUPPORTED=$([ "$unsupported_result" -eq 0 ] && echo 1 || echo 0)"
  echo "STACKCHAN_MEDIA_OVERLAP_${{slug}}_TIMEOUT=$([ "$timeout_result" -eq 0 ] && echo 1 || echo 0)"
  echo "STACKCHAN_MEDIA_OVERLAP_${{slug}}_COMMAND_ID_PRESENT=$([ -n "$command_id" ] && echo 1 || echo 0)"
}}

echo "=== standard/full firmware readiness ==="
observe_output=""
observe_ready=1
for i in $(seq 1 30); do
  observe_output=$(python3 -m stackchanctl --backend bridge --timeout 5 observe --json 2>&1)
  printf '%s\n' "$observe_output" > /tmp/stackchan-overlap-observe.json
  printf '%s\n' "$observe_output" | python3 -c 'import json,sys; raw=sys.stdin.read(); start=raw.find("{{"); end=raw.rfind("}}"); data=json.loads(raw[start:end+1]) if start >= 0 and end >= start else dict(); caps=dict((c.get("name"), c.get("state")) for c in data.get("capabilities", [])); names=("audio_playback","audio_capture","camera_snapshot"); missing=[n for n in names if caps.get(n)!="available"]; print("STACKCHAN_MEDIA_OVERLAP_CONNECTED=" + ("1" if data.get("connected") else "0")); print("STACKCHAN_MEDIA_OVERLAP_CAPABILITY_MISSING=" + (",".join(missing) if missing else "")); sys.exit(0 if data.get("connected") and not missing else 1)'
  observe_ready=$?
  [ "$observe_ready" -eq 0 ] && break
  sleep 1
done
cat /tmp/stackchan-overlap-observe.json || true
echo "STACKCHAN_MEDIA_OVERLAP_STANDARD_READY=$([ "$observe_ready" -eq 0 ] && echo 1 || echo 0)"
if [ "$observe_ready" -ne 0 ]; then
  echo "STACKCHAN_MEDIA_OVERLAP_ABORTED_PROFILE_OR_CONNECTION=1"
  phase_end 1
  exit 1
fi
echo "STACKCHAN_MEDIA_OVERLAP_ABORTED_PROFILE_OR_CONNECTION=0"

tone_wav=/tmp/stackchan-overlap-tone.wav
python3 - "$tone_wav" <<'PY'
import math
import sys
import wave

sample_rate = 16000
duration_ms = {playback_duration_ms}
frequency = {playback_frequency}
amplitude = {playback_amplitude}
sample_count = max(1, int(sample_rate * duration_ms / 1000.0))
samples = bytearray()
for index in range(sample_count):
    value = int(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
    samples.extend(int(value).to_bytes(2, "little", signed=True))
with wave.open(sys.argv[1], "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    wav.writeframes(bytes(samples))
PY

echo "=== camera-only sequential baseline ==="
python3 -m stackchanctl --backend bridge --timeout {args.timeout} camera capture --output /tmp/stackchan-overlap-camera-seq1.jpg --quality {camera_quality} --json > /tmp/stackchan-overlap-camera-seq1.json 2>&1
cat /tmp/stackchan-overlap-camera-seq1.json || true
classify_json CAMERA_SEQ1 /tmp/stackchan-overlap-camera-seq1.json
[ -s /tmp/stackchan-overlap-camera-seq1.jpg ] && echo "STACKCHAN_MEDIA_OVERLAP_CAMERA_SEQ1_BYTES=$(wc -c < /tmp/stackchan-overlap-camera-seq1.jpg)" || echo "STACKCHAN_MEDIA_OVERLAP_CAMERA_SEQ1_BYTES=0"
python3 -m stackchanctl --backend bridge --timeout {args.timeout} camera capture --output /tmp/stackchan-overlap-camera-seq2.jpg --quality {camera_quality} --json > /tmp/stackchan-overlap-camera-seq2.json 2>&1
cat /tmp/stackchan-overlap-camera-seq2.json || true
classify_json CAMERA_SEQ2 /tmp/stackchan-overlap-camera-seq2.json
[ -s /tmp/stackchan-overlap-camera-seq2.jpg ] && echo "STACKCHAN_MEDIA_OVERLAP_CAMERA_SEQ2_BYTES=$(wc -c < /tmp/stackchan-overlap-camera-seq2.jpg)" || echo "STACKCHAN_MEDIA_OVERLAP_CAMERA_SEQ2_BYTES=0"

echo "=== camera-overlap ==="
python3 -m stackchanctl --backend bridge --timeout {args.timeout} camera capture --output /tmp/stackchan-overlap-camera-first.jpg --quality {camera_quality} --json > /tmp/stackchan-overlap-camera-first.json 2>&1 &
camera_first_pid=$!
sleep 0.05
python3 -m stackchanctl --backend bridge --timeout {args.timeout} camera capture --output /tmp/stackchan-overlap-camera-second.jpg --quality {camera_quality} --json > /tmp/stackchan-overlap-camera-second.json 2>&1
wait $camera_first_pid
cat /tmp/stackchan-overlap-camera-first.json || true
classify_json CAMERA_OVERLAP_FIRST /tmp/stackchan-overlap-camera-first.json
cat /tmp/stackchan-overlap-camera-second.json || true
classify_json CAMERA_OVERLAP_SECOND /tmp/stackchan-overlap-camera-second.json
[ -s /tmp/stackchan-overlap-camera-first.jpg ] && echo "STACKCHAN_MEDIA_OVERLAP_CAMERA_FIRST_BYTES=$(wc -c < /tmp/stackchan-overlap-camera-first.jpg)" || echo "STACKCHAN_MEDIA_OVERLAP_CAMERA_FIRST_BYTES=0"
[ -s /tmp/stackchan-overlap-camera-second.jpg ] && echo "STACKCHAN_MEDIA_OVERLAP_CAMERA_SECOND_BYTES=$(wc -c < /tmp/stackchan-overlap-camera-second.jpg)" || echo "STACKCHAN_MEDIA_OVERLAP_CAMERA_SECOND_BYTES=0"

echo "=== audio-playback-overlap non-wait ==="
python3 -m stackchanctl --backend bridge --timeout {args.timeout} audio play "$tone_wav" --json > /tmp/stackchan-overlap-play-nowait.json 2>&1
cat /tmp/stackchan-overlap-play-nowait.json || true
classify_json AUDIO_PLAY_NOWAIT /tmp/stackchan-overlap-play-nowait.json
python3 -m stackchanctl --backend bridge --timeout {args.timeout} camera capture --output /tmp/stackchan-overlap-camera-after-play.jpg --quality {camera_quality} --json > /tmp/stackchan-overlap-camera-after-play.json 2>&1
cat /tmp/stackchan-overlap-camera-after-play.json || true
classify_json CAMERA_AFTER_AUDIO_PLAY_NOWAIT /tmp/stackchan-overlap-camera-after-play.json
python3 -m stackchanctl --backend bridge --timeout {args.timeout} audio capture --seconds 0.5 --output /tmp/stackchan-overlap-capture-after-play.wav --json > /tmp/stackchan-overlap-capture-after-play.json 2>&1
cat /tmp/stackchan-overlap-capture-after-play.json || true
classify_json AUDIO_CAPTURE_AFTER_AUDIO_PLAY_NOWAIT /tmp/stackchan-overlap-capture-after-play.json

echo "=== audio-playback wait baseline ==="
python3 -m stackchanctl --backend bridge --timeout {args.timeout} audio play --wait "$tone_wav" --json > /tmp/stackchan-overlap-play-wait.json 2>&1
cat /tmp/stackchan-overlap-play-wait.json || true
classify_json AUDIO_PLAY_WAIT /tmp/stackchan-overlap-play-wait.json
python3 -m stackchanctl --backend bridge --timeout {args.timeout} camera capture --output /tmp/stackchan-overlap-camera-after-play-wait.jpg --quality {camera_quality} --json > /tmp/stackchan-overlap-camera-after-play-wait.json 2>&1
cat /tmp/stackchan-overlap-camera-after-play-wait.json || true
classify_json CAMERA_AFTER_AUDIO_PLAY_WAIT /tmp/stackchan-overlap-camera-after-play-wait.json

echo "=== audio-capture-overlap ==="
python3 -m stackchanctl --backend bridge --timeout {args.timeout} audio capture --seconds {capture_seconds} --output /tmp/stackchan-overlap-capture.wav --json > /tmp/stackchan-overlap-capture.json 2>&1 &
capture_pid=$!
sleep 0.25
python3 -m stackchanctl --backend bridge --timeout {args.timeout} camera capture --output /tmp/stackchan-overlap-camera-during-capture.jpg --quality {camera_quality} --json > /tmp/stackchan-overlap-camera-during-capture.json 2>&1
wait $capture_pid
cat /tmp/stackchan-overlap-capture.json || true
classify_json AUDIO_CAPTURE_PRIMARY /tmp/stackchan-overlap-capture.json
[ -s /tmp/stackchan-overlap-capture.wav ] && echo "STACKCHAN_MEDIA_OVERLAP_AUDIO_CAPTURE_BYTES=$(wc -c < /tmp/stackchan-overlap-capture.wav)" || echo "STACKCHAN_MEDIA_OVERLAP_AUDIO_CAPTURE_BYTES=0"
cat /tmp/stackchan-overlap-camera-during-capture.json || true
classify_json CAMERA_DURING_AUDIO_CAPTURE /tmp/stackchan-overlap-camera-during-capture.json
[ -s /tmp/stackchan-overlap-camera-during-capture.jpg ] && echo "STACKCHAN_MEDIA_OVERLAP_CAMERA_DURING_CAPTURE_BYTES=$(wc -c < /tmp/stackchan-overlap-camera-during-capture.jpg)" || echo "STACKCHAN_MEDIA_OVERLAP_CAMERA_DURING_CAPTURE_BYTES=0"

if [ "{say_enabled}" = "1" ]; then
  echo "=== say-overlap ==="
  python3 -m stackchanctl --backend bridge --timeout {args.timeout} say {say_text} --json > /tmp/stackchan-overlap-say.json 2>&1 &
  say_pid=$!
  sleep 0.25
  python3 -m stackchanctl --backend bridge --timeout {args.timeout} camera capture --output /tmp/stackchan-overlap-camera-during-say.jpg --quality {camera_quality} --json > /tmp/stackchan-overlap-camera-during-say.json 2>&1
  wait $say_pid
  cat /tmp/stackchan-overlap-say.json || true
  classify_json SAY_PRIMARY /tmp/stackchan-overlap-say.json
  cat /tmp/stackchan-overlap-camera-during-say.json || true
  classify_json CAMERA_DURING_SAY /tmp/stackchan-overlap-camera-during-say.json
else
  echo "STACKCHAN_MEDIA_OVERLAP_SAY_SKIPPED=1"
fi

echo "--- normal log redaction scan ---"
cat /tmp/stackchan-overlap-bridge.log /tmp/stackchan-overlap-agent.log /tmp/stackchan-overlap-socat.log 2>/dev/null | grep -Ei 'nfc_tag_id|tag_id|uid|ir_code|raw_ir|raw_remote|remote_code|pcm|image|jpeg|base64|speech_text|transcript_text'
log_sensitive_result=$?
echo "STACKCHAN_MEDIA_OVERLAP_LOG_SENSITIVE_PAYLOAD_SEEN=$([ "$log_sensitive_result" -eq 0 ] && echo 1 || echo 0)"
[ "$log_sensitive_result" -ne 0 ] || result=1

phase_end "$result"
exit "$result"
"""
    return docker_run(
        args.image,
        command,
        mount_workspace=True,
        workdir=WORKSPACE,
    )


def run_tcp_pty_bridge_smoke(args: argparse.Namespace) -> int:
    disconnect_check = "1" if args.disconnect_check or args.reconnect_check else "0"
    allow_missing_firmware_ready = "1" if args.allow_missing_firmware_ready else "0"
    reconnect_check = "1" if args.reconnect_check else "0"
    disconnect_face_command = args.disconnect_face_command.strip()
    face_check = args.face_check.strip()
    say_check = args.say_check.strip()
    if args.say_naturalness_check and not say_check:
        say_check = DEFAULT_SAY_NATURALNESS_CHECK_TEXT
    say_check_arg = shlex.quote(say_check)
    say_voice = shlex.quote(args.say_voice.strip() or "default")
    say_face = args.say_face.strip() or (
        "happy" if args.say_naturalness_check and say_check else ""
    )
    say_motion = args.say_motion.strip() or (
        "cheerful" if args.say_naturalness_check and say_check else ""
    )
    say_after_face = args.say_after_face.strip() or (
        "happy" if args.say_naturalness_check and say_check else ""
    )
    say_operator_listening_verdict = args.say_operator_listening_verdict
    say_operator_listening_issue = args.say_operator_listening_issue
    if (
        say_operator_listening_verdict in {"unrecorded", "pass"}
        and say_operator_listening_issue != "none"
    ):
        raise SystemExit(
            "--say-operator-listening-issue must be none when verdict is unrecorded or pass"
        )
    if say_operator_listening_verdict == "fail" and say_operator_listening_issue == "none":
        raise SystemExit("--say-operator-listening-issue is required when verdict is fail")
    say_operator_listening_pass_hint = ""
    if (
        args.say_naturalness_check
        and say_check
        and say_operator_listening_verdict == "unrecorded"
    ):
        pass_hint_command = " ".join(
            shlex.quote(part)
            for part in (
                "uv",
                "run",
                "--no-project",
                "python",
                "scripts/microros_agent_container.py",
                "tcp-pty-bridge-smoke",
                "--tcp-host",
                args.tcp_host,
                "--tcp-port",
                str(args.tcp_port),
                "--baud",
                str(args.baud),
                "--verbose",
                str(args.verbose),
                "--timeout",
                str(args.timeout),
                "--say-naturalness-check",
                "--say-operator-listening-verdict",
                "pass",
            )
        )
        say_operator_listening_pass_hint = (
            "  echo "
            + shlex.quote(
                "STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_PASS_RERUN_HINT="
                + pass_hint_command
            )
        )
    say_hint_args = " ".join(
        option
        for option in (
            f"--face {shlex.quote(say_face)}" if say_face else "",
            f"--motion {shlex.quote(say_motion)}" if say_motion else "",
            f"--after-face {shlex.quote(say_after_face)}" if say_after_face else "",
        )
        if option
    )
    say_hint_payload_checks = ""
    if say_face:
        pattern = shlex.quote(f'"face_hint": "{say_face}"')
        say_hint_payload_checks += f"""
  printf '%s\\n' "$say_output" | grep -q {pattern}
  say_face_result=$?
  echo "STACKCHAN_BRIDGE_SAY_FACE_HINT_SEEN=$([ "$say_face_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$say_face_result" -eq 0 ] || result=1
"""
    if say_motion:
        pattern = shlex.quote(f'"motion_hint": "{say_motion}"')
        say_hint_payload_checks += f"""
  printf '%s\\n' "$say_output" | grep -q {pattern}
  say_motion_result=$?
  echo "STACKCHAN_BRIDGE_SAY_MOTION_HINT_SEEN=$([ "$say_motion_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$say_motion_result" -eq 0 ] || result=1
"""
    if say_after_face:
        pattern = shlex.quote(f'"after_face": "{say_after_face}"')
        say_hint_payload_checks += f"""
  printf '%s\\n' "$say_output" | grep -q {pattern}
  say_after_face_result=$?
  echo "STACKCHAN_BRIDGE_SAY_AFTER_FACE_SEEN=$([ "$say_after_face_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$say_after_face_result" -eq 0 ] || result=1
"""
    say_tts_enabled = "1" if say_check else "0"
    led_check = "1" if args.led_check else "0"
    motion_check = args.motion_check.strip()
    motion_disconnect_check = args.motion_disconnect_check.strip()
    motion_expected_error = args.motion_expected_error.strip()
    pose_check = args.pose_pan_deg is not None or args.pose_tilt_deg is not None
    if pose_check and (args.pose_pan_deg is None or args.pose_tilt_deg is None):
        raise SystemExit("--pose-pan-deg and --pose-tilt-deg must be provided together")
    pose_pan = "" if args.pose_pan_deg is None else f"{args.pose_pan_deg:.1f}"
    pose_tilt = "" if args.pose_tilt_deg is None else f"{args.pose_tilt_deg:.1f}"
    home_check = "1" if args.home_check else "0"
    soak_seconds = max(0, int(args.soak_seconds))
    soak_interval_seconds = max(1, int(args.soak_interval_seconds))
    media_action_timeout = f"{float(args.timeout):.1f}"
    status_attempt_limit = max(12, min(60, int((float(args.timeout) + 3.0) // 4.0)))
    setup_script = ros_smoke_setup_script(args)
    command = f"""
set +e
{setup_script}
export PYTHONPATH={WORKSPACE}/apps/stackchanctl/src:${{PYTHONPATH:-}}
bridge_node={WORKSPACE}/install/stackchan_bridge/lib/stackchan_bridge/stackchan_bridge_node
result=0
firmware_ready_seen=0
bridge_args=""
if [ "{say_tts_enabled}" = "1" ]; then
  export STACKCHAN_TTS_ENDPOINT="${{STACKCHAN_TTS_ENDPOINT:-http://host.docker.internal:50021}}"
  export STACKCHAN_TTS_SPEED_SCALE="${{STACKCHAN_TTS_SPEED_SCALE:-1.0}}"
  export STACKCHAN_TTS_PRE_PHONEME_LENGTH="${{STACKCHAN_TTS_PRE_PHONEME_LENGTH:-0.03}}"
  export STACKCHAN_TTS_POST_PHONEME_LENGTH="${{STACKCHAN_TTS_POST_PHONEME_LENGTH:-0.03}}"
  export STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD="${{STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD:-256}}"
  export STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS="${{STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS:-30.0}}"
  bridge_args="--ros-args -p tts_enabled:=true -p tts_endpoint:=$STACKCHAN_TTS_ENDPOINT -p tts_speed_scale:=$STACKCHAN_TTS_SPEED_SCALE -p tts_pre_phoneme_length:=$STACKCHAN_TTS_PRE_PHONEME_LENGTH -p tts_post_phoneme_length:=$STACKCHAN_TTS_POST_PHONEME_LENGTH -p tts_silence_trim_threshold:=$STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD -p tts_silence_trim_margin_ms:=$STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS -p device_media_action_timeout_sec:={media_action_timeout}"
fi
socat -d -d pty,raw,echo=0,link={args.pty} tcp:{args.tcp_host}:{args.tcp_port} 2>/tmp/stackchan-socat.log &
socat_pid=$!
agent_pid=
bridge_pid=
cleanup() {{
  cleanup_start=$(date +%s)
  kill $bridge_pid $agent_pid $socat_pid 2>/dev/null || true
  cleanup_end=$(date +%s)
  echo "STACKCHAN_SMOKE_PHASE_TEARDOWN_SECONDS=$((cleanup_end - cleanup_start))" | tee -a "$phase_times_file"
  print_phase_summary
}}
trap cleanup EXIT
phase_start "serial PTY setup" PTY_SETUP
for i in $(seq 1 50); do
  [ -e {args.pty} ] && break
  sleep 0.1
done
phase_end 0
phase_start "bridge startup" BRIDGE_STARTUP
"$bridge_node" $bridge_args >/tmp/stackchan-bridge.log 2>&1 &
bridge_pid=$!
for i in $(seq 1 80); do
  ros2 service list | grep -q '^/stackchan/default/cmd/get_status$' && break
  sleep 0.25
done
phase_end 0
phase_start "micro-ROS Agent startup" AGENT_STARTUP
ros2 run micro_ros_agent micro_ros_agent serial --dev {args.pty} -b {args.baud} -v{args.verbose} >/tmp/stackchan-agent.log 2>&1 &
agent_pid=$!
sleep 5
phase_end 0
phase_start "smoke checks" SMOKE_CHECKS
echo "--- stackchanctl observe ---"
observe_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json 2>&1)
observe_result=$?
printf '%s\n' "$observe_output"
echo "STACKCHAN_BRIDGE_OBSERVE_EXIT=$observe_result"
[ "$observe_result" -eq 0 ] || result=1
bridge_connected_output="$observe_output"
bridge_connected_result=$observe_result
printf '%s\n' "$bridge_connected_output" | grep -q '"connected": true'
bridge_connected_seen_result=$?
bridge_connected_attempt=1
for bridge_connected_attempt in $(seq 1 {status_attempt_limit}); do
  [ "$bridge_connected_result" -eq 0 ] && [ "$bridge_connected_seen_result" -eq 0 ] && break
  sleep 1
  bridge_connected_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json 2>&1)
  bridge_connected_result=$?
  printf '%s\n' "$bridge_connected_output" | grep -q '"connected": true'
  bridge_connected_seen_result=$?
done
echo "--- connected observe wait ---"
printf '%s\n' "$bridge_connected_output"
echo "STACKCHAN_BRIDGE_CONNECTED_OBSERVE_EXIT=$bridge_connected_result"
echo "STACKCHAN_BRIDGE_CONNECTED_OBSERVE_ATTEMPTS=$bridge_connected_attempt"
[ "$bridge_connected_result" -eq 0 ] || result=1
echo "STACKCHAN_BRIDGE_CONNECTED_OBSERVE_SEEN=$([ "$bridge_connected_seen_result" -eq 0 ] && echo 1 || echo 0)"
[ "$bridge_connected_seen_result" -eq 0 ] || result=1
if [ "$bridge_connected_seen_result" -eq 0 ]; then
  firmware_ready_seen=1
fi
echo "--- public status echo ---"
status_output=""
status_result=1
status_connected_result=1
status_attempt=0
for status_attempt in $(seq 1 {status_attempt_limit}); do
  status_output=$(timeout 4 ros2 topic echo --once /stackchan/default/status 2>&1)
  status_result=$?
  printf '%s\n' "$status_output" | grep -q 'connected: true'
  status_connected_result=$?
  [ "$status_result" -eq 0 ] && [ "$status_connected_result" -eq 0 ] && break
  sleep 1
done
printf '%s\n' "$status_output"
echo "STACKCHAN_BRIDGE_STATUS_ECHO_EXIT=$status_result"
echo "STACKCHAN_BRIDGE_STATUS_ATTEMPTS=$status_attempt"
[ "$status_result" -eq 0 ] || result=1
echo "STACKCHAN_BRIDGE_STATUS_CONNECTED=$([ "$status_connected_result" -eq 0 ] && echo 1 || echo 0)"
echo "STACKCHAN_BRIDGE_STATUS_CONNECTED_VIA_OBSERVE=$([ "$bridge_connected_seen_result" -eq 0 ] && echo 1 || echo 0)"
if [ "$status_connected_result" -ne 0 ] && [ "$bridge_connected_seen_result" -ne 0 ]; then
  result=1
fi
if [ "$status_connected_result" -eq 0 ]; then
  firmware_ready_seen=1
fi
if [ "{led_check}" = "1" ]; then
  for led_pattern in progress success off; do
    echo "--- stackchanctl led $led_pattern ---"
    led_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} led "$led_pattern" --json 2>&1)
    led_result=$?
    printf '%s\n' "$led_output"
    echo "STACKCHAN_BRIDGE_LED_${{led_pattern}}_EXIT=$led_result"
    [ "$led_result" -eq 0 ] || result=1
    printf '%s\n' "$led_output" | grep -q '"ok": true'
    led_ok_result=$?
    echo "STACKCHAN_BRIDGE_LED_${{led_pattern}}_OK=$([ "$led_ok_result" -eq 0 ] && echo 1 || echo 0)"
    [ "$led_ok_result" -eq 0 ] || result=1
  done
fi
if [ -n "{face_check}" ]; then
  echo "--- stackchanctl face {face_check} ---"
  face_output=""
  face_result=1
  face_attempt=0
  for face_attempt in 1 2 3 4 5; do
    face_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} face {face_check} --json 2>&1)
    face_result=$?
    [ "$face_result" -eq 0 ] && break
    printf '%s\n' "$face_output" | grep -q 'TRANSPORT_DISCONNECTED' || break
    sleep 1
  done
  printf '%s\n' "$face_output"
  echo "STACKCHAN_BRIDGE_FACE_EXIT=$face_result"
  echo "STACKCHAN_BRIDGE_FACE_ATTEMPTS=$face_attempt"
  [ "$face_result" -eq 0 ] || result=1
  sleep 2
  face_observe_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json 2>&1)
  face_observe_result=$?
  printf '%s\n' "$face_observe_output"
  echo "STACKCHAN_BRIDGE_FACE_OBSERVE_EXIT=$face_observe_result"
  [ "$face_observe_result" -eq 0 ] || result=1
  printf '%s\n' "$face_observe_output" | grep -q '"face": "{face_check}"'
  face_seen_result=$?
  echo "STACKCHAN_BRIDGE_FACE_SEEN=$([ "$face_seen_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$face_seen_result" -eq 0 ] || result=1
fi
if [ -n "{say_check}" ]; then
  echo "--- stackchanctl say ---"
  say_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} say --voice {say_voice} {say_hint_args} {say_check_arg} --wait --json 2>&1)
  say_result=$?
  printf '%s\n' "$say_output"
  echo "STACKCHAN_BRIDGE_SAY_EXIT=$say_result"
  [ "$say_result" -eq 0 ] || result=1
  printf '%s\n' "$say_output" | grep -q '"result_state": "COMPLETED"'
  say_completed_result=$?
  echo "STACKCHAN_BRIDGE_SAY_COMPLETED=$([ "$say_completed_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$say_completed_result" -eq 0 ] || result=1
  printf '%s\n' "$say_output" | grep -q '"voice_profile":'
  say_voice_result=$?
  echo "STACKCHAN_BRIDGE_SAY_VOICE_PROFILE_SEEN=$([ "$say_voice_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$say_voice_result" -eq 0 ] || result=1
{say_hint_payload_checks}
  sleep 1
  say_events_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} events list --json 2>&1)
  say_events_result=$?
  printf '%s\n' "$say_events_output"
  echo "STACKCHAN_BRIDGE_SAY_EVENTS_EXIT=$say_events_result"
  [ "$say_events_result" -eq 0 ] || result=1
  printf '%s\n' "$say_events_output" | grep -q '"event_name": "tts_finished"'
  say_tts_finished_result=$?
  echo "STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=$([ "$say_tts_finished_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$say_tts_finished_result" -eq 0 ] || result=1
  echo "STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_REQUIRED=1"
  echo "STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_CHECKS=intelligible,volume_ok,no_truncation,no_phrase_chop,wait_acceptable"
  echo "STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_VERDICT={say_operator_listening_verdict}"
  echo "STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_ISSUE={say_operator_listening_issue}"
{say_operator_listening_pass_hint}
  if printf '%s\n' "$say_events_output" | grep -q 'firmware_ready'; then
    firmware_ready_seen=1
  fi
fi
if [ -n "{motion_check}" ]; then
  echo "--- stackchanctl motion {motion_check} ---"
  motion_status_stream="/tmp/stackchan-motion-status.log"
  rm -f "$motion_status_stream"
  timeout 4 ros2 topic echo /stackchan/default/status >"$motion_status_stream" 2>&1 &
  motion_status_pid=$!
  sleep 0.2
  motion_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} motion {motion_check} --json 2>&1)
  motion_result=$?
  printf '%s\n' "$motion_output"
  echo "STACKCHAN_BRIDGE_MOTION_EXIT=$motion_result"
  if [ -n "{motion_expected_error}" ]; then
    printf '%s\n' "$motion_output" | grep -q '"code": "{motion_expected_error}"'
    motion_expected_result=$?
    echo "STACKCHAN_BRIDGE_MOTION_EXPECTED_ERROR_SEEN=$([ "$motion_expected_result" -eq 0 ] && echo 1 || echo 0)"
    [ "$motion_expected_result" -eq 0 ] || result=1
  else
    [ "$motion_result" -eq 0 ] || result=1
  fi
  wait "$motion_status_pid" 2>/dev/null || true
  echo "--- motion status stream ---"
  cat "$motion_status_stream" || true
  if [ -z "{motion_expected_error}" ]; then
    grep -q 'motion: {motion_check}' "$motion_status_stream"
    motion_stream_seen_result=$?
    echo "STACKCHAN_BRIDGE_MOTION_STREAM_SEEN=$([ "$motion_stream_seen_result" -eq 0 ] && echo 1 || echo 0)"
    [ "$motion_stream_seen_result" -eq 0 ] || result=1
  fi
  sleep 2
  motion_observe_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json 2>&1)
  motion_observe_result=$?
  printf '%s\n' "$motion_observe_output"
  echo "STACKCHAN_BRIDGE_MOTION_OBSERVE_EXIT=$motion_observe_result"
  [ "$motion_observe_result" -eq 0 ] || result=1
  if [ -n "{motion_expected_error}" ]; then
    printf '%s\n' "$motion_observe_output" | grep -q '"code": "{motion_expected_error}"'
    motion_observe_error_result=$?
    echo "STACKCHAN_BRIDGE_MOTION_OBSERVE_ERROR_SEEN=$([ "$motion_observe_error_result" -eq 0 ] && echo 1 || echo 0)"
    [ "$motion_observe_error_result" -eq 0 ] || result=1
  else
    printf '%s\n' "$motion_observe_output" | grep -q '"motion": "{motion_check}"'
    motion_seen_result=$?
    echo "STACKCHAN_BRIDGE_MOTION_SEEN=$([ "$motion_seen_result" -eq 0 ] && echo 1 || echo 0)"
  fi
fi
if [ "{1 if pose_check else 0}" = "1" ]; then
  echo "--- stackchanctl motion pose {pose_pan} {pose_tilt} ---"
  pose_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} motion pose --pan-deg {pose_pan} --tilt-deg {pose_tilt} --wait --json 2>&1)
  pose_result=$?
  printf '%s\n' "$pose_output"
  echo "STACKCHAN_BRIDGE_POSE_EXIT=$pose_result"
  [ "$pose_result" -eq 0 ] || result=1
  printf '%s\n' "$pose_output" | grep -q '"result_state": "COMPLETED"'
  pose_completed_result=$?
  echo "STACKCHAN_BRIDGE_POSE_COMPLETED=$([ "$pose_completed_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$pose_completed_result" -eq 0 ] || result=1
  sleep 1
  pose_status_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} motion status --json 2>&1)
  pose_status_result=$?
  printf '%s\n' "$pose_status_output"
  echo "STACKCHAN_BRIDGE_POSE_STATUS_EXIT=$pose_status_result"
  printf '%s\n' "$pose_status_output" | grep -q '"pan_deg": {pose_pan}'
  pose_pan_seen_result=$?
  printf '%s\n' "$pose_status_output" | grep -q '"tilt_deg": {pose_tilt}'
  pose_tilt_seen_result=$?
  echo "STACKCHAN_BRIDGE_POSE_PAN_SEEN=$([ "$pose_pan_seen_result" -eq 0 ] && echo 1 || echo 0)"
  echo "STACKCHAN_BRIDGE_POSE_TILT_SEEN=$([ "$pose_tilt_seen_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$pose_pan_seen_result" -eq 0 ] || result=1
  [ "$pose_tilt_seen_result" -eq 0 ] || result=1
fi
if [ "{home_check}" = "1" ]; then
  echo "--- stackchanctl motion home ---"
  home_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} motion home --wait --json 2>&1)
  home_result=$?
  printf '%s\n' "$home_output"
  echo "STACKCHAN_BRIDGE_HOME_EXIT=$home_result"
  [ "$home_result" -eq 0 ] || result=1
  printf '%s\n' "$home_output" | grep -q '"result_state": "COMPLETED"'
  home_completed_result=$?
  echo "STACKCHAN_BRIDGE_HOME_COMPLETED=$([ "$home_completed_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$home_completed_result" -eq 0 ] || result=1
  sleep 1
  home_status_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} motion status --json 2>&1)
  home_status_result=$?
  printf '%s\n' "$home_status_output"
  echo "STACKCHAN_BRIDGE_HOME_STATUS_EXIT=$home_status_result"
  printf '%s\n' "$home_status_output" | grep -q '"pan_deg": 0.0'
  home_pan_seen_result=$?
  printf '%s\n' "$home_status_output" | grep -q '"tilt_deg": 0.0'
  home_tilt_seen_result=$?
  echo "STACKCHAN_BRIDGE_HOME_PAN_SEEN=$([ "$home_pan_seen_result" -eq 0 ] && echo 1 || echo 0)"
  echo "STACKCHAN_BRIDGE_HOME_TILT_SEEN=$([ "$home_tilt_seen_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$home_pan_seen_result" -eq 0 ] || result=1
  [ "$home_tilt_seen_result" -eq 0 ] || result=1
fi
if [ -n "{motion_disconnect_check}" ]; then
  echo "--- motion disconnect check {motion_disconnect_check} ---"
  motion_disconnect_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} motion {motion_disconnect_check} --json 2>&1)
  motion_disconnect_result=$?
  printf '%s\n' "$motion_disconnect_output"
  echo "STACKCHAN_BRIDGE_MOTION_DISCONNECT_COMMAND_EXIT=$motion_disconnect_result"
  [ "$motion_disconnect_result" -eq 0 ] || result=1
  sleep 0.2
  kill -9 $agent_pid 2>/dev/null || true
  pkill -9 -f micro_ros_agent 2>/dev/null || true
  agent_pid=
  sleep 8
  motion_disconnect_observe=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json 2>&1)
  motion_disconnect_observe_result=$?
  printf '%s\n' "$motion_disconnect_observe"
  echo "STACKCHAN_BRIDGE_MOTION_DISCONNECT_OBSERVE_EXIT=$motion_disconnect_observe_result"
  printf '%s\n' "$motion_disconnect_observe" | grep -q 'TRANSPORT_DISCONNECTED'
  motion_disconnect_seen_result=$?
  echo "STACKCHAN_BRIDGE_MOTION_DISCONNECT_SEEN=$([ "$motion_disconnect_seen_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$motion_disconnect_seen_result" -eq 0 ] || result=1
  echo "--- motion disconnect reconnect check ---"
  ros2 run micro_ros_agent micro_ros_agent serial --dev {args.pty} -b {args.baud} -v{args.verbose} >/tmp/stackchan-agent-motion-reconnect.log 2>&1 &
  agent_pid=$!
  motion_reconnect_output=""
  motion_reconnect_result=1
  motion_reconnect_seen_result=1
  for i in $(seq 1 20); do
    sleep 3
    motion_reconnect_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json 2>&1)
    motion_reconnect_result=$?
    printf '%s\n' "$motion_reconnect_output" | grep -q '"connected": true'
    motion_reconnect_seen_result=$?
    [ "$motion_reconnect_seen_result" -eq 0 ] && break
  done
  printf '%s\n' "$motion_reconnect_output"
  echo "STACKCHAN_BRIDGE_MOTION_RECONNECT_OBSERVE_EXIT=$motion_reconnect_result"
  [ "$motion_reconnect_result" -eq 0 ] || result=1
  echo "STACKCHAN_BRIDGE_MOTION_RECONNECT_SEEN=$([ "$motion_reconnect_seen_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$motion_reconnect_seen_result" -eq 0 ] || result=1
  printf '%s\n' "$motion_reconnect_output" | grep -q '"motion": "{motion_disconnect_check}"'
  motion_reconnect_stale_result=$?
  echo "STACKCHAN_BRIDGE_MOTION_RECONNECT_STALE_MOTION_SEEN=$([ "$motion_reconnect_stale_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$motion_reconnect_stale_result" -ne 0 ] || result=1
fi
if [ "{disconnect_check}" = "1" ]; then
  echo "--- liveness disconnect check ---"
  kill -9 $agent_pid 2>/dev/null || true
  pkill -9 -f micro_ros_agent 2>/dev/null || true
  agent_pid=
  sleep 8
  disconnect_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json 2>&1)
  disconnect_result=$?
  printf '%s\n' "$disconnect_output"
  echo "STACKCHAN_BRIDGE_DISCONNECT_OBSERVE_EXIT=$disconnect_result"
  printf '%s\n' "$disconnect_output" | grep -q 'TRANSPORT_DISCONNECTED'
  disconnect_seen_result=$?
  echo "STACKCHAN_BRIDGE_DISCONNECT_SEEN=$([ "$disconnect_seen_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$disconnect_seen_result" -eq 0 ] || result=1
  if [ -n "{disconnect_face_command}" ]; then
    echo "--- disconnected stackchanctl face {disconnect_face_command} ---"
    disconnect_command_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} face {disconnect_face_command} --json 2>&1)
    disconnect_command_result=$?
    printf '%s\n' "$disconnect_command_output"
    echo "STACKCHAN_BRIDGE_DISCONNECT_COMMAND_EXIT=$disconnect_command_result"
    printf '%s\n' "$disconnect_command_output" | grep -q 'TRANSPORT_DISCONNECTED'
    disconnect_command_rejected_result=$?
    echo "STACKCHAN_BRIDGE_DISCONNECT_COMMAND_REJECTED=$([ "$disconnect_command_rejected_result" -eq 0 ] && echo 1 || echo 0)"
    [ "$disconnect_command_rejected_result" -eq 0 ] || result=1
  fi
fi
if [ "{reconnect_check}" = "1" ]; then
  echo "--- liveness reconnect check ---"
  ros2 run micro_ros_agent micro_ros_agent serial --dev {args.pty} -b {args.baud} -v{args.verbose} >/tmp/stackchan-agent-reconnect.log 2>&1 &
  agent_pid=$!
  reconnect_output=""
  reconnect_result=1
  reconnect_seen_result=1
  for i in $(seq 1 20); do
    sleep 3
    reconnect_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json 2>&1)
    reconnect_result=$?
    printf '%s\n' "$reconnect_output" | grep -q '"connected": true'
    reconnect_seen_result=$?
    [ "$reconnect_seen_result" -eq 0 ] && break
  done
  printf '%s\n' "$reconnect_output"
  echo "STACKCHAN_BRIDGE_RECONNECT_OBSERVE_EXIT=$reconnect_result"
  [ "$reconnect_result" -eq 0 ] || result=1
  echo "STACKCHAN_BRIDGE_RECONNECT_SEEN=$([ "$reconnect_seen_result" -eq 0 ] && echo 1 || echo 0)"
  [ "$reconnect_seen_result" -eq 0 ] || result=1
  if [ -n "{disconnect_face_command}" ]; then
    printf '%s\n' "$reconnect_output" | grep -q '"face": "{disconnect_face_command}"'
    reconnect_delayed_face_result=$?
    echo "STACKCHAN_BRIDGE_RECONNECT_DELAYED_FACE_SEEN=$([ "$reconnect_delayed_face_result" -eq 0 ] && echo 1 || echo 0)"
    [ "$reconnect_delayed_face_result" -ne 0 ] || result=1
  fi
fi
if [ "{soak_seconds}" -gt 0 ]; then
  echo "--- soak check {soak_seconds}s ---"
  soak_end=$(( $(date +%s) + {soak_seconds} ))
  soak_iteration=0
  while [ "$(date +%s)" -lt "$soak_end" ]; do
    soak_iteration=$((soak_iteration + 1))
    soak_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json 2>&1)
    soak_result=$?
    printf '%s\n' "$soak_output"
    echo "STACKCHAN_BRIDGE_SOAK_OBSERVE_EXIT_$soak_iteration=$soak_result"
    [ "$soak_result" -eq 0 ] || result=1
    printf '%s\n' "$soak_output" | grep -q '"connected": true'
    soak_connected_result=$?
    echo "STACKCHAN_BRIDGE_SOAK_CONNECTED_$soak_iteration=$([ "$soak_connected_result" -eq 0 ] && echo 1 || echo 0)"
    [ "$soak_connected_result" -eq 0 ] || result=1
    printf '%s\n' "$soak_output" | grep -q '"code":'
    soak_error_seen_result=$?
    echo "STACKCHAN_BRIDGE_SOAK_ERROR_SEEN_$soak_iteration=$([ "$soak_error_seen_result" -eq 0 ] && echo 1 || echo 0)"
    [ "$soak_error_seen_result" -ne 0 ] || result=1
    sleep {soak_interval_seconds}
  done
  echo "STACKCHAN_BRIDGE_SOAK_ITERATIONS=$soak_iteration"
fi
echo "--- stackchanctl events list ---"
events_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} events list --limit 10 --json)
events_result=$?
printf '%s\\n' "$events_output"
echo "STACKCHAN_BRIDGE_EVENTS_EXIT=$events_result"
[ "$events_result" -eq 0 ] || result=1
printf '%s\\n' "$events_output" | grep -q 'firmware_ready'
firmware_ready_result=$?
if [ "$firmware_ready_result" -eq 0 ]; then
  firmware_ready_seen=1
fi
echo "STACKCHAN_BRIDGE_FIRMWARE_READY_SEEN=$firmware_ready_seen"
if [ "{allow_missing_firmware_ready}" != "1" ]; then
  [ "$firmware_ready_seen" = "1" ] || result=1
fi
if [ "{reconnect_check}" = "1" ]; then
  device_connected_count=$(printf '%s\n' "$events_output" | grep -c 'device_connected')
  device_disconnected_count=$(printf '%s\n' "$events_output" | grep -c 'device_disconnected')
  echo "STACKCHAN_BRIDGE_RECONNECT_DEVICE_CONNECTED_COUNT=$device_connected_count"
  echo "STACKCHAN_BRIDGE_RECONNECT_DEVICE_DISCONNECTED_COUNT=$device_disconnected_count"
  [ "$device_connected_count" -ge 2 ] || result=1
  [ "$device_disconnected_count" -ge 1 ] || result=1
fi
echo "--- stackchan services ---"
ros2 service list -t | grep stackchan || true
echo "--- stackchan topics ---"
ros2 topic list -t | grep stackchan || true
echo "--- bridge tail ---"
tail -n 120 /tmp/stackchan-bridge.log || true
echo "--- micro-ROS Agent tail ---"
tail -n 120 /tmp/stackchan-agent.log || true
echo "--- micro-ROS Agent reconnect tail ---"
tail -n 120 /tmp/stackchan-agent-reconnect.log || true
echo "--- micro-ROS Agent motion reconnect tail ---"
tail -n 120 /tmp/stackchan-agent-motion-reconnect.log || true
echo "--- socat tail ---"
tail -n 60 /tmp/stackchan-socat.log || true
phase_end "$result"
exit $result
"""
    return docker_run(
        args.image,
        command,
        mount_workspace=True,
        workdir=WORKSPACE,
    )


def run_tcp_pty_loaded_audio_probe(args: argparse.Namespace) -> int:
    try:
        chunk_sizes = parse_chunk_sizes(args.chunk_bytes)
    except ValueError as exc:
        raise SystemExit(f"--chunk-bytes: {exc}") from exc
    chunk_sizes_value = ",".join(str(value) for value in chunk_sizes)
    total_bytes = max(2, int(args.total_bytes))
    if total_bytes % 2:
        total_bytes += 1
    chunk_timeout = max(0.5, float(args.chunk_timeout))
    status_attempt_limit = max(1, int((float(args.timeout) + 4.0) // 5.0))
    play_action = "1" if args.play_action else "0"
    setup_script = ros_smoke_setup_script(args)
    command = f"""
set +e
{setup_script}
export STACKCHAN_LOAD_PROBE_CHUNK_SIZES={shlex.quote(chunk_sizes_value)}
export STACKCHAN_LOAD_PROBE_TOTAL_BYTES={total_bytes}
export STACKCHAN_LOAD_PROBE_CHUNK_TIMEOUT={chunk_timeout:.3f}
export STACKCHAN_LOAD_PROBE_PLAY_ACTION={play_action}
socat -d -d pty,raw,echo=0,link={args.pty} tcp:{args.tcp_host}:{args.tcp_port} 2>/tmp/stackchan-socat.log &
socat_pid=$!
agent_pid=
cleanup() {{
  cleanup_start=$(date +%s)
  kill $agent_pid $socat_pid 2>/dev/null || true
  cleanup_end=$(date +%s)
  echo "STACKCHAN_LOAD_PROBE_TEARDOWN_SECONDS=$((cleanup_end - cleanup_start))"
  print_phase_summary
}}
trap cleanup EXIT
phase_start "serial PTY setup" PTY_SETUP
for i in $(seq 1 50); do
  [ -e {args.pty} ] && break
  sleep 0.1
done
phase_end 0
phase_start "micro-ROS Agent startup" AGENT_STARTUP
ros2 run micro_ros_agent micro_ros_agent serial --dev {args.pty} -b {args.baud} -v{args.verbose} >/tmp/stackchan-agent.log 2>&1 &
agent_pid=$!
sleep 5
phase_end 0
phase_start "device status wait" DEVICE_STATUS_WAIT
status_output=""
status_connected_result=1
status_attempt=0
for status_attempt in $(seq 1 {status_attempt_limit}); do
  status_output=$(timeout 4 ros2 topic echo --once /stackchan/default/device/status 2>&1)
  printf '%s\\n' "$status_output" | grep -q 'connected: true'
  status_connected_result=$?
  [ "$status_connected_result" -eq 0 ] && break
  sleep 1
done
printf '%s\\n' "$status_output"
echo "STACKCHAN_LOAD_PROBE_STATUS_ATTEMPTS=$status_attempt"
echo "STACKCHAN_LOAD_PROBE_STATUS_CONNECTED=$([ "$status_connected_result" -eq 0 ] && echo 1 || echo 0)"
phase_end "$status_connected_result"
if [ "$status_connected_result" -ne 0 ]; then
  echo "--- micro-ROS Agent tail ---"
  tail -n 120 /tmp/stackchan-agent.log || true
  echo "--- socat tail ---"
  tail -n 80 /tmp/stackchan-socat.log || true
  exit 1
fi
phase_start "loaded audio probe" LOADED_AUDIO_PROBE
python3 - <<'PY'
import os
import time
import uuid

import rclpy
from rclpy.action import ActionClient

from stackchan_msgs.action import PlayAudio
from stackchan_msgs.msg import CommandMeta
from stackchan_msgs.srv import LoadAudioChunk


def fill_meta(node, meta, command_id):
    meta.device_id = "default"
    meta.command_id = command_id
    meta.source = "loaded_audio_probe"
    meta.created_at = node.get_clock().now().to_msg()
    meta.priority = CommandMeta.PRIORITY_NORMAL


def spin_until_done(node, future, timeout_sec):
    started = time.monotonic()
    while not future.done() and time.monotonic() - started < timeout_sec:
        rclpy.spin_once(node, timeout_sec=0.05)
    return future.done(), time.monotonic() - started


chunk_sizes = [
    int(part)
    for part in os.environ["STACKCHAN_LOAD_PROBE_CHUNK_SIZES"].split(",")
    if part
]
total_bytes_base = int(os.environ["STACKCHAN_LOAD_PROBE_TOTAL_BYTES"])
chunk_timeout = float(os.environ["STACKCHAN_LOAD_PROBE_CHUNK_TIMEOUT"])
play_action = os.environ.get("STACKCHAN_LOAD_PROBE_PLAY_ACTION") == "1"

rclpy.init()
node = rclpy.create_node("loaded_audio_probe")
client = node.create_client(
    LoadAudioChunk,
    "/stackchan/default/device/audio/playback/load",
)
print("STACKCHAN_LOAD_PROBE_SERVICE_WAIT_START", flush=True)
service_ready = client.wait_for_service(timeout_sec=10.0)
print("STACKCHAN_LOAD_PROBE_SERVICE_READY=%s" % (1 if service_ready else 0), flush=True)
if not service_ready:
    raise SystemExit(1)

action_client = None
if play_action:
    action_client = ActionClient(
        node,
        PlayAudio,
        "/stackchan/default/device/audio/play",
    )
    action_ready = action_client.wait_for_server(timeout_sec=10.0)
    print(
        "STACKCHAN_LOAD_PROBE_ACTION_READY=%s" % (1 if action_ready else 0),
        flush=True,
    )
    if not action_ready:
        raise SystemExit(1)

overall_status = 0
for chunk_size in chunk_sizes:
    total_bytes = max(total_bytes_base, chunk_size)
    if total_bytes % 2:
        total_bytes += 1
    total_chunks = (total_bytes + chunk_size - 1) // chunk_size
    payload = bytes(total_bytes)
    command_id = str(uuid.uuid4())
    print(
        "STACKCHAN_LOAD_PROBE_START chunk_bytes=%d total_bytes=%d "
        "total_chunks=%d command_id=%s"
        % (chunk_size, total_bytes, total_chunks, command_id),
        flush=True,
    )
    chunk_failed = False
    for sequence, start in enumerate(range(0, total_bytes, chunk_size)):
        request = LoadAudioChunk.Request()
        fill_meta(node, request.meta, command_id)
        request.sequence = sequence
        request.total_chunks = total_chunks
        request.total_bytes = total_bytes
        request.format = 1
        request.sample_rate = 16000
        request.channels = 1
        request.end_of_stream = sequence + 1 >= total_chunks
        request.pcm = payload[start : start + chunk_size]
        future = client.call_async(request)
        done, elapsed = spin_until_done(node, future, chunk_timeout)
        if not done:
            print(
                "STACKCHAN_LOAD_PROBE_CHUNK_TIMEOUT chunk_bytes=%d "
                "sequence=%d total_chunks=%d bytes=%d elapsed_ms=%d"
                % (
                    chunk_size,
                    sequence,
                    total_chunks,
                    len(request.pcm),
                    int(elapsed * 1000),
                ),
                flush=True,
            )
            overall_status = 1
            chunk_failed = True
            break
        response = future.result()
        result = response.result
        print(
            "STACKCHAN_LOAD_PROBE_CHUNK_RESPONSE chunk_bytes=%d "
            "sequence=%d total_chunks=%d bytes=%d ok=%s state=%d "
            "error_code=%s accepted_sequence=%d buffered_chunks=%d "
            "buffered_bytes=%d complete=%s elapsed_ms=%d"
            % (
                chunk_size,
                sequence,
                total_chunks,
                len(request.pcm),
                "1" if result.ok else "0",
                result.state,
                result.error_code,
                response.accepted_sequence,
                response.buffered_chunks,
                response.buffered_bytes,
                "1" if response.complete else "0",
                int(elapsed * 1000),
            ),
            flush=True,
        )
        if not result.ok:
            overall_status = 1
            chunk_failed = True
            break
    if chunk_failed:
        break
    if play_action and action_client is not None:
        goal = PlayAudio.Goal()
        fill_meta(node, goal.meta, command_id)
        goal.format = "pcm_s16le"
        goal.sample_rate = 16000
        goal.channels = 1
        goal.first_chunk_present = False
        goal.first_chunk_sequence = 0
        goal.first_chunk_pcm = b""
        goal.face_hint = ""
        goal.motion_hint = ""
        send_future = action_client.send_goal_async(goal)
        done, elapsed = spin_until_done(node, send_future, 10.0)
        if not done:
            print(
                "STACKCHAN_LOAD_PROBE_ACTION_GOAL_TIMEOUT "
                "chunk_bytes=%d elapsed_ms=%d"
                % (chunk_size, int(elapsed * 1000)),
                flush=True,
            )
            overall_status = 1
            break
        goal_handle = send_future.result()
        print(
            "STACKCHAN_LOAD_PROBE_ACTION_GOAL chunk_bytes=%d accepted=%s"
            % (chunk_size, "1" if goal_handle.accepted else "0"),
            flush=True,
        )
        if not goal_handle.accepted:
            overall_status = 1
            break
        result_future = goal_handle.get_result_async()
        done, elapsed = spin_until_done(node, result_future, 15.0)
        if not done:
            print(
                "STACKCHAN_LOAD_PROBE_ACTION_RESULT_TIMEOUT "
                "chunk_bytes=%d elapsed_ms=%d"
                % (chunk_size, int(elapsed * 1000)),
                flush=True,
            )
            overall_status = 1
            break
        action_result = result_future.result().result.result
        print(
            "STACKCHAN_LOAD_PROBE_ACTION_RESULT chunk_bytes=%d ok=%s "
            "state=%d error_code=%s message=%s"
            % (
                chunk_size,
                "1" if action_result.ok else "0",
                action_result.state,
                action_result.error_code,
                action_result.message,
            ),
            flush=True,
        )
        if not action_result.ok:
            overall_status = 1
            break

node.destroy_node()
rclpy.shutdown()
raise SystemExit(overall_status)
PY
probe_status=$?
phase_end "$probe_status"
echo "--- micro-ROS Agent tail ---"
tail -n 120 /tmp/stackchan-agent.log || true
echo "--- socat tail ---"
tail -n 80 /tmp/stackchan-socat.log || true
exit "$probe_status"
"""
    return docker_run(
        args.image,
        command,
        mount_workspace=True,
        workdir=WORKSPACE,
    )


def run_serial(args: argparse.Namespace) -> int:
    command = " && ".join(
        [
            "source /opt/ros/jazzy/setup.bash",
            "source /uros_ws/install/local_setup.bash",
            (
                "ros2 run micro_ros_agent micro_ros_agent "
                f"serial --dev {args.dev} -b {args.baud} -v{args.verbose}"
            ),
        ]
    )
    return docker_run(args.image, command, devices=[args.dev])


def docker_run(
    image: str,
    command: str,
    *,
    devices: list[str] | None = None,
    mount_workspace: bool = False,
    workdir: str | None = None,
) -> int:
    docker_args = ["docker", "run", "--rm", "--net=host"]
    for name in ENV_PASSTHROUGH:
        value = os.environ.get(name)
        if value is not None:
            docker_args.extend(["-e", f"{name}={value}"])
    for device in devices or []:
        docker_args.append(f"--device={device}")
    if mount_workspace:
        docker_args.extend(["-v", f"{ROOT}:{WORKSPACE}"])
    if workdir:
        docker_args.extend(["-w", workdir])
    docker_args.extend(["--entrypoint", "/bin/bash", image, "-lc", command])
    completed = subprocess.run(docker_args, cwd=ROOT, check=False)
    return int(completed.returncode)


def run(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
