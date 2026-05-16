# Architecture Notes

## Core idea

Codex should not talk to StackChan through a cloud account, mobile app, or ad hoc network API. It should call a local command, and the local command should speak ROS 2.

```mermaid
flowchart LR
    Codex["Codex App"] --> Skill["Agent Skill"]
    Skill --> CLI["stackchanctl"]
    CLI --> Bridge["ROS 2 bridge nodes"]
    Bridge --> Agent["micro-ROS Agent"]
    Agent --> Firmware["M5StackChan firmware"]
    Firmware --> Hardware["Face / Servo / LED / Sensors"]
```

## Responsibility split

- Codex agent skill decides when a physical expression is useful.
- `stackchanctl` provides a small, stable command surface.
- ROS 2 nodes own routing, observation, and PC-side integration.
- micro-ROS firmware owns hardware control and safety limits.
- Shared message definitions keep the boundary explicit.

Layer details:

- CLI design: [stackchanctl.md](stackchanctl.md)
- ROS 2 interface: [ros-interface.md](ros-interface.md)
- Firmware design: [firmware.md](firmware.md)

Development decisions:

- `stackchanctl` will call ROS 2 directly for simple topic/service/action calls.
- `stackchanctl` is a Python `rclpy` CLI.
- Single-device and multi-device operation use the same contract through `device_id`.
- The default ROS namespace shape is `/stackchan/<device_id>`, with `default` as the default device id.
- Rust is a companion-worker language for measured hot paths or long-running workers, such as audio buffering, camera pre-processing, or high-rate IMU filtering.
- Rust workers must preserve the same command metadata and error contracts as the Python CLI.
- ROS interfaces are feature-specific rather than one generic command bus.
- Command-bearing interfaces include `command_id`, `source`, `created_at`, and `priority`.
- Errors use `code`, `message`, and `recoverable`.
- Firmware owns safety defaults; PC-side config owns normal tuning.
- Mock backend support is required for CLI and Codex skill development.
- Logs and CLI output should support structured JSON.
- Status, events, logs, and command results must include `device_id`.
- The repository license is MIT.
- Work can continue on `main` until release discipline is needed.

## Device identity

The project should support one or more StackChan devices through the same contract.

Rules:

- Every physical or mock StackChan has a `device_id`.
- `default` is the standard single-device id.
- `device_id` should use only ASCII letters, numbers, `_`, and `-`.
- ROS resources live under `/stackchan/<device_id>`.
- CLI commands select the target with `--device <device_id>`.
- If `--device` is omitted, CLI config may provide a default; otherwise use `default`.
- `device_id` is separate from `command_id`.
- Status, events, logs, and command results include `device_id`.

Example namespaces:

```text
/stackchan/default/status
/stackchan/default/face/set
/stackchan/desk/status
/stackchan/livingroom/audio/play
```

## Layer ownership

```mermaid
flowchart TB
    subgraph CodexLayer["Codex side"]
        Skill["Agent Skill\n- decide when expression is useful\n- call stackchanctl only"]
    end

    subgraph LocalLayer["Local PC side"]
        CLI["stackchanctl\n- stable command surface\n- mock or ros2 backend"]
        Bridge["ROS 2 bridge nodes\n- routing\n- observation\n- PC-side integration"]
        Msgs["stackchan_msgs\n- topic/service/action contracts"]
    end

    subgraph DeviceLayer["Device side"]
        Agent["micro-ROS Agent\n- transport boundary"]
        Firmware["M5StackChan firmware\n- hardware control\n- safety limits"]
        Hardware["M5StackChan hardware\n- display\n- servos\n- LEDs\n- sensors"]
    end

    Skill --> CLI
    CLI --> Bridge
    Bridge --> Msgs
    Msgs --> Bridge
    Bridge --> Agent
    Agent --> Firmware
    Firmware --> Hardware
```

## Hardware-free bootstrap

The repository should support useful development without hardware:

1. `stackchanctl` accepts `say`, `face`, `motion`, and `led`.
2. A mock backend logs normalized commands.
3. A ROS 2 backend publishes the same normalized commands.
4. The Codex skill uses only the CLI surface.
5. Rust is added only for measured worker boundaries.
