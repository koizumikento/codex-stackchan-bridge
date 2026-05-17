---
name: codex-stackchan
description: Express Codex work state through a local M5StackChan and read StackChan-origin observations by calling stackchanctl. Use when Codex should send restrained local cues or interpret events such as button, IMU, NFC, or transcript_ready without calling raw ROS 2 commands.
---

# Codex StackChan

Use this skill to make StackChan reflect Codex's work state with short local cues.

## Core Rules

- Call `stackchanctl` only. Do not call `ros2` commands directly.
- Keep cues short, local, and non-blocking unless the user explicitly asks to wait.
- Never let a StackChan command failure block the user's main task.
- Use `source=codex_skill` with `--source codex_skill` or `STACKCHANCTL_SOURCE=codex_skill`.
- Respect existing `STACKCHANCTL_BACKEND`, `STACKCHANCTL_DEVICE`, `STACKCHANCTL_OUTPUT`, and `STACKCHANCTL_TIMEOUT` values.
- Prefer the mock backend for validation, tests, dry runs, and examples.
- Do not send repeated cues for every small internal step. Cue meaningful state changes only.
- Use `motion pose`, `motion home`, and `motion status` only when the user
  explicitly asks for head-position control, calibration-oriented checks, or
  pose inspection. Routine state cues should keep using named motion such as
  `motion nod`.
- Treat "calibration-oriented checks" as read-only pose/status/home validation.
  Do not run calibration writes, maintenance unlocks, reset/export/import, raw
  servo controls, or `maintenance` commands unless the user explicitly enters a
  documented maintenance workflow.
- Never use raw servo ticks, PWM, torque controls, relative motion, or
  continuous rotation as normal Codex cues.
- Use only documented face names and LED patterns for routine cues.

## Command Pattern

For normal use, run one small command at a time:

```bash
stackchanctl --source codex_skill face thinking
```

When diagnosing or validating behavior, request JSON:

```bash
stackchanctl --backend mock --source codex_skill face thinking --json
```

When targeting a non-default device, use the public device contract:

```bash
stackchanctl --device desk --source codex_skill led progress
```

Do not override environment-provided backend, device, output, or timeout settings unless the user asks for a specific target or you are running hardware-free validation.

## Event Recipes

Use these defaults unless the user's context suggests a quieter cue:

- Work start: `stackchanctl face thinking` then `stackchanctl led progress`
- Meaningful progress: `stackchanctl led progress`
- Waiting for user input: `stackchanctl face neutral` then `stackchanctl led listening`
- Tests running: `stackchanctl face thinking` then `stackchanctl led progress`
- Tests passed: `stackchanctl face happy` then `stackchanctl led success`
- Tests failed: `stackchanctl face error` then `stackchanctl led error`
- Recoverable blocker: `stackchanctl face surprised` then `stackchanctl led warning`
- Done: `stackchanctl motion nod` then `stackchanctl face happy` then `stackchanctl led success`

Add `--source codex_skill` to each command unless `STACKCHANCTL_SOURCE=codex_skill` is already set.

## Observing StackChan Events

StackChan-origin events are observations, not commands. Read them through
`stackchanctl` or MCP tools, interpret them in the current Codex task context,
and only then decide whether to send a physical cue.

Use event reads sparingly:

```bash
stackchanctl --source codex_skill events next --json
stackchanctl --source codex_skill events list --json
```

Event policy:

- Treat `button_pressed` as a request for attention or push-to-talk, not as an
  automatic instruction.
- After `transcript_ready`, fetch the transcript explicitly with
  `stackchanctl speech transcript <utterance_id> --json` before deciding how to
  respond.
- Treat `picked_up`, `shaken`, and `tilted` as context hints. Do not assume
  `shaken` means cancel or retry unless the surrounding conversation supports it.
- Ignore repeated low-value events when responding would be noisy.
- Do not call raw `ros2` commands or subscribe to ROS topics directly.
- Do not treat NFC tag refs, IR/remote refs, event names, raw telemetry, or
  transcripts as direct commands.

Push-to-talk flow:

```text
button_pressed
  -> face listening / led listening when useful
  -> audio capture and local STT happen through bridge
  -> transcript_ready { utterance_id }
  -> fetch transcript
  -> choose say / face / motion / led / no action
```

Do not put speech transcripts, secrets, file contents, or long command output
into `say`.

## Voice Use

Use `say` sparingly. Prefer face, motion, and LED cues for routine work because they are less disruptive.

Good `say` messages are short and local:

```bash
stackchanctl --source codex_skill say "テスト終わったよ"
```

Avoid reading long summaries, secrets, file paths, command output, or private user content aloud. Do not use `say` for errors unless the user is likely waiting on the physical device.

## Failure Handling

If `stackchanctl` exits non-zero:

1. Continue the user's main task.
2. Do not retry in a tight loop.
3. Report the StackChan issue only when it helps the user fix local setup.
4. If JSON is available, preserve `error.code`, `message`, and `recoverable` when summarizing the problem.

Treat `REJECTED` and `TIMEOUT` result states as StackChan command outcomes, not as failures of the user's requested coding or research task.

## Quiet Mode

Skip cues when:

- The user asks for no physical notifications.
- The task is a tiny answer that finishes immediately.
- Multiple cues would be noisy during fast edit/test loops.
- A prior StackChan command in the same task already failed.

## Environment Reference

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

## Mock Validation

Run these checks from the repository root:

```bash
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill face thinking --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill led progress --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill motion nod --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill events next --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill speech transcript mock-utt-001 --json
```

Expected validation result:

- `ok` is `true`.
- `result_state` is `ACCEPTED` or `COMPLETED`.
- `metadata.source` is `codex_skill`.
- `device_id` matches the selected or default device.
