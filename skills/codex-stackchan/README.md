# codex-stackchan

Codex agent skill for expressing local work state through StackChan.

The skill calls `stackchanctl` for events such as starting work, waiting for user input, reporting test results, recovering from blockers, or finishing a task. It does not call raw ROS 2 commands.

See [SKILL.md](SKILL.md) for the active skill instructions.

## Validation

Use the mock backend when validating skill behavior:

```bash
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill face thinking --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill led success --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill motion nod --json
```

If `stackchanctl` exits non-zero, the skill should keep the user's main task moving and report the local StackChan issue only when useful.
