# Custom Codex Agents

Project-scoped custom agents live in this directory. `.codex/config.toml` keeps delegation shallow with `max_depth = 1`.

Use agents by risk boundary, not just by folder.

## Reviewers And Scouts

- `interface-contract-steward`: read-only reviewer for `CommandMeta`, `Result`, `device_id`, `/cmd/...` vs `/device/...`, QoS, and topic/service/action contracts.
- `docs-consistency-auditor`: read-only reviewer for README/docs/AGENTS drift, stale wording, and cross-document contradictions.
- `firmware-safety-reviewer`: read-only reviewer for firmware safety, resource arbitration, calibration, and failure behavior.
- `dependency-license-scout`: read-only researcher for upstream dependencies, versions, licenses, and source-use constraints.

## Workers

- `stackchan-msgs-worker`: `ros/stackchan_msgs` interface definitions.
- `stackchanctl-worker`: `apps/stackchanctl` Python CLI, mock backend, bridge backend, JSON output, and tests.
- `ros-bridge-worker`: `ros/stackchan_bridge` facade nodes, device registry, routing, diagnostics, and multi-device separation.
- `firmware-bringup-worker`: `firmware/m5stackchan-microros` PlatformIO/micro-ROS bring-up and device-side handlers.
- `codex-skill-worker`: `skills/codex-stackchan` skill behavior that calls `stackchanctl`.
- `quality-ci-worker`: GitHub Actions, lint, build checks, mock contract tests, and quality gates.

## Recommended Pairings

- Interface changes: `stackchan-msgs-worker` plus `interface-contract-steward`.
- CLI changes: `stackchanctl-worker` plus `interface-contract-steward`.
- Bridge changes: `ros-bridge-worker` plus `interface-contract-steward`.
- Firmware changes: `firmware-bringup-worker` plus `firmware-safety-reviewer`.
- Skill changes: `codex-skill-worker` plus `docs-consistency-auditor`.
- CI changes: `quality-ci-worker`; add `docs-consistency-auditor` when quality-gate wording changes.
- Dependency or license questions: `dependency-license-scout`.

Reviewer and scout agents are read-only. Worker agents may edit only their owned areas unless explicitly instructed otherwise.
