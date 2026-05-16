# Architecture Notes

## Core idea

Codex should not talk to StackChan through a cloud account, mobile app, or ad hoc network API. It should call a local command, and the local command should speak ROS 2.

```text
Codex App -> Agent Skill -> stackchanctl -> ROS 2 -> micro-ROS -> M5StackChan
```

## Responsibility split

- Codex agent skill decides when a physical expression is useful.
- `stackchanctl` provides a small, stable command surface.
- ROS 2 nodes own routing, observation, and PC-side integration.
- micro-ROS firmware owns hardware control and safety limits.
- Shared message definitions keep the boundary explicit.

## First slice

The first implementation slice should work without hardware:

1. `stackchanctl` accepts `say`, `face`, `motion`, and `led`.
2. A mock backend logs normalized commands.
3. A ROS 2 backend can later publish the same normalized commands.
4. The Codex skill uses only the CLI surface.
