from __future__ import annotations

import argparse
import os
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
ENV_PASSTHROUGH = (
    "STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES",
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
            "to pick up/tilt/shake the device, present/remove NFC tags, or press "
            "IR remote buttons while the Agent and bridge are connected."
        ),
    )
    tcp_pty_sweep.add_argument(
        "--media-audio-capture-seconds",
        type=float,
        default=0.02,
        help="Audio capture duration used by the hardware media smoke.",
    )
    tcp_pty_sweep.add_argument(
        "--media-camera-quality",
        type=int,
        default=50,
        help="JPEG quality used by the hardware camera smoke.",
    )
    tcp_pty_sweep.add_argument(
        "--skip-build",
        action="store_true",
        help="Use the existing install/ workspace instead of rebuilding ROS packages.",
    )

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


def run_tcp_pty(args: argparse.Namespace) -> int:
    command = f"""
set -e
apt-get update >/dev/null
apt-get install -y --no-install-recommends socat >/dev/null
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
apt-get update >/dev/null
apt-get install -y --no-install-recommends socat >/dev/null
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
    build_deps_command = (
        ""
        if args.skip_build
        else (
            "apt-get install -y --no-install-recommends "
            "build-essential cmake python3-colcon-common-extensions "
            "ros-jazzy-geometry-msgs ros-jazzy-rclpy "
            "ros-jazzy-rosidl-default-generators >/dev/null\n"
        )
    )
    build_command = (
        ""
        if args.skip_build
        else (
            "colcon build --base-paths ros/stackchan_msgs ros/stackchan_bridge "
            "--packages-select stackchan_msgs stackchan_bridge --cmake-clean-cache\n"
        )
    )
    command = f"""
set +e
apt-get update >/dev/null
apt-get install -y --no-install-recommends socat >/dev/null
{build_deps_command}
source /opt/ros/jazzy/setup.bash
source /uros_ws/install/local_setup.bash
{build_command}source {WORKSPACE}/install/setup.bash
export PYTHONPATH={WORKSPACE}/apps/stackchanctl/src:$PYTHONPATH
bridge_node={WORKSPACE}/install/stackchan_bridge/lib/stackchan_bridge/stackchan_bridge_node
result=0
socat -d -d pty,raw,echo=0,link={args.pty} tcp:{args.tcp_host}:{args.tcp_port} 2>/tmp/stackchan-socat.log &
socat_pid=$!
agent_pid=
bridge_pid=
trap 'kill $bridge_pid $agent_pid $socat_pid 2>/dev/null || true' EXIT
for i in $(seq 1 50); do
  [ -e {args.pty} ] && break
  sleep 0.1
done
"$bridge_node" >/tmp/stackchan-bridge.log 2>&1 &
bridge_pid=$!
for i in $(seq 1 80); do
  ros2 service list | grep -q '^/stackchan/default/cmd/get_status$' && break
  sleep 0.25
done
ros2 run micro_ros_agent micro_ros_agent serial --dev {args.pty} -b {args.baud} -v{args.verbose} >/tmp/stackchan-agent.log 2>&1 &
agent_pid=$!
sleep 6

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

run_media_smoke() {{
  prompt_wav=$(mktemp /tmp/stackchan-prompt-XXXXXX.wav)
  mic_wav=$(mktemp /tmp/stackchan-mic-XXXXXX.wav)
  frame_jpg=$(mktemp /tmp/stackchan-frame-XXXXXX.jpg)
  python3 - "$prompt_wav" <<'PY'
import math
import sys
import wave

sample_rate = 16000
samples = bytearray()
for index in range(sample_rate // 50):
    value = int(1200 * math.sin(2 * math.pi * 440 * index / sample_rate))
    samples.extend(int(value).to_bytes(2, "little", signed=True))
with wave.open(sys.argv[1], "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    wav.writeframes(bytes(samples))
PY

  echo "--- stackchanctl audio play smoke ---"
  audio_play_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} audio play "$prompt_wav" --json 2>&1)
  audio_play_result=$?
  rm -f "$prompt_wav"
  printf '%s\n' "$audio_play_output"
  echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_EXIT=$audio_play_result"
  printf '%s\n' "$audio_play_output" | grep -Eq '"code": *"UNSUPPORTED_FEATURE"'
  audio_play_unsupported_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_UNSUPPORTED_SEEN=$([ "$audio_play_unsupported_result" -eq 0 ] && echo 1 || echo 0)"
  printf '%s\n' "$audio_play_output" | grep -Eq '"ok": *true'
  audio_play_ok_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_OK_SEEN=$([ "$audio_play_ok_result" -eq 0 ] && echo 1 || echo 0)"

  echo "--- stackchanctl audio capture smoke ---"
  audio_capture_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} audio capture --seconds {max(0.001, float(args.media_audio_capture_seconds))} --output "$mic_wav" --json 2>&1)
  audio_capture_result=$?
  rm -f "$mic_wav"
  printf '%s\n' "$audio_capture_output"
  echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_EXIT=$audio_capture_result"
  printf '%s\n' "$audio_capture_output" | grep -Eq '"code": *"UNSUPPORTED_FEATURE"'
  audio_capture_unsupported_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_UNSUPPORTED_SEEN=$([ "$audio_capture_unsupported_result" -eq 0 ] && echo 1 || echo 0)"
  printf '%s\n' "$audio_capture_output" | grep -Eq '"code": *"MIC_OVERRUN"'
  audio_capture_mic_overrun_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_MIC_OVERRUN_SEEN=$([ "$audio_capture_mic_overrun_result" -eq 0 ] && echo 1 || echo 0)"
  printf '%s\n' "$audio_capture_output" | grep -Eq '"ok": *true'
  audio_capture_ok_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OK_SEEN=$([ "$audio_capture_ok_result" -eq 0 ] && echo 1 || echo 0)"

  echo "--- stackchanctl camera capture smoke ---"
  camera_output=$(python3 -m stackchanctl --backend bridge --timeout {args.timeout} camera capture --output "$frame_jpg" --quality {min(95, max(1, int(args.media_camera_quality)))} --json 2>&1)
  camera_result=$?
  rm -f "$frame_jpg"
  printf '%s\n' "$camera_output"
  echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_EXIT=$camera_result"
  printf '%s\n' "$camera_output" | grep -Eq '"code": *"UNSUPPORTED_FEATURE"'
  camera_unsupported_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_UNSUPPORTED_SEEN=$([ "$camera_unsupported_result" -eq 0 ] && echo 1 || echo 0)"
  printf '%s\n' "$camera_output" | grep -Eq '"ok": *true'
  camera_ok_result=$?
  echo "STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=$([ "$camera_ok_result" -eq 0 ] && echo 1 || echo 0)"

  if {{ [ "$audio_play_unsupported_result" -ne 0 ] && [ "$audio_play_ok_result" -ne 0 ]; }} ||
     {{ [ "$audio_capture_unsupported_result" -ne 0 ] && [ "$audio_capture_mic_overrun_result" -ne 0 ] && [ "$audio_capture_ok_result" -ne 0 ]; }} ||
     {{ [ "$camera_unsupported_result" -ne 0 ] && [ "$camera_ok_result" -ne 0 ]; }}; then
    result=1
  fi
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
  echo "Apply button, IMU, NFC, and IR/remote stimuli now. Normal logs/events will be redaction-scanned afterwards."
  sleep {max(0, int(args.stimulus_window_seconds))}
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
run_media_smoke
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
exit $result
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
    build_deps_command = (
        ""
        if args.skip_build
        else (
            "apt-get install -y --no-install-recommends "
            "build-essential cmake python3-colcon-common-extensions "
            "ros-jazzy-geometry-msgs ros-jazzy-rclpy "
            "ros-jazzy-rosidl-default-generators >/dev/null\n"
        )
    )
    build_command = (
        ""
        if args.skip_build
        else (
            "colcon build --base-paths ros/stackchan_msgs ros/stackchan_bridge "
            "--packages-select stackchan_msgs stackchan_bridge --cmake-clean-cache\n"
        )
    )
    command = f"""
set +e
apt-get update >/dev/null
apt-get install -y --no-install-recommends socat >/dev/null
{build_deps_command}
source /opt/ros/jazzy/setup.bash
source /uros_ws/install/local_setup.bash
{build_command}source {WORKSPACE}/install/setup.bash
export PYTHONPATH={WORKSPACE}/apps/stackchanctl/src:${{PYTHONPATH:-}}
bridge_node={WORKSPACE}/install/stackchan_bridge/lib/stackchan_bridge/stackchan_bridge_node
result=0
socat -d -d pty,raw,echo=0,link={args.pty} tcp:{args.tcp_host}:{args.tcp_port} 2>/tmp/stackchan-socat.log &
socat_pid=$!
agent_pid=
bridge_pid=
trap 'kill $bridge_pid $agent_pid $socat_pid 2>/dev/null || true' EXIT
for i in $(seq 1 50); do
  [ -e {args.pty} ] && break
  sleep 0.1
done
"$bridge_node" >/tmp/stackchan-bridge.log 2>&1 &
bridge_pid=$!
for i in $(seq 1 80); do
  ros2 service list | grep -q '^/stackchan/default/cmd/get_status$' && break
  sleep 0.25
done
ros2 run micro_ros_agent micro_ros_agent serial --dev {args.pty} -b {args.baud} -v{args.verbose} >/tmp/stackchan-agent.log 2>&1 &
agent_pid=$!
sleep 5
echo "--- stackchanctl observe ---"
python3 -m stackchanctl --backend bridge --timeout {args.timeout} observe --json
observe_result=$?
echo "STACKCHAN_BRIDGE_OBSERVE_EXIT=$observe_result"
[ "$observe_result" -eq 0 ] || result=1
echo "--- public status echo ---"
status_output=""
status_result=1
status_connected_result=1
status_attempt=0
for status_attempt in $(seq 1 12); do
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
[ "$status_connected_result" -eq 0 ] || result=1
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
echo "STACKCHAN_BRIDGE_FIRMWARE_READY_SEEN=$([ "$firmware_ready_result" -eq 0 ] && echo 1 || echo 0)"
if [ "{allow_missing_firmware_ready}" != "1" ]; then
  [ "$firmware_ready_result" -eq 0 ] || result=1
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
exit $result
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
