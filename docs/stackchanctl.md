# stackchanctl Design

`stackchanctl` is the stable local command surface between Codex and the robot system. Codex skills should call this CLI instead of constructing raw `ros2` commands.

## Goals

- Provide commands that are easy to use from both a shell and a Codex agent skill.
- Hide ROS 2 command details behind a small interface.
- Support a mock backend so skill behavior can be tested without hardware.
- Keep command names stable even if ROS 2 message details change.
- Send normal commands through the `stackchan_bridge` facade.
- Support one or more StackChan devices through the same `--device` contract.

## Non-goals

- Do not embed cloud authentication or remote account management.
- Do not run heavy AI inference inside the CLI.
- Do not bypass firmware-side safety limits for servo, LED, audio, or display behavior.
- Do not become the long-running bridge process.

`stackchanctl mcp serve` is allowed as a long-lived local adapter. It must not
take over bridge responsibilities such as routing, state aggregation, hardware
coordination, or ROS resource ownership.

## Implementation language

`stackchanctl` is a Python CLI that uses `rclpy` for ROS 2 integration.

This is an architectural decision, not a temporary default. `stackchanctl` is primarily a ROS 2 command surface and data-handling tool, not a real-time control loop. Python is the right fit for ROS 2 command calls, audio/image/NFC/IMU data handling, JSON output, mock testing, diagnostics, and Codex-facing iteration.

Rust is reserved for targeted companion workers where performance, binary distribution, or stronger type boundaries are clearly valuable. Rust workers should sit behind the same command metadata and error contracts rather than replace the Python CLI.

### Python responsibilities

Python owns:

- The `stackchanctl` executable and user-facing command surface.
- ROS 2 service and action calls to the `stackchan_bridge` facade through `rclpy`.
- Command parsing, config loading, JSON output, and structured errors.
- Mock backend behavior and CLI tests.
- Normal-rate audio, image, NFC, IMU, and diagnostic data handling.
- Codex skill integration and automation ergonomics.

Risks:

- Packaging depends on a Python environment and the sourced ROS 2 environment.
- Startup latency may matter if the skill calls the CLI frequently.
- Type-level command modeling is weaker than Rust.

### Rust responsibilities

Rust is a companion-worker language, not the CLI language.

Rust can own:

- Audio chunk buffering, format conversion, or low-latency streaming helpers.
- Camera frame pre-processing where Python overhead becomes visible.
- IMU raw stream filtering at higher rates.
- Long-running local workers where predictable resource use matters.
- Future single-binary helper tooling around a stable command contract.

Rust should not own:

- The public `stackchanctl` command surface.
- The main ROS 2 command path unless there is a measured reason.
- Exploratory data-processing workflows where Python libraries are more effective.

Why Rust is constrained to workers:

- `rclrs` / `ros2_rust` exists, but ROS 2 Rust tooling is less central in the ecosystem than `rclpy` / `rclcpp`.
- Generated message integration adds setup complexity, especially on Jazzy.
- The CLI still depends on a ROS 2 environment even if the executable is Rust.
- Data exploration and debugging move faster in Python.

### Other options

- C++: better for low-level performance, but heavier for CLI iteration and testing.
- Go: good CLI ergonomics, but ROS 2 integration would add more glue.
- Shell wrapper: too brittle once services, actions, JSON output, and correlation IDs matter.

### Language policy

The language policy is:

- Build and maintain `stackchanctl` in Python with `rclpy`.
- Keep the command contract language-neutral.
- Introduce Rust only as a companion worker for measured hot paths or deployment needs.
- Prefer moving sustained streaming workloads into ROS nodes before turning the CLI into a long-running process.

Rust spikes are validation tasks, not decision blockers:

1. Can a Rust worker consume the same command metadata and error model?
2. Can it integrate with ROS 2 cleanly if needed?
3. Is the performance or packaging benefit large enough to offset the setup cost?

Do not block `stackchanctl` implementation on Rust validation.

### Current Rust research snapshot

As of 2026-05-16, Rust is viable but still needs a proof-of-fit before being added to the runtime path.

Observed `rclrs` / `ros2_rust` state:

- `ros2-rust/ros2_rust` is active, Apache-2.0 licensed, and latest release is 0.7.0.
- `rclrs` documents publishers, subscriptions, services, actions, parameters, logging, graph queries, timers, QoS, dynamic messages, and message generation.
- The Jazzy setup is heavier than Python: the documented Jazzy workspace pulls in ROS message repositories plus `rosidl_rust`, `rosidl_runtime_rs`, and examples.
- Open upstream issues mention Jazzy setup friction, generated-message dependency issues, executor overhead, and large-message allocation/copy behavior.
- Custom message packages are possible, but dynamic library and workspace sourcing details must be verified in our repo layout.

Implication for this project:

- Rust is attractive for strict command metadata, structured errors, mock-compatible workers, and performance-sensitive local helpers.
- Python is the chosen path for ROS 2 bridge-facade calls because `rclpy` is a core ROS 2 client library and the custom msg/srv/action path is well-trodden.
- Audio and camera data should not be routed through a Rust CLI hot path until throughput is measured. The CLI should trigger or inspect those flows; long-running transport belongs in ROS nodes.

Rust worker acceptance criteria:

1. Use the same `stackchan_msgs` command metadata and error model as the Python CLI.
2. Build cleanly in the documented ROS 2 Jazzy workspace.
3. Include `device_id`, `command_id`, `source`, `created_at`, and `priority` in the request.
4. Expose a narrow process boundary that Python can call or supervise.
5. Demonstrate a measured benefit over Python or a ROS node implementation.
6. Document exact setup steps, failure modes, and ownership boundary.

Decision rule:

- If a measured hot path appears and the Rust spike builds cleanly, add a Rust worker for that boundary.
- If the Rust spike requires fragile workspace hacks, keep the Python CLI and prefer ROS nodes for performance-sensitive work.

## ROS interaction model

The standard command path is:

```text
stackchanctl -> stackchan_bridge facade -> firmware
```

This keeps acknowledgement, status aggregation, diagnostics, audio/camera routing, and multi-device behavior in one PC-side place.

Direct CLI-to-device ROS calls are allowed only for diagnostics and bring-up. They should not become the normal Codex-facing path.

The PC-side `stackchan_bridge` nodes own:

- state aggregation
- richer behavior orchestration
- audio and camera routing
- diagnostics
- future policies that should stay out of firmware

The CLI should still avoid exposing ROS 2 topic, service, action, or package names as the public API.

## MCP stdio mode

`stackchanctl` may also expose the same command contract through a local MCP
server:

```bash
stackchanctl mcp serve --transport stdio --backend mock
stackchanctl mcp serve --transport stdio --backend bridge
```

This mode is a thin adapter for MCP hosts. It is not a new robot control path,
not an ad hoc network API, and not a replacement for `stackchan_bridge`.

Rules:

- The only baseline transport is `stdio`.
- `stdout` is reserved for MCP JSON-RPC framing.
- Logs, diagnostics, and debug output go to `stderr`.
- MCP tools use the same backend command contract and validation model as the shell CLI.
- MCP tools use the configured `mock` or `bridge` backend.
- MCP tools do not call raw `ros2` commands or firmware-side resources.
- Tool results preserve the CLI result shape inside the MCP result payload.
- Rejected commands and timeouts normally return tool results with `ok=false`,
  not MCP protocol errors.

Initial tools:

- `say`
- `face`
- `motion`
- `led`
- `observe`
- `events_list`
- `events_next`
- `events_clear`
- `speech_get_transcript`
- `power_status`
- `motion_pose`
- `motion_home`
- `motion_status`
- `audio_play`
- `audio_capture`
- `camera_capture`

MCP mode defaults `source` to `mcp_agent`. `command_id` is generated per tool
call and must not be copied from the MCP JSON-RPC request id.

The media tools use the same metadata-only result contract as the CLI. They do
not return PCM bytes, image bytes/base64, speech text, transcript text, raw NFC
tag IDs, raw IR codes, or protocol dumps. The mock backend returns deterministic
metadata-only results. The bridge backend may return structured
`UNSUPPORTED_FEATURE` results for audio and camera until firmware-confirmed
transport exists.

IR transmit is not part of the normal CLI or MCP command surface. Firmware may
publish bounded `ir_transmit_*` diagnostic events for explicitly contracted
local adapters, but `stackchanctl`, MCP tools, and normal logs must not expose
raw IR codes, protocol dumps, or arbitrary transmit payloads.

`nfc wait` remains a CLI/human observation surface until the bridge exposes a
bounded NFC wait facade. MCP clients should use event tools for NFC-related
observations for now.

`imu stream` remains a CLI/human diagnostic surface only. It is intentionally
not exposed as a finite MCP request/response tool because raw telemetry streams
need a separate streaming MCP contract before Codex-facing MCP clients can
consume them safely.

## Command groups

```bash
stackchanctl say "テスト終わったよ"
stackchanctl say --voice default "テスト終わったよ"
stackchanctl face happy
stackchanctl motion nod
stackchanctl motion pose --pan-deg 30 --tilt-deg 20 --speed 500
stackchanctl motion home --speed 500
stackchanctl motion status --json
stackchanctl led progress
stackchanctl observe
stackchanctl events next --json
stackchanctl speech transcript mock-utt-001 --json
stackchanctl power status --json
stackchanctl --device desk face happy
```

## Device selection

`stackchanctl` targets a StackChan device by `device_id`.

Rules:

- `--device <device_id>` selects the target device.
- If `--device` is omitted, CLI config may provide a default; otherwise use `default`.
- `device_id` should use only ASCII letters, numbers, `_`, and `-`.
- The ROS namespace for a device is `/stackchan/<device_id>`.
- The mock backend uses the same `device_id` behavior as the bridge backend.
- `device_id` must appear in JSON output, logs, status, events, and command results.
- `device_id` is separate from `command_id`.

Examples:

```bash
stackchanctl --device default observe
stackchanctl --device desk say "テスト終わったよ"
stackchanctl --device livingroom motion nod
```

### `say`

Requests speech output.

Expected backend behavior:

- Normalize text.
- Send a speech request to the bridge facade.
- Optionally select a bridge-owned voice profile with `--voice <profile>`.
- Optionally choose a face or motion while speaking when that policy is
  implemented.
- With the bridge backend and TTS enabled, return after local synthesis and the
  firmware-owned audio playback action reach a terminal result.
- With the mock backend, keep deterministic metadata-only behavior and do not
  synthesize audio.

The CLI/MCP command result must not print speech text, synthesized PCM,
provider request payloads, raw provider speaker IDs, or provider credentials.
The command metadata may include `text_length` and the selected
`voice_profile`.

Bridge TTS configuration belongs to `stackchan_bridge`, not CLI config. The CLI
may pass a profile name, but it must not own provider endpoints, secrets, or
speaker-ID safety policy.

### `face`

Requests a named expression.

Expected examples:

- `neutral`
- `happy`
- `thinking`
- `surprised`
- `sleepy`
- `error`

Rules:

- `duration_ms=0` means persistent until replaced by another command,
  safety/fault handling, or device reset.
- Repeating the same expression/duration is idempotent and must not enqueue
  another animation.
- Unknown expressions return `UNKNOWN_COMMAND`.
- `HIGH` may preempt lower-priority face state. External `SAFETY` priority is
  rejected with `INVALID_PRIORITY`.

### `motion`

Requests a named motion primitive.

Expected examples:

- `nod`
- `shake`
- `look-left`
- `look-right`
- `look-user`
- `idle`

The CLI should send intent, not raw servo angles. Low-level angle limits belong in firmware.

Named motion remains the normal Codex-facing behavior surface. Explicit pose
control is available only through constrained home-frame absolute-angle
subcommands:

```bash
stackchanctl motion pose --pan-deg 30 --tilt-deg 20 --speed 500 --json
stackchanctl motion home --speed 500 --json
stackchanctl motion status --json
```

Rules:

- `pan_deg` and `tilt_deg` are degrees in `frame=home`.
- `pan_deg` is yaw/head horizontal and accepts `-128.0..128.0`.
- `tilt_deg` is pitch/head vertical and accepts `0.0..90.0`.
- `speed` accepts `0..1000`; `0` means firmware default speed.
- `duration_ms` accepts `0` or `100..2000`; `0` means firmware default.
- Out-of-range explicit pose values are rejected, not clamped.
- `motion home` uses firmware-owned home behavior. It is not sent to firmware
  as an external `pose(0,0)` target.
- On the bridge backend, `motion pose` and `motion home` validate obvious
  bounds, then route through firmware-owned pose/home validation. They must not
  be reported as physical actuation success based on bridge-only synthetic
  telemetry.
- Raw servo ticks, PWM, torque, relative movement, continuous rotation, and
  home calibration are not normal CLI/MCP control surfaces.

Example JSON for a successful bridge-backed pose command:

```json
{
  "ok": true,
  "result_state": "ACCEPTED",
  "device_id": "default",
  "command_id": "018f...",
  "metadata": {
    "device_id": "default",
    "command_id": "018f...",
    "source": "human_cli",
    "created_at": "2026-05-17T00:00:00Z",
    "priority": "NORMAL"
  },
  "command": {
    "type": "motion.pose",
    "frame": "home",
    "pan_deg": 30.0,
    "tilt_deg": 20.0,
    "speed": 500,
    "duration_ms": 0
  }
}
```

`motion home` uses `command.type = "motion.home"`. `motion status --json`
returns a `pose` object with `frame`, `pan_deg`, `tilt_deg`, `moving`, `stale`,
and `stamp`. Stale pose telemetry, unsupported firmware, invalid calibration,
and servo read failures are non-success structured results.

### `led`

Requests a named LED pattern.

Expected examples:

- `off`
- `progress`
- `success`
- `warning`
- `error`
- `listening`

Rules:

- `duration_ms=0` means persistent until replaced by another command,
  safety/fault handling, or device reset.
- Repeating the same pattern/color/duration is idempotent and must not enqueue
  another animation.
- Unknown patterns return `UNKNOWN_COMMAND`.
- `HIGH` may preempt lower-priority LED state. External `SAFETY` priority is
  rejected with `INVALID_PRIORITY`.

### `observe`

Reads current status from the bridge.

Default output is compact and human-readable. With `--json`, the output uses this shape:

```json
{
  "device_id": "default",
  "connected": true,
  "device_state": "idle",
  "face": "neutral",
  "last_error": null
}
```

`observe --json` includes bounded diagnostic capability fields such as:

```json
{
  "capabilities": [
    {"name": "face", "state": "available"},
    {"name": "motion", "state": "unavailable", "detail_code": "CALIBRATION_INVALID"},
    {"name": "audio_playback", "state": "available", "queued": 1, "playing": true},
    {"name": "camera_snapshot", "state": "degraded", "detail_code": "CAMERA_INIT_FAILED"}
  ],
  "firmware_version": "stackchan-microros-0.1"
}
```

These fields are additive and diagnostic. They do not replace explicit commands
such as `power status`, `motion status`, `audio play`, `audio capture`, `camera
capture`, or event/transcript commands. `observe` stays low-rate and
metadata-only.

### Event commands

Event commands read bridge-normalized observations from StackChan. They are not
robot control commands, and Codex should treat returned events as observations
to interpret before choosing a later action.

Baseline examples:

```bash
stackchanctl events list --json
stackchanctl events next --json
stackchanctl events next --after <event_id> --timeout 0 --json
stackchanctl events tail --follow
stackchanctl events clear --json
```

Rules:

- `events list` returns recent buffered public events for the selected device.
- `events next` returns the next unread event for the CLI/MCP consumer cursor.
- No unread event returns `ok=true` with an empty `events` list.
- `events clear` clears the consumer cursor only. It does not delete the bridge
  ring buffer.
- `events tail --follow` is a human diagnostic command. Codex skills and MCP
  clients should use `events next` or `events list`. Follow mode streams
  human-readable output and is rejected with `--json`.
- JSON output includes `device_id`, `events`, and `cursor`.

Example JSON shape:

```json
{
  "ok": true,
  "result_state": "COMPLETED",
  "device_id": "default",
  "events": [
    {
      "event_id": "018f...",
      "device_id": "default",
      "event_name": "button_pressed",
      "source": "firmware",
      "stamp": "2026-05-17T00:00:00Z",
      "command_id": null,
      "payload": {}
    }
  ],
  "cursor": "018f..."
}
```

### Speech transcript commands

Speech transcripts are retrieved explicitly after a `transcript_ready` event.
The event payload carries an `utterance_id`; full transcript text is not placed
in normal event payloads or logs.

```bash
stackchanctl speech transcript <utterance_id> --json
```

The bridge stores transcripts in memory with a default 10 minute TTL.

### Power commands

Power telemetry is read explicitly instead of being folded into `observe`.

```bash
stackchanctl power status --json
```

The command returns the latest bridge-observed power status from
`/stackchan/<device_id>/cmd/power/status`. JSON output uses strict JSON:
unsupported numeric ROS fields such as NaN battery percentage are rendered as
`null`.

Example JSON shape:

```json
{
  "ok": true,
  "result_state": "COMPLETED",
  "device_id": "default",
  "power": {
    "voltage_v": 4.92,
    "current_ma": 184.0,
    "power_mw": 905.3,
    "percentage": null,
    "power_source": "usb",
    "charging": true,
    "powered": true,
    "low_battery": false,
    "brownout_risk": false,
    "fault_code": null,
    "stale": false,
    "stamp": "2026-05-16T00:00:03Z"
  }
}
```

### Audio commands

Audio is a first-class capability. The CLI should expose simple commands while keeping speech recognition, speech synthesis, and dialog policy on the PC side.

Baseline examples:

```bash
stackchanctl audio play prompt.wav
stackchanctl audio capture --seconds 3 --output mic.wav
```

Device exchange should use PCM 16 kHz mono 16-bit, even if the CLI accepts or writes WAV files for human convenience.
For bridge-backed playback, `stackchanctl audio play <path>` accepts PCM S16LE
16 kHz mono WAV input (`.wav`) or raw PCM input (`.pcm`). It does not read or
publish the file while firmware status reports `audio_playback` unavailable, so
metadata-only unsupported smokes do not require a real audio file.
Without `--wait`, `audio play` returns `ACCEPTED` after the bridge action goal
is accepted and the CLI-side chunks have been handed to the bridge ingress. Use
`--wait` only when the caller needs the firmware-owned playback action terminal
result; on serial hardware that wait can be much longer than the audio duration
while the micro-ROS action graph catches up.

Audio CLI and MCP results expose metadata only: `device_id`, `command_id`,
`result_state`, input/output path, duration, byte count, format, sample rate,
channels, and structured `error` fields. They must not include PCM payloads,
speech text, transcript text, or raw audio bytes.

Playback chunks use `/stackchan/<device_id>/device/audio/playback/chunks`;
capture chunks use `/stackchan/<device_id>/device/audio/chunks`. Both paths are
keyed by `device_id`, `command_id`, `direction`, and monotonic `sequence`.
Playback chunks use reliable, volatile, keep-last-8 QoS plus the
`/stackchan/<device_id>/audio/playback/next_chunk` recovery helper because
best-effort playback lost even short prompts in hardware smoke; capture chunks
remain best-effort, volatile, keep-last-8 observation telemetry.
Backpressure is not acknowledged per chunk. Malformed
chunks, wrong direction, wrong command id, sequence gaps, overrun, underrun,
and disconnects are structured command results or events.

The bridge backend accepts audio play/capture only after firmware status reports
`audio_playback` or `audio_capture` as available. Devices without
firmware-confirmed audio transport still return `UNSUPPORTED_FEATURE`. CLI JSON
reports the baseline metadata contract and never includes PCM bytes. The mock
backend keeps deterministic responses for CLI development.
When `audio_playback` is available, the bridge backend sends the public
`PlayAudio` action, then publishes playback chunks with the same `command_id`
on `/stackchan/<device_id>/cmd/audio/chunks` starting at sequence `0`. The
bridge buffers those command-ingress chunks and relays them to
`/stackchan/<device_id>/device/audio/playback/chunks` only after it observes
the firmware-owned `/stackchan/<device_id>/device/audio/play` goal acceptance.
The bridge also serves the same buffered chunks through
`/stackchan/<device_id>/audio/playback/next_chunk`; firmware can pull from that
helper after action acceptance and still validates sequence, format, and payload
bounds before speaker playback. Bridge-owned TTS uses a bounded topic relay
plus service recovery because serial micro-ROS service responses with audio
payloads can add enough round-trip latency to make speech stall. For
prebuffered TTS topic playback, the bridge keeps the same bounded chunks in the
pull-helper queue as a fallback for missing topic sequences; firmware ignores
duplicate sequences that arrive from both transports. After firmware has
advanced past the buffered chunks, the pull helper can report end-of-stream.
For topic-first sessions, a firmware request for a buffered sequence is first
treated as a bounded NACK: the bridge republishes the requested sequence plus a
small lookahead window on
`/stackchan/<device_id>/device/audio/playback/chunks` and returns an accepted
empty response. After repeated NACKs for the same sequence, the bridge may serve
that one fallback chunk in the service response and republish the same sequence
on the playback topic. Pull-only diagnostics remain available when
service-response PCM is the behavior under test. The pull
helper must not idle-close a prebuffered topic session while the bridge is still
publishing topic chunks, or firmware may finish after only the first short
fragments. Because serial micro-ROS playback chunks are still bounded command
payloads, the default relay avoids duplicating every
prebuffered TTS topic chunk and avoids publishing an entire long utterance at
once; pull requests advance a bounded topic lookahead window. The pull helper is
the fallback for missing sequences, and duplicate sequences that do occur are
harmless and ignored by firmware.
Firmware also keeps a bounded in-RAM jitter buffer for future playback
sequences so a late chunk on the serial micro-ROS topic path does not
immediately abort speech. This buffer only absorbs short ordering jitter; a
missing sequence still becomes structured `AUDIO_UNDERRUN` after the firmware
gap timeout.
Playback chunks are paced at the baseline 20 ms cadence from the CLI to the
bridge; the bridge owns device-session arming and must not rely on a fixed
sleep before forwarding to firmware. Invalid or unsupported input files return
structured errors; PCM bytes are never printed in normal output.
On K151, the firmware may request smaller buffered chunks more frequently
through the pull helper to fit the serial micro-ROS path, then aggregate those
transport chunks back into 20 ms M5Unified speaker frames before calling
`M5.Speaker.playRaw()`. This keeps transport tuning separate from the speaker
buffer lifetime required by the device library.
For longer speech, KOIZUMI-146 tracks an experimental loaded-playback
transaction because hardware smokes show that real-time topic/service retries
do not deliver TTS-sized PCM in order. In that design, `stackchanctl say` still
uses the bridge backend, but the bridge first writes bounded local PCM into a
firmware-owned, device-scoped playback buffer through
`/stackchan/<device_id>/device/audio/playback/load` with ACK-only responses,
then starts the normal firmware playback action for the same `command_id`. The
bridge uses this path for TTS by default when the firmware load service is
available; set `STACKCHAN_TTS_LOADED_PLAYBACK=0` to force the older topic-first
relay for diagnostics. This load path must not expose PCM, speech text, or raw
audio bytes in normal CLI output or MCP responses.
For KOIZUMI-111 diagnostics, developers can set
`STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES` to a bounded byte count such as
`64` to move the first playback segment into the action goal. Developers can
also set `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES` to an even byte count such as
`64`, `160`, or `640` while diagnosing serial micro-ROS payload limits. K151
bridge-owned TTS currently defaults to a `64` byte first-goal payload and
160 byte topic/pull transport chunks, then firmware aggregates accepted PCM
back into 20 ms speaker frames. The loaded playback transaction has a separate
`STACKCHAN_AUDIO_PLAYBACK_LOAD_CHUNK_BYTES` knob and defaults to 64 byte
service requests because K151 serial validation showed that 96 and 160 byte
`LoadAudioChunk` requests can time out before firmware callback response.
The TTS path can be forced back to pull-only diagnostics with
`STACKCHAN_AUDIO_PLAYBACK_PULL_ONLY=1`, but that is not the recommended speech
path on serial hardware because larger service responses may time out and tiny
responses add audible latency. These diagnostic settings are local bring-up
knobs, not a stable user-facing audio quality contract.

When `audio_capture` is available, the bridge backend subscribes to
`/stackchan/<device_id>/device/audio/chunks` before sending the public
`CaptureAudio` action, collects only `AudioChunk(direction=CAPTURE)` messages
with the matching `device_id` and `command_id`, and writes the collected PCM to
the requested WAV output path. Missing chunks, malformed metadata, odd byte
lengths, or sequence gaps return structured audio capture errors. Captured PCM
bytes are written only to the explicit output file and are not printed in
normal output, JSON, events, or diagnostics.

Audio command results should distinguish transport/session acceptance from
playback or capture completion. For example, a future `audio play --json` result
may report accepted metadata first, while final completion, underrun, queue
depth, and `playing` state come from action feedback, status, or bounded events.
The CLI should not block unrelated commands while waiting for long speaker
playback unless the user explicitly requests a wait mode.

### Camera commands

Camera support should start with snapshots rather than continuous streaming.

```bash
stackchanctl camera capture --output frame.jpg --quality 80 --json
```

The CLI should keep this as an explicit command instead of hiding image capture inside `observe`.

Camera JSON returns metadata only: output path, `format=jpeg`, `width=320`,
`height=240`, `quality`, byte size, command metadata, result state, and
structured errors. It must not inline base64, JPEG bytes, or image payloads in
JSON, MCP results, events, or normal logs.

Baseline camera capture is snapshot-only QVGA JPEG with `quality=1..95` and max
payload 96 KiB. Continuous streaming, follow mode, and video-like frame
sequences require a separate contract.

The bridge backend rejects camera capture with `UNSUPPORTED_FEATURE` until
firmware status reports `camera_snapshot` as available, then forwards the goal
through `/stackchan/<device_id>/cmd/camera/capture` to
`/stackchan/<device_id>/device/camera/capture` and writes the returned JPEG
payload to the explicit `--output` file. Missing, empty, non-JPEG, or oversized
payloads return structured camera capture errors. CLI JSON still reports the
baseline QVGA JPEG metadata contract and never includes JPEG bytes or base64.
If the firmware-owned camera action accepts a goal but does not deliver a
result before the bridge media-action timeout, the bridge reports
`CAMERA_CAPTURE_FAILED` instead of surfacing an unclassified CLI `TIMEOUT`.
The mock backend keeps deterministic camera validation behavior for CLI
development.

Camera command results should distinguish request acceptance from image
availability. A future implementation can accept a capture goal, then return
metadata only after frame acquisition, JPEG encode, size validation, and output
write complete. If any step fails, the result remains structured and should not
fall back to embedding image bytes in JSON.

### NFC commands

NFC should expose bridge-normalized events and bounded correlation references,
not application meaning or raw tag IDs.

```bash
stackchanctl nfc wait
```

The PC side or Codex skill decides what the tag means. Normal output, MCP event
results, and logs must not include raw NFC tag IDs, raw IR codes, or protocol
dumps. Use bounded references such as `tag_ref` or `remote_ref` when correlation
is needed. Raw IDs/codes are debug-only and require an explicit local diagnostic
path.

### IMU commands

IMU should expose high-level events and explicitly contracted raw telemetry.

```bash
stackchanctl imu stream --hz 10
```

If a raw stream command is introduced, the target is 10-30 Hz and the stream
contract must stay separate from finite JSON request/response commands.
`observe` remains low-frequency device/bridge status; raw telemetry must not be
folded into `observe` or `/status`. MCP tools should use bounded status/event
results unless a separate streaming MCP contract exists.

Strict JSON output converts unsupported numeric ROS values such as NaN to
`null`; fields such as `stale`, `saturated`, and
`calibration_available`/`calibration_unavailable` carry meaning explicitly.

### Maintenance commands

Normal CLI/MCP/Codex surfaces must not expose raw servo ticks, PWM, torque,
relative movement, continuous rotation, calibration writes, NVS import/export,
reset-to-default calibration, or maintenance unlocks.

The human-only maintenance surface starts with:

```bash
stackchanctl maintenance calibration status --json
stackchanctl maintenance calibration capture-neutral --confirm --json
stackchanctl maintenance calibration reset --confirm --json
```

It is opt-in for a local operator and is rejected when `source` is
`codex_skill`, `mcp_agent`, or any value other than `human_cli`.
`capture-neutral` and `reset` require `--confirm`; status is read-only. JSON
uses explicit command types such as `maintenance.calibration.status`,
`maintenance.calibration.capture-neutral`, and `maintenance.calibration.reset`.

The maintenance surface is not part of the Codex skill or MCP tool set. It must
not be reachable through routine `face`, `motion`, `led`, `observe`, or MCP
calls. The mock backend returns deterministic maintenance-shaped results for
CLI tests. The bridge backend returns `UNSUPPORTED_FEATURE` until a
firmware-owned maintenance service exists, so write/reset cannot bypass
firmware hard limits. Firmware NVS is the only calibration safety store; CLI
config must not store hardware safety values. For early K151 bring-up, a
firmware-local maintenance seed path is acceptable when it is documented in
`docs/hardware-validation.md` and keeps normal bridge facade resources under
`/stackchan/<device_id>/cmd/...` read-only with respect to calibration.

Calibration write commands, if added, must write only a validated
firmware-owned calibration record. They must not accept raw servo ticks, PWM,
torque, relative movement, continuous rotation, arbitrary NVS blobs, or CLI
config-derived safety limits. They must also provide or document a reset-to-
invalid path so hardware validation can prove `CALIBRATION_INVALID` remains
the default safety behavior for missing or corrupt calibration.

## Backend model

`stackchanctl` should support at least two backends:

- `mock`: logs normalized commands and returns deterministic responses.
- `bridge`: sends normalized commands to `stackchan_bridge`.

Terminology:

- `bridge backend` means the `stackchanctl` implementation backend named `bridge`.
- `stackchan_bridge facade` means the ROS-side service/action surface under `/stackchan/<device_id>/cmd/...`.

Diagnostic backends may exist separately, but they should not be the default Codex-facing path.

The command contract should be shared by both backends. If a command cannot be represented in the mock backend, it is probably too vague for the bootstrap command set.

## Success and waiting behavior

Default command success means the bridge facade returned a shared `Result` with `ok=true` and `state=ACCEPTED`.

Bridge acceptance means:

- command metadata is valid
- the target `device_id` is known and not in a disconnected state
- the request passed bridge-side policy checks
- the bridge has either completed the short service operation or accepted/forwarded the action goal to the next layer

It is not just receipt of a request.

Rules:

- Default mode waits for bridge acceptance, not physical completion.
- For action-backed facade commands, bridge acceptance means the facade action
  has returned its immediate shared `Result`; this must not be treated as
  physical behavior completion.
- `--wait` waits for behavior completion when the underlying action supports completion.
- `--timeout <duration>` bounds waiting for acceptance or completion.
- Rejection by bridge or firmware returns a non-zero exit code.
- Timeout returns a non-zero exit code with a recoverable structured error when retry is reasonable.
- `--json` output must expose the shared result state as `result_state`: `ACCEPTED`, `COMPLETED`, `REJECTED`, or `TIMEOUT`.
- Unknown devices fail immediately with `DEVICE_NOT_FOUND`.
- Configured but disconnected devices fail with `TRANSPORT_DISCONNECTED`.

This keeps short CLI calls fast while allowing Codex or humans to wait explicitly when timing matters.

## Command metadata

Every command sent through the CLI should carry correlation metadata.

Required fields:

- `device_id`
- `command_id`
- `source`
- `created_at`
- `priority`

Priority values:

- `LOW`
- `NORMAL`
- `HIGH`
- `SAFETY`

CLI and Codex commands may use `LOW`, `NORMAL`, or `HIGH`. `SAFETY` is reserved for bridge and firmware internal use.

Priority behavior:

- `LOW` is background/decorative.
- `NORMAL` is the default.
- `HIGH` may interrupt lower-priority face, LED, or motion behavior.
- CLI requests for `SAFETY` are rejected with `INVALID_PRIORITY`.

Suggested `source` values:

- `human_cli`
- `codex_skill`
- `mcp_agent`
- `test`

The CLI should print the `command_id` in human output and include it in JSON output.

## Error model

Errors should be structured as code, message, and recoverability.

The ROS shared `Result.error_code` maps to CLI JSON as `error.code`. CLI JSON should keep the shorter `code` key for readability while preserving the same value.

Example:

```json
{
  "ok": false,
  "result_state": "REJECTED",
  "device_id": "default",
  "command_id": "018f...",
  "error": {
    "code": "SERVO_LIMIT_EXCEEDED",
    "message": "motion nod rejected: y target out of range",
    "recoverable": true
  }
}
```

The CLI can render a short human-readable message by default, but `--json` should preserve the full structure.

## Configuration

Configuration should be split by risk.

- Firmware owns safety-critical defaults and hard limits.
- PC-side config owns normal operation tuning.
- CLI config owns user convenience, backend selection, default device, and output preferences.

The CLI must not be the only place where servo, LED, audio, or camera safety limits exist.

CLI config owns:

- default backend
- default device
- default output mode
- log level
- timeout defaults

CLI config must not own hardware safety limits, calibration, speech provider secrets, or raw device credentials.

CLI config path:

- `$XDG_CONFIG_HOME/stackchanctl/config.toml`
- fallback: `~/.config/stackchanctl/config.toml`

Environment variables may override convenience settings for automation:

- `STACKCHANCTL_BACKEND`
- `STACKCHANCTL_DEVICE`
- `STACKCHANCTL_OUTPUT`
- `STACKCHANCTL_LOG_LEVEL`
- `STACKCHANCTL_SOURCE`

Audio bring-up diagnostics may also use:

- `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES`
- `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES`
- `STACKCHAN_AUDIO_PLAYBACK_LOAD_CHUNK_BYTES`
- `STACKCHAN_AUDIO_PLAYBACK_PULL_ONLY`

## Mock backend

The mock backend is required, not optional.

It should:

- validate the same command shapes as the bridge backend
- emit deterministic JSON
- support command metadata
- simulate success and common failures
- provide deterministic event and transcript fixtures for event-policy tests
- avoid requiring ROS 2 or physical hardware

Example:

```bash
stackchanctl --backend mock face happy --json
stackchanctl --backend mock --device desk face happy --json
stackchanctl --backend mock audio play prompt.wav --json
stackchanctl --backend mock events next --json
stackchanctl --backend mock speech transcript mock-utt-001 --json
```

This lets the Codex skill and CLI tests advance before firmware bring-up is ready.

## Logging and observability

Recommended behavior:

- CLI default output is compact and human-readable.
- `--json` prints structured results.
- PC-side tools should use structured JSON logs.
- Firmware errors should surface through status/error ROS interfaces.
- Logs include `device_id`, `command_id` when available, `source` when available, and structured error fields.
- Do not log speech text, image payloads, NFC tag IDs, IR/raw remote codes, or
  secrets by default.
- Normal ROS events, command results, MCP tool results, and CLI JSON should use
  bounded references such as `tag_ref` or `remote_ref` instead of raw NFC tag
  IDs, raw IR codes, or protocol dumps.
- Debug opt-in output must stay local and should not be mixed with normal `--json` command output.

## Relationship to ROS 2

The CLI should not expose ROS 2 package names as its public API. It can use ROS 2 internally, but the user-facing surface should remain:

```bash
stackchanctl <command> [args]
```

ROS 2 mappings are documented in [ros-interface.md](ros-interface.md).
