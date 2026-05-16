# stackchanctl Design

`stackchanctl` is the stable local command surface between Codex and the robot system. Codex skills should call this CLI instead of constructing raw `ros2` commands.

## Goals

- Provide commands that are easy to use from both a shell and a Codex agent skill.
- Hide ROS 2 command details behind a small interface.
- Support a mock backend so skill behavior can be tested without hardware.
- Keep command names stable even if ROS 2 message details change.
- Call ROS 2 topics, services, and actions directly for simple operations.
- Support one or more StackChan devices through the same `--device` contract.

## Non-goals

- Do not embed cloud authentication or remote account management.
- Do not run heavy AI inference inside the CLI.
- Do not bypass firmware-side safety limits for servo, LED, audio, or display behavior.
- Do not become the long-running bridge process.

## Implementation language

`stackchanctl` is a Python CLI that uses `rclpy` for ROS 2 integration.

This is an architectural decision, not a temporary default. `stackchanctl` is primarily a ROS 2 command surface and data-handling tool, not a real-time control loop. Python is the right fit for ROS 2 command calls, audio/image/NFC/IMU data handling, JSON output, mock testing, diagnostics, and Codex-facing iteration.

Rust is reserved for targeted companion workers where performance, binary distribution, or stronger type boundaries are clearly valuable. Rust workers should sit behind the same command metadata and error contracts rather than replace the Python CLI.

### Python responsibilities

Python owns:

- The `stackchanctl` executable and user-facing command surface.
- Direct ROS 2 topic, service, and action calls through `rclpy`.
- Command parsing, config loading, JSON output, and structured errors.
- Mock backend behavior and CLI tests.
- Normal-rate audio, image, NFC, IMU, and diagnostic data handling.
- Codex skill integration and automation ergonomics.

Risks:

- Packaging depends on a Python environment and the sourced ROS 2 environment.
- Startup latency may matter if the skill calls the CLI frequently.
- Type-level command modeling is weaker than Rust.

### Rust responsibilities

Rust is a companion-worker language, not the CLI language.

Rust can own:

- Audio chunk buffering, format conversion, or low-latency streaming helpers.
- Camera frame pre-processing where Python overhead becomes visible.
- IMU raw stream filtering at higher rates.
- Long-running local workers where predictable resource use matters.
- Future single-binary helper tooling around a stable command contract.

Rust should not own:

- The public `stackchanctl` command surface.
- The main ROS 2 command path unless there is a measured reason.
- Exploratory data-processing workflows where Python libraries are more effective.

Why Rust is constrained to workers:

- `rclrs` / `ros2_rust` exists, but ROS 2 Rust tooling is less central in the ecosystem than `rclpy` / `rclcpp`.
- Generated message integration adds setup complexity, especially on Jazzy.
- The CLI still depends on a ROS 2 environment even if the executable is Rust.
- Data exploration and debugging move faster in Python.

### Other options

- C++: better for low-level performance, but heavier for CLI iteration and testing.
- Go: good CLI ergonomics, but ROS 2 integration would add more glue.
- Shell wrapper: too brittle once services, actions, JSON output, and correlation IDs matter.

### Language policy

The language policy is:

- Build and maintain `stackchanctl` in Python with `rclpy`.
- Keep the command contract language-neutral.
- Introduce Rust only as a companion worker for measured hot paths or deployment needs.
- Prefer moving sustained streaming workloads into ROS nodes before turning the CLI into a long-running process.

Rust spikes are validation tasks, not decision blockers:

1. Can a Rust worker consume the same command metadata and error model?
2. Can it integrate with ROS 2 cleanly if needed?
3. Is the performance or packaging benefit large enough to offset the setup cost?

Do not block `stackchanctl` implementation on Rust validation.

### Current Rust research snapshot

As of 2026-05-16, Rust is viable but still needs a proof-of-fit before being added to the runtime path.

Observed `rclrs` / `ros2_rust` state:

- `ros2-rust/ros2_rust` is active, Apache-2.0 licensed, and latest release is `v0.7.0`.
- `rclrs` documents publishers, subscriptions, services, actions, parameters, logging, graph queries, timers, QoS, dynamic messages, and message generation.
- The Jazzy setup is heavier than Python: the documented Jazzy workspace pulls in ROS message repositories plus `rosidl_rust`, `rosidl_runtime_rs`, and examples.
- Open upstream issues mention Jazzy setup friction, generated-message dependency issues, executor overhead, and large-message allocation/copy behavior.
- Custom message packages are possible, but dynamic library and workspace sourcing details must be verified in our repo layout.

Implication for this project:

- Rust is attractive for strict command metadata, structured errors, mock-compatible workers, and performance-sensitive local helpers.
- Python is the chosen path for direct ROS 2 calls because `rclpy` is a core ROS 2 client library and the custom msg/srv/action path is well-trodden.
- Audio and camera data should not be routed through a Rust CLI hot path until throughput is measured. The CLI should trigger or inspect those flows; long-running transport belongs in ROS nodes.

Rust worker acceptance criteria:

1. Use the same `stackchan_msgs` command metadata and error model as the Python CLI.
2. Build cleanly in the documented ROS 2 Jazzy workspace.
3. Include `command_id`, `source`, `created_at`, and `priority` in the request.
4. Expose a narrow process boundary that Python can call or supervise.
5. Demonstrate a measured benefit over Python or a ROS node implementation.
6. Document exact setup steps, failure modes, and ownership boundary.

Decision rule:

- If a measured hot path appears and the Rust spike builds cleanly, add a Rust worker for that boundary.
- If the Rust spike requires fragile workspace hacks, keep the Python CLI and prefer ROS nodes for performance-sensitive work.

## ROS interaction model

`stackchanctl` should call ROS 2 topics, services, and actions directly for simple operations.

The PC-side `stackchan_bridge` nodes are still useful for:

- state aggregation
- richer behavior orchestration
- audio and camera routing
- diagnostics
- future policies that should stay out of firmware

The CLI should not require a bridge node for every simple command if the ROS interface is already explicit.

## Command groups

```bash
stackchanctl say "テスト終わったよ"
stackchanctl face happy
stackchanctl motion nod
stackchanctl led progress
stackchanctl observe
stackchanctl --device desk face happy
```

## Device selection

`stackchanctl` targets a StackChan device by `device_id`.

Rules:

- `--device <device_id>` selects the target device.
- If `--device` is omitted, CLI config may provide a default; otherwise use `default`.
- `device_id` should use only ASCII letters, numbers, `_`, and `-`.
- The ROS namespace for a device is `/stackchan/<device_id>`.
- The mock backend uses the same `device_id` behavior as the ROS 2 backend.
- `device_id` must appear in JSON output, logs, status, events, and command results.
- `device_id` is separate from `command_id`.

Examples:

```bash
stackchanctl --device default observe
stackchanctl --device desk say "テスト終わったよ"
stackchanctl --device livingroom motion nod
```

### `say`

Requests speech output.

Expected backend behavior:

- Normalize text.
- Send a speech request to ROS 2.
- Optionally choose a face or motion while speaking.
- Return after the request is accepted, unless the caller explicitly chooses blocking behavior.

### `face`

Requests a named expression.

Expected examples:

- `neutral`
- `happy`
- `thinking`
- `surprised`
- `sleepy`
- `error`

### `motion`

Requests a named motion primitive.

Expected examples:

- `nod`
- `shake`
- `look-left`
- `look-right`
- `look-user`
- `idle`

The CLI should send intent, not raw servo angles. Low-level angle limits belong in firmware.

### `led`

Requests a named LED pattern.

Expected examples:

- `off`
- `progress`
- `success`
- `warning`
- `error`
- `listening`

### `observe`

Reads current status from the bridge.

Expected output should be machine-readable by default, likely JSON:

```json
{
  "device_id": "default",
  "connected": true,
  "state": "idle",
  "face": "neutral",
  "last_error": null
}
```

### Audio commands

Audio is a first-class capability. The CLI should expose simple commands while keeping speech recognition, speech synthesis, and dialog policy on the PC side.

Baseline examples:

```bash
stackchanctl audio play prompt.wav
stackchanctl audio capture --seconds 3 --output mic.wav
```

Device exchange should use PCM 16 kHz mono 16-bit, even if the CLI accepts or writes WAV files for human convenience.

### Camera commands

Camera support should start with snapshots rather than continuous streaming.

```bash
stackchanctl camera capture --output frame.jpg
```

The CLI should keep this as an explicit command instead of hiding image capture inside `observe`.

### NFC commands

NFC should expose events and tag IDs, not application meaning.

```bash
stackchanctl nfc wait
```

The PC side or Codex skill decides what the tag means.

### IMU commands

IMU should expose both high-level events and raw telemetry.

```bash
stackchanctl imu stream --hz 10
```

The raw stream target is 10-30 Hz.

## Backend model

`stackchanctl` should support at least two backends:

- `mock`: logs normalized commands and returns deterministic responses.
- `ros2`: sends normalized commands to ROS 2 topics, services, or actions.

The command contract should be shared by both backends. If a command cannot be represented in the mock backend, it is probably too vague for the bootstrap command set.

## Command metadata

Every command sent through the CLI should carry correlation metadata.

Required fields:

- `device_id`
- `command_id`
- `source`
- `created_at`
- `priority`

Suggested `source` values:

- `human_cli`
- `codex_skill`
- `test`

The CLI should print the `command_id` in human output and include it in JSON output.

## Error model

Errors should be structured as code, message, and recoverability.

Example:

```json
{
  "ok": false,
  "device_id": "default",
  "command_id": "018f...",
  "error": {
    "code": "SERVO_LIMIT_EXCEEDED",
    "message": "motion nod rejected: y target out of range",
    "recoverable": true
  }
}
```

The CLI can render a short human-readable message by default, but `--json` should preserve the full structure.

## Configuration

Configuration should be split by risk.

- Firmware owns safety-critical defaults and hard limits.
- PC-side config owns normal operation tuning.
- CLI config owns user convenience, backend selection, default device, and output preferences.

The CLI must not be the only place where servo, LED, audio, or camera safety limits exist.

## Mock backend

The mock backend is required, not optional.

It should:

- validate the same command shapes as the ROS 2 backend
- emit deterministic JSON
- support command metadata
- simulate success and common failures
- avoid requiring ROS 2 or physical hardware

Example:

```bash
stackchanctl --backend mock face happy --json
stackchanctl --backend mock --device desk face happy --json
stackchanctl --backend mock audio play prompt.wav --json
```

This lets the Codex skill and CLI tests advance before firmware bring-up is ready.

## Logging and observability

Recommended behavior:

- CLI default output is compact and human-readable.
- `--json` prints structured results.
- PC-side tools should use structured JSON logs.
- Firmware errors should surface through status/error ROS interfaces.

## Relationship to ROS 2

The CLI should not expose ROS 2 package names as its public API. It can use ROS 2 internally, but the user-facing surface should remain:

```bash
stackchanctl <command> [args]
```

ROS 2 mappings are documented in [ros-interface.md](ros-interface.md).
