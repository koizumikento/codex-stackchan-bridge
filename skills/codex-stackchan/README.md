# codex-stackchan

Codex product skill for expressing local work state through StackChan.

This is the single Codex-facing StackChan skill. It calls `stackchanctl` for restrained cues such as starting work, waiting for user input, reporting test results, recovering from blockers, or finishing a task. It can also read StackChan-origin observations through `stackchanctl events`, but it does not call raw ROS 2 commands or treat event names as direct commands.

Keep the skill focused on product behavior:

- Work-state cues through face, LED, named motion, and short `say` messages.
- StackChan-origin events interpreted as observations, not instructions.
- Speech observations handled through explicit transcript lookup, without
  automatic physical actions.
- Quiet-mode decisions when physical feedback would be noisy or private.

Do not split this skill until the speech, event-observation, or cue workflows become large enough to need separate routing.

See [SKILL.md](SKILL.md) for the active skill instructions.

## Validation

Use the mock backend when validating skill behavior:

```bash
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill face thinking --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill led progress --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill motion nod --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill events next --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill speech transcript mock-utt-001 --json
```

The `apps/stackchanctl` unit tests include hardware-free policy checks for this
skill. They guard against examples drifting to raw `ros2` commands,
maintenance/calibration controls, raw hardware controls, or undocumented cue
names:

```bash
uv run --directory apps/stackchanctl python -m unittest discover -s tests
```

If `stackchanctl` exits non-zero, the skill should keep the user's main task moving and report the local StackChan issue only when useful.
