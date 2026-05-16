---
name: stackchan-quality-gates
description: Validation workflow for codex-stackchan-bridge. Use before committing, pushing, or marking work complete, and when choosing tests or CI gates for changes to docs, stackchanctl, ROS 2 interfaces, the bridge, firmware, repo-local Codex agents, or repo-local Codex skills.
---

# StackChan Quality Gates

Use this skill to choose the smallest validation set that still covers the changed boundary.

## Read First

1. Read `docs/quality-gates.md`.
2. Read the closest `AGENTS.md` for the edited area.
3. Inspect `git status --short` and the diff before selecting checks.

## Gate Selection

- Docs-only changes: check links, references, terminology, and cross-document consistency.
- Agent config changes: validate TOML and confirm root `AGENTS.md` still lists routing accurately.
- Skill changes: run the skill validator and confirm `agents/openai.yaml` matches `SKILL.md`.
- CLI changes: run Python formatting/lint/tests when available and verify deterministic mock JSON.
- MCP stdio changes: verify JSON-RPC framing, stdout/stderr separation, mock tool results, and metadata propagation.
- ROS interface changes: build message packages and verify CLI/bridge/firmware docs use the same names.
- Bridge changes: run ROS package tests when available and cover device routing, errors, and multi-device separation.
- Firmware changes: run PlatformIO build-only checks when available and review safety/resource arbitration.
- Rust helper changes: run formatting, lint, and tests for the Rust crate when introduced.
- CI changes: validate workflow syntax and keep checks scoped to supported environments.

## Required Reporting

When finishing, state:

- Which checks ran.
- Which checks were unavailable and why.
- Whether docs or package instructions were updated with the behavior change.
- Any residual hardware-only risk that could not be validated locally.

Use `quality-ci-worker` for CI or broad validation changes. Use `docs-consistency-auditor` when quality-gate wording or repo routing changes.
