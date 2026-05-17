# Containerized ROS 2 Environment

Use this environment when you want ROS 2 Jazzy readiness without installing ROS
2 directly on your host machine.

The host only needs Docker Desktop or another Docker-compatible engine that can
run Linux containers. Windows, Linux, and macOS hosts should all use the same
repository runner commands below. ROS 2, colcon, rosdep, rclpy, and interface
generation dependencies stay inside the container.

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
