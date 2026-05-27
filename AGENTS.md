# AGENTS.md

This file gives repository-wide instructions for AI agents and maintainers. Follow the closest package `AGENTS.md` first, then this root file.

## Project Goal

Build a local bridge that lets Codex use M5StackChan as a physical avatar through ROS 2.

```text
Codex App -> Agent Skill -> stackchanctl -> stackchan_bridge facade -> micro-ROS Agent -> M5StackChan firmware
Codex App -> MCP Host -> stackchanctl mcp serve -> stackchanctl command contract -> mock backend
Codex App -> MCP Host -> stackchanctl mcp serve -> stackchanctl command contract -> bridge backend -> stackchan_bridge facade -> micro-ROS Agent -> M5StackChan firmware
```

Keep the system local-first. Do not introduce cloud accounts, mobile-app dependencies, or ad hoc network APIs unless the project direction explicitly changes.

## Start Here

Start with `docs/README.md`. It links the canonical design docs for architecture, CLI behavior, ROS interfaces, firmware, licensing, and quality gates.

Package-specific instructions:

- `apps/stackchanctl/AGENTS.md`
- `ros/stackchan_msgs/AGENTS.md`
- `ros/stackchan_bridge/AGENTS.md`
- `firmware/m5stackchan-microros/AGENTS.md`

Development assistant surfaces:

- Custom subagents live in `.codex/agents/`; see `.codex/agents/README.md`.
- Repo-local development skills live in `.agents/skills/`.
- Product skills that this repository is building live under `skills/`.

## Fixed Boundaries

- The standard command path is `stackchanctl -> stackchan_bridge facade -> firmware`.
- Codex skills call `stackchanctl`, not raw `ros2` commands.
- Codex-facing MCP integrations may use `stackchanctl mcp serve`, but must still route through the `stackchanctl` command contract and must not call raw `ros2` commands.
- `stackchanctl` is a Python CLI using `rclpy`.
- Rust is only for companion workers on measured hot paths or long-running helper processes.
- ROS resources live under `/stackchan/<device_id>`, with `default` as the standard single-device id.
- Always write device-scoped ROS resources with the full namespace in docs,
  issues, and implementation notes. Use `/stackchan/<device_id>/device/...`
  for firmware-owned resources, `/stackchan/<device_id>/cmd/...` for bridge
  facade commands, and `/stackchan/<device_id>/...` without `/device` for
  bridge-owned public status, telemetry, and events. Do not use bare
  `/device/...` shorthand when describing actual topic/service/action names.
- Multi-StackChan support is by `device_id` namespace. Multiple sensors within
  one StackChan use fields such as `sensor_index`; `sensor_index` is not a
  replacement for `device_id` and must not route between devices.
- Command-bearing interfaces carry command metadata and return structured results as documented in `docs/ros-interface.md`.
- The mock backend is required and must share the same command contract as the bridge backend.
- Firmware owns safety-critical defaults and hard limits.
- High-risk feature surfaces such as audio streams, camera payloads, calibration or maintenance controls, raw sensor streams, and multi-step behavior orchestration need an explicit docs-level contract before implementation.
- Raw hardware controls, calibration writes, and maintenance operations must stay out of the normal Codex-facing command surface unless a documented design creates a separate maintenance path.
- Hardware-origin events and raw telemetry are observations, not commands. Codex or bridge policy may react to them, but firmware event names must not become direct command execution.
- TTS belongs on the local PC/bridge side. Do not route speech synthesis
  through cloud accounts, mobile apps, StackChan World, XiaoZhi, Alibaba-style
  service paths, or firmware-resident text handling unless a documented project
  direction explicitly changes this boundary.
- Treat local TTS engines such as VOICEVOX as optional external services. Do
  not vendor TTS engines or voice libraries into this repository without a
  documented license and distribution decision. Refer to voices by bridge-owned
  profile names, not provider-specific raw IDs, in Codex-facing commands.
- For default local TTS over serial hardware, audio payload bytes should use
  the documented loaded playback topic transaction, then one firmware
  `audio_playback_load` completion observation and the normal playback action
  result. Do not reintroduce per-chunk application service ACKs as the default
  TTS payload path.
- Treat `tts_finished`, bridge action completion, and loaded-playback drain as
  transport/software evidence only. Audible quality, intelligibility, volume,
  and naturalness require an explicit operator-listening result before marking
  audible-quality work done.
- Speech text, PCM audio, image payloads, NFC tag IDs, IR/raw remote codes, secrets, and similar sensitive payloads must be redacted from normal logs and avoided in public events unless the relevant contract explicitly allows bounded, local exposure.
- The repository license is MIT.

## Documentation Policy

- Put design decisions and cross-layer contracts in `docs/`.
- Keep package READMEs focused on package-local setup and entrypoints.
- Update docs in the same change when behavior, contracts, safety policy, or validation expectations change.
- Do not duplicate detailed interface, firmware, CLI, or dependency rules in this root file; link to the canonical doc instead.

## Hardware Bring-Up Practice

- Use `uv` for repository Python helpers and validation commands.
- For connected firmware work, prefer the repository PlatformIO helper over
  direct `esptool` calls. Use direct flashing tools only when a documented
  recovery or diagnostic path requires them.
- Treat Windows Docker Desktop serial access as suspicious until proven. If a
  COM port appears inside the Linux container or WSL VM but fails to open, use
  the documented host serial TCP bridge flow in `docs/hardware-validation.md`.
- During micro-ROS Agent bring-up, prefer same-container Agent, bridge, and
  smoke checks before blaming firmware. Docker Desktop can expose the ROS graph
  while still dropping cross-container DDS samples.
- For smoke harnesses, preserve early readiness observations such as
  `firmware_ready` across the whole run. Do not fail a successful media smoke
  just because a later paginated event query no longer includes an early
  readiness event.
- Docker compose may be used as an optional helper for local services such as
  VOICEVOX, but it must not replace the documented Python Docker helpers unless
  the repository deliberately changes its bring-up workflow. Keep Windows host
  serial bridge assumptions explicit when compose is involved.
- When adding firmware publishers, services, actions, or clients, check
  micro-ROS resource limits and regenerate `libmicroros` with matching entity
  counts. In particular, the bring-up firmware needs more than the upstream
  default single service once both face and motion firmware services exist.
- For uncalibrated hardware, `CALIBRATION_INVALID` from firmware is a valid
  safety result, not a failed command path. Only count servo-actuating motion as
  complete after an explicit maintenance/calibration path has loaded valid
  firmware-owned calibration.
- Record hardware failures, workarounds, and smoke results in the relevant
  Linear issue before marking bring-up work complete. Create focused subissues
  for the next physical risk instead of hiding it in a broad parent issue.

## Quality

Use `docs/quality-gates.md` before committing, pushing, or marking work complete.

No full test suite exists yet. When adding implementation, add focused tests around the boundary being introduced and report unavailable checks explicitly.

## Git Hygiene

- Keep changes scoped to the layer you are editing.
- Do not rewrite unrelated files or reformat the whole repository.
- Do not revert user changes unless explicitly asked.
- The project currently works on `main`; avoid introducing branch or release-process requirements unless requested.
