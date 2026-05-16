# AGENTS.md

This file gives repository-wide instructions for AI agents and maintainers. Follow the closest package `AGENTS.md` first, then this root file.

## Project Goal

Build a local bridge that lets Codex use M5StackChan as a physical avatar through ROS 2.

```text
Codex App -> Agent Skill -> stackchanctl -> ROS 2 nodes -> micro-ROS Agent -> M5StackChan firmware
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
- `stackchanctl` is a Python CLI using `rclpy`.
- Rust is only for companion workers on measured hot paths or long-running helper processes.
- ROS resources live under `/stackchan/<device_id>`, with `default` as the standard single-device id.
- Command-bearing interfaces carry command metadata and return structured results as documented in `docs/ros-interface.md`.
- The mock backend is required and must share the same command contract as the bridge backend.
- Firmware owns safety-critical defaults and hard limits.
- The repository license is MIT.

## Documentation Policy

- Put design decisions and cross-layer contracts in `docs/`.
- Keep package READMEs focused on package-local setup and entrypoints.
- Update docs in the same change when behavior, contracts, safety policy, or validation expectations change.
- Do not duplicate detailed interface, firmware, CLI, or dependency rules in this root file; link to the canonical doc instead.

## Quality

Use `docs/quality-gates.md` before committing, pushing, or marking work complete.

No full test suite exists yet. When adding implementation, add focused tests around the boundary being introduced and report unavailable checks explicitly.

## Git Hygiene

- Keep changes scoped to the layer you are editing.
- Do not rewrite unrelated files or reformat the whole repository.
- Do not revert user changes unless explicitly asked.
- The project currently works on `main`; avoid introducing branch or release-process requirements unless requested.
