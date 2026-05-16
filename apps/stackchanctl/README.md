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
```
