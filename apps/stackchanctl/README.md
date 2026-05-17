# stackchanctl

Local CLI for sending high-level commands from Codex or a human shell to the StackChan ROS 2 bridge.

`stackchanctl` is implemented as Python + `rclpy`. Rust belongs in companion workers for measured hot paths or long-running helper processes, not in the public CLI surface.

Design details live in [../../docs/stackchanctl.md](../../docs/stackchanctl.md).

Baseline examples:

```bash
stackchanctl say "hello"
stackchanctl face happy
stackchanctl motion nod
stackchanctl led progress
stackchanctl power status --json
```

MCP hosts can use the same command contract through local stdio:

```bash
stackchanctl mcp serve --transport stdio --backend mock
stackchanctl mcp serve --transport stdio --backend bridge
```

## Local development

Run the hardware-free mock backend with `uv`:

```bash
uv run --directory apps/stackchanctl stackchanctl --backend mock face happy --json
uv run --directory apps/stackchanctl stackchanctl --backend mock observe --json
uv run --directory apps/stackchanctl stackchanctl mcp serve --transport stdio --backend mock
```

Run the focused CLI tests:

```bash
uv run --directory apps/stackchanctl python -m unittest discover -s tests
```
