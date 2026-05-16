---
name: codex-stackchan
description: Express Codex work state through a local M5StackChan using stackchanctl. Use when Codex should signal start, progress, waiting, test success/failure, or completion through StackChan.
---

# Codex StackChan

Use this skill to send small local expression cues to StackChan while Codex works.

## Rules

- Call `stackchanctl` only. Do not call `ros2` commands directly.
- Keep cues short and non-blocking unless the user explicitly wants to wait.
- Never let a StackChan failure block the user's main task.
- Use `source=codex_skill` through `STACKCHANCTL_SOURCE=codex_skill` or `--source codex_skill`.
- Respect `STACKCHANCTL_BACKEND`, `STACKCHANCTL_DEVICE`, and `STACKCHANCTL_OUTPUT` when they are already set.
- Prefer the mock backend for tests and dry runs.

## Event Mapping

Use these defaults:

- Work start: `stackchanctl face thinking` then `stackchanctl led progress`
- Waiting for user: `stackchanctl face neutral` then `stackchanctl led listening`
- Tests running: `stackchanctl face thinking` then `stackchanctl led progress`
- Tests passed: `stackchanctl face happy` then `stackchanctl led success`
- Tests failed: `stackchanctl face error` then `stackchanctl led error`
- Done: `stackchanctl motion nod` then `stackchanctl face happy`

Use `say` sparingly for short local announcements, for example:

```bash
stackchanctl say "テスト終わったよ"
```

## Environment

For Codex-originated commands, set:

```bash
STACKCHANCTL_SOURCE=codex_skill
```

For hardware-free validation, set:

```bash
STACKCHANCTL_BACKEND=mock
```

For a non-default device:

```bash
STACKCHANCTL_DEVICE=desk
```

## Failure Handling

If a command exits non-zero, continue the user's main task. Report the StackChan failure only when it helps the user diagnose the local setup. Do not retry in a tight loop.

## Mock Validation

Run these checks from the repository root:

```bash
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill face thinking --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill led progress --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill motion nod --json
```
