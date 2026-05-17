# AGENTS.md

Instructions for agents editing `ros/stackchan_bridge`.

This package owns PC-side ROS 2 bridge nodes. Follow this file for bridge-specific rules, and use the repository root `AGENTS.md` for repository-wide policy.

## Ownership

`stackchan_bridge` owns:

- PC-side routing between `stackchanctl`, ROS 2 interfaces, micro-ROS Agent, and firmware.
- The standard command facade used by `stackchanctl`.
- Device status aggregation.
- Device discovery or registration policy when it exists.
- Audio and camera routing that is too heavy for firmware.
- Diagnostics and structured logs.
- Coordination that should stay off the device.

`stackchan_bridge` does not own:

- The public CLI surface.
- Codex skill decision logic.
- Firmware hard safety limits.
- Low-level hardware control.
- ROS interface definitions.

## Device Identity

Bridge nodes must preserve the shared `device_id` contract.

Rules:

- Use `/stackchan/<device_id>/...` namespaces.
- `default` is the standard single-device id.
- Include `device_id` in status, events, logs, and command results.
- Do not treat `source` as authentication.
- Do not merge state from different devices without keeping device identity explicit.

## Bridge Role

The bridge should make the system easier to operate, not hide the contract.

Good bridge responsibilities:

- Accept normal CLI commands through stable service/action facades.
- Aggregate device and firmware status for `stackchanctl observe`.
- Route audio chunks and camera snapshots.
- Normalize diagnostics from firmware and PC-side workers.
- Redact, debounce, and buffer hardware-origin observations before exposing them
  to `stackchanctl`, MCP, or Codex-facing skills.
- Provide stable facades when firmware interfaces are lower-level than CLI commands.
- Coordinate multi-step behavior that is too heavy for firmware but still local.

Avoid:

- Owning hardware safety as the only safety layer.
- Inventing private command schemas that diverge from `stackchan_msgs`.
- Hiding long-running work behind fire-and-forget topics.
- Logging secrets, raw private audio text, or unnecessary image/NFC data.
- Treating event names, NFC tag IDs, IR codes, raw telemetry, or transcripts as
  direct commands.
- Treating direct CLI-to-device ROS calls as the standard path.

## ROS Interface Use

- Use interfaces from `ros/stackchan_msgs`.
- Do not define bridge-private ROS messages unless there is a documented reason.
- Services should return structured results.
- Actions should expose progress, completion, cancellation, and failure.
- Topics should be used for status, events, telemetry, and chunks.

## QoS And Timing

Use the baseline QoS choices from `../../docs/ros-interface.md`.

- Status heartbeat is 1 Hz.
- A device is considered disconnected after 3 missed heartbeats unless config overrides it.
- Status should be easy for late subscribers to observe.
- Events should avoid unbounded queues.
- Raw IMU and audio chunks should prefer bounded queues with clear drop behavior.
- Safety/fault signals should not be blocked by camera or audio work.

## Configuration And Logging

Bridge config owns normal operation tuning, not firmware hard limits.

Expected config areas:

- device ids and namespace mappings
- physical serial or hardware identity to `device_id` mappings
- bridge node names
- audio and camera routing limits
- log level and structured log output
- optional default device behavior for local development

Config paths:

- package defaults: `ros/stackchan_bridge/config/*.yaml`
- local overrides: `$XDG_CONFIG_HOME/codex-stackchan-bridge/bridge.yaml`
- fallback local overrides: `~/.config/codex-stackchan-bridge/bridge.yaml`

Device registry behavior:

- Unknown device ids return `DEVICE_NOT_FOUND`.
- Configured but disconnected devices return `TRANSPORT_DISCONNECTED`.
- Duplicate physical devices for the same `device_id` return `DEVICE_ID_CONFLICT`.
- The bridge keeps the first healthy binding until configuration or hardware state changes.

Logs must include:

- `device_id`
- `command_id` when available
- `source` when available
- structured error fields when failures occur

Apply redaction before logging secrets or sensitive user data.

Redaction rules:

- Speech text is redacted by default.
- Image payloads are never written to normal logs.
- NFC tag IDs, IR/raw remote codes, and similar identifiers may appear in
  events/results only when the relevant contract allows it, and logs should hash
  or redact them by default.
- Local debug opt-in may expose sensitive values only in developer logs, not in normal CLI `--json` output.

## Testing

For bridge changes:

- Add tests for routing and status aggregation where possible.
- Test multi-device separation with at least `default` and one non-default device id.
- Test structured error propagation.
- Test mock or simulated firmware paths before requiring hardware.

## Documentation

- Update `../../docs/ros-interface.md` when bridge behavior depends on interface changes.
- Update `../../docs/architecture.md` when bridge ownership changes.
- Update `../../docs/quality-gates.md` if bridge validation expectations change.
- Keep this package README focused on local setup and node entrypoints.
