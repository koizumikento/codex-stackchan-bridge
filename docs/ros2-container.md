# Containerized ROS 2 Environment

Use this environment when you want ROS 2 Jazzy readiness without installing ROS
2 directly on your host machine.

The host only needs Docker Desktop or another Docker-compatible engine that can
run Linux containers. Windows, Linux, and macOS hosts should all use the same
repository runner commands below. ROS 2, colcon, rosdep, rclpy, and interface
generation dependencies stay inside the container.

The repository also includes an optional `compose.yaml` for local helper
services such as VOICEVOX. Compose is not the primary ROS 2 runner and does not
replace the Python helper scripts below; it is a convenience layer for services
that the bridge may call.

## Build The Image

From the repository root:

```bash
uv run --no-project python scripts/ros2_container.py build-image
```

## Run A Shell

From PowerShell, bash, zsh, or another local shell:

```bash
uv run --no-project python scripts/ros2_container.py shell
```

This opens a shell with the repository mounted at
`/workspaces/codex-stackchan-bridge`.

If you need the raw Docker command instead, adapt the host path syntax for your
local shell:

```bash
docker run --rm -it -v "$PWD":/workspaces/codex-stackchan-bridge -w /workspaces/codex-stackchan-bridge codex-stackchan-ros2:jazzy bash
```

Inside the container, ROS 2 is sourced automatically for interactive bash
shells. If a non-interactive command needs it, source it explicitly:

```bash
source /opt/ros/jazzy/setup.bash
```

## Optional Local TTS Service

Start a local VOICEVOX Engine service when validating
`/stackchan/<device_id>/cmd/say` with local TTS:

```bash
docker compose up -d voicevox
```

From a compose-attached bridge container, use:

```bash
STACKCHAN_TTS_ENDPOINT=http://voicevox:50021
```

From the existing Python Docker helpers or another container that reaches the
host-published port, use:

```bash
STACKCHAN_TTS_ENDPOINT=http://host.docker.internal:50021
```

The normal host URL is:

```bash
http://localhost:50021
```

The `ros2` compose profile is a convenience shell built from the same
micro-ROS Agent Dockerfile used by `scripts/microros_agent_container.py`:

```bash
docker compose --profile ros2 run --rm ros2
```

Keep using the Python helpers for the documented ROS 2 smoke, micro-ROS Agent,
host serial TCP bridge, stale-build guard, and hardware validation flows unless
a specific diagnostic calls for compose.

## Run A One-Off ROS Command

Use the `exec` subcommand for targeted diagnostics from the containerized ROS 2
environment:

```bash
uv run --no-project python scripts/ros2_container.py exec "source /opt/ros/jazzy/setup.bash && source install/setup.bash && ros2 topic list -t"
```

Hardware smoke tests that need to discover a micro-ROS Agent running in another
container can request Docker host networking:

```bash
uv run --no-project python scripts/ros2_container.py --network host exec "source /opt/ros/jazzy/setup.bash && source install/setup.bash && ros2 topic list -t"
```

## Hardware-Free Readiness Checks

Run the full containerized readiness check before hardware arrives:

```bash
uv run --no-project python scripts/ros2_container.py smoke
```

This runs the equivalent container-side commands:

```bash
source /opt/ros/jazzy/setup.bash
colcon build --packages-select stackchan_msgs stackchan_bridge
source install/setup.bash
python3 scripts/ros2_bridge_smoke.py
```

The build writes `build/`, `install/`, and `log/` at the repository root. These
directories are ignored by git and can be removed when you want a clean local
workspace.

The smoke script starts `stackchan_bridge_node` with
`device_connected:=false`, then calls `stackchanctl --backend bridge` through
ROS 2. It should pass without hardware by confirming that the configured
`default` device reports `TRANSPORT_DISCONNECTED`.

To simulate an already-connected facade while still staying hardware-free,
start the node with:

```bash
stackchan_bridge_node --ros-args -p device_connected:=true
```

## Ready-For-Device Checklist

Before the physical StackChan is connected, the goal is:

- The container image builds.
- `stackchan_msgs` builds with colcon.
- `stackchan_bridge` builds with colcon.
- `python3 scripts/ros2_bridge_smoke.py` confirms the no-device bridge path.
- Host-side mock tests still pass with `uv`.
- The remaining unchecked items are only device, micro-ROS Agent, firmware, and
  USB/serial passthrough behavior.

When hardware arrives, validate USB/serial passthrough separately before
claiming bridge-to-device behavior works. The exact passthrough command may
depend on the host OS, Docker engine, and serial adapter path exposed to the
container.

On Windows with Docker Desktop, a COM port may appear in the Docker Desktop WSL
VM as `/dev/ttyS*` but still fail when the Agent container opens it with
termios. The repository has a host-serial fallback that keeps `COM3` open on
Windows and presents it to the Linux Agent container through TCP and a
container PTY:

```powershell
uv run --no-project python scripts/microros_agent_container.py build-image
uv run --no-project --with pyserial python scripts/serial_tcp_bridge.py --serial-port COM3 --baud 921600 --host 0.0.0.0 --tcp-port 11411
uv run --no-project python scripts/microros_agent_container.py tcp-pty --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4
```

The repository Agent image is built from the same ROS 2 Jazzy base used for
`stackchan_bridge` and builds micro-ROS Agent with `micro_ros_setup`. Prefer it
over `microros/micro-ros-agent:jazzy` for bridge/CLI smoke tests so Python ROS
nodes and Agent dependencies remain ABI-aligned.

For a payload-level event smoke on Windows Docker Desktop, keep the host bridge
running and run the Agent plus `ros2 topic echo` in the same Agent container:

```powershell
uv run --no-project python scripts/ros2_container.py build
uv run --no-project python scripts/microros_agent_container.py tcp-pty-event-echo --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 6
```

The same-container smoke should print a
`stackchan_msgs/msg/StackChanEvent` with `event_name: firmware_ready`. A
current firmware also publishes a 1 Hz
`/stackchan/default/device/status [stackchan_msgs/msg/StackChanStatus]`
heartbeat; the bridge uses that heartbeat for liveness timeout and reconnect
tracking. A separate ROS 2 container may still see
`/stackchan/default/device/events [stackchan_msgs/msg/StackChanEvent]` in the
topic graph while `ros2 topic echo --once` times out; treat that as a Docker
Desktop cross-container DDS data path issue until the networking setup is
changed.

For a full bridge/CLI smoke against the same Agent transport, keep the host
serial TCP bridge running and use:

```powershell
uv run --no-project python scripts/microros_agent_container.py build-image
uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4
```

The runner builds `stackchan_msgs` and `stackchan_bridge` inside the Agent
container to avoid ROS 2 ABI mismatches, starts `stackchan_bridge` with
the normal disconnected default, runs
`stackchanctl --backend bridge observe --json`, and verifies that the observed
firmware liveness makes `/stackchan/default` available and that
`stackchanctl --backend bridge events list --json` sees `firmware_ready`.
Add `--face-check happy` to verify face command forwarding. Add
`--motion-check nod --motion-expected-error CALIBRATION_INVALID` to verify the
named motion path reaches firmware and returns the expected device-owned
calibration rejection before real servo motion is enabled.
Add `--disconnect-check` to stop the Agent after the connected check and verify
that the bridge returns `TRANSPORT_DISCONNECTED` after the status heartbeat
timeout. Add `--reconnect-check` to restart the Agent in the same container
after that disconnect check and verify that
`stackchanctl --backend bridge observe --json` returns `connected: true` again.
The reconnect runner also checks the buffered public events for at least two
`device_connected` events and at least one `device_disconnected` event.

Use the direct serial Agent runner only when the Linux container can really open
the device:

```bash
uv run --no-project python scripts/microros_agent_container.py serial --dev /dev/ttyS2 --baud 921600 --verbose 4
```
