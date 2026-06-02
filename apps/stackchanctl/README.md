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

Run the bridge backend from a host shell such as PowerShell through the
documented ROS 2 container workflow:

```bash
uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-live --replace --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4
uv run --directory apps/stackchanctl stackchanctl --backend bridge observe --json
```

If the host Python environment does not provide `rclpy` and `stackchan_msgs`,
the CLI delegates the bridge command into the running ROS 2 container named by
`STACKCHANCTL_BRIDGE_CONTAINER` or `stackchan-e2e-live` by default.

For repeated PowerShell commands after the project environment has been created,
using the package virtualenv entrypoint avoids the extra `uv run` startup cost:

```powershell
apps/stackchanctl/.venv/Scripts/stackchanctl.exe --backend bridge observe --json
apps/stackchanctl/.venv/Scripts/stackchanctl.exe --backend bridge say --face happy --after-face happy "できたよ" --json
```

Use `--wait` only when you need the terminal physical playback result or when
you intentionally chain another media command after speech.

Run the focused CLI tests:

```bash
uv run --directory apps/stackchanctl python -m unittest discover -s tests
```
