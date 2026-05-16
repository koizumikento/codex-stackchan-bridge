# AGENTS.md

Instructions for agents editing `ros/stackchan_msgs`.

This package owns the ROS 2 message, service, and action definitions. Follow this file for interface-specific rules, and use the repository root `AGENTS.md` for repository-wide policy.

## Ownership

`stackchan_msgs` owns:

- `.msg`, `.srv`, and `.action` definitions.
- Shared command metadata.
- Shared result/error structures.
- Device identity fields that keep single-device and multi-device behavior consistent.
- Interface stability rules for CLI, bridge, firmware, and Codex skill integration.

`stackchan_msgs` does not own:

- CLI command parsing.
- PC-side orchestration logic.
- Firmware hardware behavior.
- Business logic for Codex skill decisions.
- Transport-specific buffering or worker implementations.

## Interface Contract

Interfaces are the cross-layer contract. Keep them small, explicit, and boring.

Command-bearing interfaces must include:

- `device_id`
- `command_id`
- `source`
- `created_at`
- `priority`

Use `device_id` for target selection and `command_id` for request correlation. Do not conflate them.

Response-like interfaces must include a structured result shape:

- `ok`
- `error_code`
- `message`
- `recoverable`

Do not introduce ad hoc `accepted`, `success`, or `error` fields unless they wrap or map cleanly to the shared result shape.

## Device Namespace

ROS resources use:

```text
/stackchan/<device_id>/...
```

`default` is the standard single-device id. Mock and physical devices use the same identity contract.

## Topic / Service / Action Policy

- Use topics for state, telemetry, events, and chunk streams.
- Use services for short request/response operations such as setting face or LED.
- Use actions for long-running, cancellable, or progress-bearing operations such as motion, speech, audio capture/playback, and camera capture.
- Avoid one generic command envelope. Prefer feature-specific interfaces.

## Stability

- Treat interface changes as cross-layer changes.
- Prefer additive changes over renaming or removing fields.
- Document breaking changes in `../../docs/ros-interface.md`.
- Keep field names stable once implementation starts.
- Do not change metadata or result fields without updating CLI, bridge, firmware docs, and quality gates.

## Standard Types

Prefer standard ROS 2 types where they fit clearly, such as timestamps and sensor/image-like payloads. Use project-specific messages when the semantics are StackChan-specific.

Do not put large unbounded payloads into simple services when an action plus chunk topic is more appropriate.

## Testing

For interface changes:

- Run or document a ROS 2 interface build check.
- Add or update contract tests when generated messages are consumed by CLI or bridge code.
- Verify command-bearing interfaces include required metadata.
- Verify response-like interfaces use the shared result shape.

## Documentation

- Update `../../docs/ros-interface.md` for every interface change.
- Update `../../docs/quality-gates.md` if interface validation expectations change.
- Update package READMEs only for package-local setup notes.

