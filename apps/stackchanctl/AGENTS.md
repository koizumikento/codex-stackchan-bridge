# AGENTS.md

Instructions for agents editing `apps/stackchanctl`.

This directory owns the Python CLI. Follow this file for package-specific rules, and use the repository root `AGENTS.md` for repository-wide policy.

## Ownership

`stackchanctl` owns:

- The public local command surface used by humans and Codex skills.
- Command parsing and validation.
- Backend selection between `mock` and `ros2`.
- Device selection through `--device <device_id>`.
- Direct ROS 2 topic, service, and action calls through `rclpy`.
- Human-readable output and `--json` output.
- Command metadata creation and propagation.
- Structured error rendering.

`stackchanctl` does not own:

- Firmware safety limits.
- Low-level hardware behavior.
- TTS, STT, VAD, or dialog policy.
- Long-running audio, camera, or IMU streaming workers.
- Raw `ros2` command strings as the public API.

## Language And Runtime

- Implement the CLI in Python.
- Use `rclpy` for ROS 2 integration.
- Do not reimplement the public CLI in Rust.
- Rust may appear only as a companion worker behind a narrow process boundary when `docs/quality-gates.md` criteria are met.
- Keep command contracts language-neutral so workers and ROS nodes can share them.

## CLI Contract

The public shape should remain:

```bash
stackchanctl <command> [args]
```

Do not expose ROS 2 package names, topic names, or service names as the normal user-facing contract.

Device selection belongs on the CLI surface:

```bash
stackchanctl --device default observe
stackchanctl --device desk face happy
```

If `--device` is omitted, config may provide a default; otherwise use `default`.

Expected command groups:

- `say`
- `face`
- `motion`
- `led`
- `observe`
- `audio`
- `camera`
- `nfc`
- `imu`

Keep camera capture, NFC wait, and IMU streaming as explicit commands. Do not hide them inside `observe`.

## Backends

Support at least:

- `mock`: deterministic local behavior without ROS 2 or hardware.
- `ros2`: direct ROS 2 communication through `rclpy`.

The mock backend is required. If a command cannot be represented in the mock backend, the command is probably underspecified.

## Metadata And Errors

Every command-bearing request must carry:

- `device_id`
- `command_id`
- `source`
- `created_at`
- `priority`

Every structured error must include:

- `code`
- `message`
- `recoverable`

Human output should be compact. `--json` output is part of the machine-readable contract and must stay stable.

`device_id` must appear in JSON output, logs, status, events, and command results.

## Testing

For CLI changes, add or update tests for:

- command parsing
- validation
- mock backend JSON
- command metadata
- structured error shape
- backend selection

Do not require physical hardware for CLI tests.

## Documentation

- Update `../../docs/stackchanctl.md` when command semantics, language policy, backend behavior, output shape, or metadata changes.
- Update `../../docs/ros-interface.md` when CLI behavior depends on a ROS interface change.
- Update `../../docs/quality-gates.md` if validation expectations change.
