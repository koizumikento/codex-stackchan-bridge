# Quality Gates

This document defines the quality gates for this repository. These gates are intended to keep the Codex skill, CLI, ROS 2 interfaces, and firmware moving together without relying on hardware for every change.

## Principles

- Every command path must be testable without physical hardware.
- The mock backend and bridge backend must share the same command contract.
- Single-device and multi-device behavior must share the same `device_id` contract.
- Cross-layer contracts must be documented before implementation spreads across packages.
- Safety behavior must be validated at the firmware boundary, not only in the CLI.
- JSON output and structured errors are part of the public contract.

## Required Gates By Area

### Documentation

Required when changing architecture, interfaces, safety behavior, dependencies, or command semantics:

- Update the relevant document under `docs/`.
- Keep package READMEs focused on package-local setup and link back to `docs/`.
- Update `AGENTS.md` when a decision should guide future agents.

### stackchanctl

Required for CLI changes:

- Unit tests for command parsing and validation.
- Mock backend tests for deterministic JSON.
- Error-shape tests for ROS `error_code` and CLI `error.code` mapping, plus `message` and `recoverable`.
- Metadata tests for `device_id`, `command_id`, `source`, `created_at`, and `priority`.
- Device selection tests for default device and `--device <device_id>`.
- Success semantics tests for `ACCEPTED`, `COMPLETED`, `REJECTED`, and `TIMEOUT` states.
- Human output remains compact; `--json` remains machine-readable.

### ROS 2 Interfaces

Required for message, service, or action changes:

- Interface definitions build successfully.
- New command-bearing interfaces include required metadata.
- Namespaces follow `/stackchan/<device_id>`.
- Response/error shapes follow the documented error model.
- Interface changes are reflected in `docs/ros-interface.md`.
- QoS and heartbeat decisions are documented when implementation touches status, events, IMU, audio chunks, or camera paths.

### Firmware

Required for firmware changes:

- Firmware build-only check passes for the supported board target.
- Safety limits remain firmware-owned.
- Calibration storage remains firmware NVS unless a documented decision changes it.
- Disconnect, audio underrun, mic overrun, camera failure, NFC failure, and servo/safety failure behavior remains documented.
- Any change touching hardware control preserves resource arbitration order:

```text
safety > motion stop/neutral > audio capture/playback > command handling > camera > LED/idle
```

### Codex Skill

Required for skill changes:

- Skill calls `stackchanctl`, not raw `ros2` commands.
- Skill behavior works against the mock backend.
- User-facing command timing and failure behavior is documented if it changes.

### Rust Companion Workers

Required before adding or expanding Rust workers:

- The hot path or deployment need is measured or clearly documented.
- The worker preserves the same command metadata and error model as the Python CLI.
- The Python CLI can call or supervise the worker through a narrow boundary.
- Setup and failure modes are documented.

## CI Targets

The expected CI shape is:

- GitHub Actions on Ubuntu 24.04.
- Python lint and unit tests for `apps/stackchanctl`.
- Mock backend contract tests.
- Multi-device/default-device contract tests.
- ROS 2 interface contract checks for `ros/stackchan_msgs`; replace or supplement these with `colcon` interface build checks when a ROS 2 Jazzy CI image is available.
- ROS 2 bridge package tests for hardware-free facade logic.
- Firmware contract checks for `firmware/m5stackchan-microros`; run PlatformIO build-only checks in a PlatformIO/micro-ROS-capable environment.

Deferred until implementation stabilizes:

- Markdown formatting checks.
- external link checks
- hardware-in-the-loop checks
- release packaging checks

## Manual Validation

Hardware validation is still required for behavior that depends on the physical device, but it should not be the only way to validate a change.

Manual hardware checks should cover:

- Face command rendering.
- Motion command safety and neutral behavior.
- LED command behavior.
- Audio playback and capture.
- Camera snapshot.
- NFC tag event reporting.
- IMU raw stream and high-level events.
- Disconnect and reconnect behavior.

## Merge Readiness

A change is ready when:

- The relevant automated gates pass or are explicitly marked unavailable.
- Mock backend behavior still works for affected commands.
- Cross-layer contract changes are documented.
- Safety-related changes include firmware-side validation notes.
- Known limitations are written down instead of left implicit.
