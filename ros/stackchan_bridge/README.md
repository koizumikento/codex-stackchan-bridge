# stackchan_bridge

PC-side ROS 2 nodes for connecting the local CLI and Codex-facing workflow to StackChan.

This package should own orchestration that is too heavy or too environment-specific for the device firmware, while keeping physical safety limits enforced on the device side as well.

Interface details live in [../../docs/ros-interface.md](../../docs/ros-interface.md).

## Local development

The hardware-free facade core can be tested without ROS 2:

```bash
uv run --directory ros/stackchan_bridge python -m unittest discover -s tests
uv run --directory ros/stackchan_bridge ruff check .
```

The `stackchan_bridge_node` entrypoint requires a sourced ROS 2 Jazzy environment.
