# AGENTS.md

This file gives working instructions for AI agents and maintainers editing this repository.

More specific `AGENTS.md` files may exist under package directories. When editing a file, follow the closest `AGENTS.md` first, then fall back to this root file for repository-wide policy.

## Project Goal

Build a local bridge that lets Codex use M5StackChan as a physical avatar through ROS 2.

The intended path is:

```text
Codex App -> Agent Skill -> stackchanctl -> ROS 2 nodes -> micro-ROS Agent -> M5StackChan firmware
```

Keep the system local-first. Do not introduce cloud accounts, mobile-app dependencies, or ad hoc network APIs unless the project direction explicitly changes.

## Canonical Docs

Start with `docs/README.md`.

Important design references:

- `docs/architecture.md`: overall ownership and layer boundaries
- `docs/stackchanctl.md`: CLI contract and language policy
- `docs/ros-interface.md`: ROS 2 topic/service/action boundaries
- `docs/firmware.md`: firmware responsibilities and safety behavior
- `docs/license-notes.md`: upstream dependency and reference policy
- `docs/quality-gates.md`: required validation gates before changes are considered ready

Package-specific agent instructions:

- `apps/stackchanctl/AGENTS.md`: Python CLI and backend rules
- `ros/stackchan_msgs/AGENTS.md`: ROS interface contract and compatibility rules
- `ros/stackchan_bridge/AGENTS.md`: PC-side bridge, routing, diagnostics, and multi-device rules
- `firmware/m5stackchan-microros/AGENTS.md`: PlatformIO firmware and device safety rules

When behavior crosses layers, document it in `docs/`. Keep package READMEs focused on local setup and package-specific notes.

## Fixed Architecture Decisions

- `stackchanctl` is a Python CLI using `rclpy`.
- Rust is only for companion workers on measured hot paths or long-running helper processes.
- `stackchanctl` calls ROS 2 topics, services, and actions directly for simple operations.
- Single-device and multi-device operation use the same `device_id` contract.
- ROS resources live under `/stackchan/<device_id>`, with `default` as the standard single-device id.
- ROS interfaces are feature-specific, not one generic command bus.
- Command-bearing interfaces must include `device_id`, `command_id`, `source`, `created_at`, and `priority`.
- Errors use `code`, `message`, and `recoverable`.
- The mock backend is required and must share the same command contract as the ROS 2 backend.
- Firmware owns safety-critical defaults and hard limits.
- PC-side config owns normal operation tuning.
- CLI config owns convenience settings such as backend selection and output format.
- The repository license is MIT.

## Firmware Policy

- Do not fork the M5Stack factory firmware as this repository's firmware base.
- Treat `m5stack/StackChan` factory firmware as reference material only.
- Prefer `m5stack/StackChan-BSP` for hardware access.
- Keep low-level hardware control in BSP/libraries where possible.
- This repository's firmware should focus on behavior adaptation, micro-ROS communication, device status, and safety behavior.
- Supported firmware capabilities include face, motion, LED, audio, camera, NFC, raw IMU, and sensors.
- Audio is a first-class capability.

## Data And Control Policy

- Send named intent commands first, not raw servo angles.
- Raw servo control is for debug/calibration only.
- Audio device exchange uses PCM 16 kHz mono 16-bit unless a documented decision changes it.
- PC side owns TTS, STT, VAD, and dialog policy.
- Firmware plays audio and captures microphone data.
- Camera support should start with explicit snapshot commands.
- NFC reports tag events and IDs; meaning is decided on the PC/Codex side.
- IMU exposes raw telemetry plus high-level events such as picked up, shaken, and tilted.

## Resource Priority

Device-side resource priority is:

```text
safety > motion stop/neutral > audio capture/playback > command handling > camera > LED/idle
```

Failures should degrade gracefully and publish structured status/errors where possible.

## Implementation Guidance

- Prefer small, explicit interfaces over large abstractions.
- Keep command contracts language-neutral even though `stackchanctl` is Python.
- Do not expose ROS 2 package names as the public CLI API.
- The public surface should stay like `stackchanctl <command> [args]`.
- Keep Codex skills calling `stackchanctl`, not raw `ros2` commands.
- Keep device selection on the CLI surface as `--device <device_id>`.
- Do not hide camera capture, NFC wait, or IMU streaming inside `observe`; keep them explicit commands.
- Preserve JSON output for machine use and compact human output for shell use.

## Expected Bootstrap Commands

The CLI contract should support at least:

```bash
stackchanctl say "hello"
stackchanctl face happy
stackchanctl --device desk face happy
stackchanctl motion nod
stackchanctl led progress
stackchanctl observe
```

Also expected:

```bash
stackchanctl audio play prompt.wav
stackchanctl audio capture --seconds 3 --output mic.wav
stackchanctl camera capture --output frame.jpg
stackchanctl nfc wait
stackchanctl imu stream --hz 10
```

## Dependency Policy

- Firmware target baseline is PlatformIO + Arduino framework.
- ROS 2 baseline is Jazzy.
- Pin firmware dependencies intentionally.
- Prefer `StackChan-BSP` by Git tag.
- Pin `micro_ros_platformio` to a verified commit SHA when release tags lag the needed ROS distro.
- Before copying upstream code, verify the exact license and preserve notices.
- Do not vendor large upstream firmware/app/server code into this repo without a documented reason.

## Testing And Validation

Use `docs/quality-gates.md` as the source of truth for validation gates.

No full test suite exists yet. When adding implementation, add focused tests around the boundary being introduced.

Expected validation areas:

- Python CLI unit tests
- Mock backend deterministic JSON
- ROS interface build checks
- Firmware build-only checks
- Contract tests for command metadata and structured errors

If a command cannot be represented in the mock backend, it is probably too vague.

## Git And Docs Hygiene

- Keep changes scoped to the layer you are editing.
- Update docs in the same change when a design decision or cross-layer contract changes.
- Do not rewrite unrelated files or reformat the whole repository.
- Do not revert user changes unless explicitly asked.
- The project currently works on `main`; avoid introducing branch/process requirements unless requested.
