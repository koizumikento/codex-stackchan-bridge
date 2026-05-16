# Containerized ROS 2 Environment

Use this environment when you want ROS 2 Jazzy readiness without installing ROS
2 directly on the Windows host or the base WSL2 distribution.

The host only needs Docker Desktop or another Docker engine. ROS 2, colcon,
rosdep, rclpy, and interface generation dependencies stay inside the
container.

## Build The Image

From the repository root:

```bash
docker build -f .devcontainer/Dockerfile -t codex-stackchan-ros2:jazzy .
```

## Run A Shell

On Windows PowerShell:

```powershell
docker run --rm -it -v ${PWD}:/workspaces/codex-stackchan-bridge -w /workspaces/codex-stackchan-bridge codex-stackchan-ros2:jazzy bash
```

On bash:

```bash
docker run --rm -it -v "$PWD":/workspaces/codex-stackchan-bridge -w /workspaces/codex-stackchan-bridge codex-stackchan-ros2:jazzy bash
```

Inside the container, ROS 2 is sourced automatically for interactive bash
shells. If a non-interactive command needs it, source it explicitly:

```bash
source /opt/ros/jazzy/setup.bash
```

## Hardware-Free Readiness Checks

Run these checks before hardware arrives:

```bash
source /opt/ros/jazzy/setup.bash
colcon build --packages-select stackchan_msgs
colcon build --packages-select stackchan_bridge
```

The build writes `build/`, `install/`, and `log/` at the repository root. These
directories are ignored by git and can be removed when you want a clean local
workspace.

## Ready-For-Device Checklist

Before the physical StackChan is connected, the goal is:

- The container image builds.
- `stackchan_msgs` builds with colcon.
- `stackchan_bridge` builds with colcon.
- Host-side mock tests still pass with `uv`.
- The remaining unchecked items are only device, micro-ROS Agent, firmware, and
  USB/serial passthrough behavior.

When hardware arrives, validate USB/serial passthrough separately before
claiming bridge-to-device behavior works. The exact passthrough command may
depend on Docker Desktop, WSL2, and the serial adapter path exposed by Windows.
