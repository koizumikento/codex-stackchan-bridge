---
name: stackchan-dev-workflow
description: Repository development workflow for codex-stackchan-bridge. Use when Codex is asked to plan, implement, review, or route work in this repository, especially changes spanning docs, firmware, ROS 2 packages, stackchanctl, repo-local Codex agents, or repo-local Codex skills.
---

# StackChan Dev Workflow

Use this skill to orient development work in `codex-stackchan-bridge` before editing.

## Start Here

1. Read the root `AGENTS.md`.
2. Read `docs/README.md`, then the closest relevant docs:
   - Architecture or boundary work: `docs/architecture.md`
   - CLI work: `docs/stackchanctl.md`
   - ROS interfaces: `docs/ros-interface.md`
   - Firmware: `docs/firmware.md`
   - Dependencies or source use: `docs/license-notes.md`
   - Validation: `docs/quality-gates.md`
3. Read the closest package `AGENTS.md` before editing files under `apps/`, `ros/`, or `firmware/`.

## Route Work

Use repo-scoped custom agents from `.codex/agents/` when delegation is requested or helpful:

- Interface changes: `stackchan-msgs-worker`, then `interface-contract-steward`.
- CLI changes: `stackchanctl-worker`, then `interface-contract-steward`.
- Bridge changes: `ros-bridge-worker`, then `interface-contract-steward`.
- Firmware changes: `firmware-bringup-worker`, then `firmware-safety-reviewer`.
- Skill changes: `codex-skill-worker`, then `docs-consistency-auditor`.
- CI or validation changes: `quality-ci-worker`.
- Dependency, license, or upstream questions: `dependency-license-scout`.

Keep delegation shallow. `.codex/config.toml` intentionally sets `max_depth = 1`.

## Preserve Project Decisions

- Keep the standard control path as `stackchanctl -> stackchan_bridge facade -> firmware`.
- Keep Codex skills calling `stackchanctl`, not raw `ros2` commands.
- Keep ROS resources under `/stackchan/<device_id>`, with `default` as the single-device default.
- Use feature-specific ROS interfaces rather than a generic command bus.
- Keep `stackchanctl` in Python with `rclpy`; use Rust only for measured companion workers or long-running helpers.
- Treat firmware safety limits as device-owned and PC-side configuration as normal tuning.

## Finish Work

Update docs in the same change when a design decision or cross-layer contract changes. Before committing or pushing, use `$stackchan-quality-gates` to select the validation surface.
