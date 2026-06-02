# codex-stackchan

Codex product skill for expressing local work state through StackChan.

This is the single Codex-facing StackChan skill. It calls `stackchanctl` for restrained cues such as starting work, waiting for user input, reporting test results, recovering from blockers, or finishing a task. It can also read StackChan-origin observations through `stackchanctl events`, but it does not call raw ROS 2 commands or treat event names as direct commands.

Keep the skill focused on product behavior:

- Work-state cues through face, LED, named motion, and short `say` messages.
- Avatar-style communication through short speech and expression when the user
  talks with StackChan directly. Motion should be a separate cue when it is
  known to be available.
- Spoken summaries for detail-heavy work; keep citations, logs, and long
  findings in text instead of reading them all aloud.
- Connected short spoken sentences instead of comma-separated keyword lists.
- Routine spoken summaries kept to one very short sentence so serial
  loaded-playback gaps stay rare.
- Detailed spoken explanations when requested, delivered as one compact,
  naturally punctuated `say` paragraph with 2-4 connected short sentences that
  preserve the key decision and reason. On serial hardware, aim for about
  20-30 Japanese characters total when that still conveys the point, and prefer
  about 20-25 characters when initial waiting is the main naturalness risk.
  The current best transport candidate is 20 Japanese characters.
  Prefer speech short enough to fit one loaded playback transaction, and keep
  the complete technical record in text instead of reading it all aloud.
- One naturally punctuated `say` per user-facing response by default. Long
  spoken responses should stay one CLI command; the bridge splits synthesized
  TTS audio internally when bounded firmware playback needs smaller segments.
- StackChan-origin events interpreted as observations, not instructions.
- Explicit camera snapshots for "what can you see?" style visual questions,
  routed through `stackchanctl camera capture`.
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
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill say --face happy --after-face happy "今日は電気をたべたよ" --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill events next --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill speech transcript mock-utt-001 --json
uv run --directory apps/stackchanctl stackchanctl --backend mock --source codex_skill camera capture --output tmp/stackchan-view.jpg --quality 80 --json
```

The `apps/stackchanctl` unit tests include hardware-free policy checks for this
skill. They guard against examples drifting to raw `ros2` commands,
maintenance/calibration controls, raw hardware controls, or undocumented cue
names:

```bash
uv run --directory apps/stackchanctl python -m unittest discover -s tests
```

If `stackchanctl` exits non-zero, the skill should keep the user's main task moving and report the local StackChan issue only when useful.
