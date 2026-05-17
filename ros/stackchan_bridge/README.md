# stackchan_bridge

PC-side ROS 2 nodes for connecting the local CLI and Codex-facing workflow to StackChan.

This package should own orchestration that is too heavy or too environment-specific for the device firmware, while keeping physical safety limits enforced on the device side as well.

Interface details live in [../../docs/ros-interface.md](../../docs/ros-interface.md).

## Local development

The hardware-free facade core can be tested without ROS 2:

```bash
uv run --directory ros/stackchan_bridge --no-project python -m unittest discover -s tests
uv run --directory ros/stackchan_bridge --no-project --with ruff ruff check .
```

The `stackchan_bridge_node` entrypoint requires a sourced ROS 2 Jazzy environment.
Use [../../docs/ros2-container.md](../../docs/ros2-container.md) when you want
that environment isolated in Docker/devcontainer instead of installed on the
host.

The `stackchan_speech_node` entrypoint is scaffolded separately from the command
facade so AEC/VAD/ASR worker failures do not take down face, motion, LED, say,
or status commands. Speech design details live in
[../../docs/speech-design.md](../../docs/speech-design.md).

By default, `stackchan_bridge_node` configures the `default` device as present
but disconnected so hardware-free smoke tests can verify
`TRANSPORT_DISCONNECTED`. Use `--ros-args -p device_connected:=true` only when
you intentionally want to simulate an already-connected facade.
