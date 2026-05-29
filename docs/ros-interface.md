# ROS 2 Interface Design

This document describes the baseline contract between `stackchanctl`, PC-side ROS 2 nodes, and M5StackChan firmware.

Avoid using version labels in this document unless a released compatibility policy exists. Treat the sections below as the intended baseline contract, with scaffold limitations called out inline where the current implementation deliberately returns `UNSUPPORTED_FEATURE` or acceptance-only results.

## Interface principles

- Prefer named commands over raw hardware values.
- Support single-device and multi-device operation through the same `device_id` contract.
- Use topics for state, telemetry, events, and bounded chunk streams.
- Use services for request/response operations.
- Use actions for long-running behavior that needs progress or cancellation.
- Keep message definitions small and stable.
- Publish device state separately from command requests.
- Use USB Serial as the first micro-ROS transport.
- Keep audio, camera, NFC, and IMU as explicit interfaces instead of hiding them behind generic status blobs.
- Prefer feature-specific message, service, and action types over one generic command envelope.
- Include command correlation metadata in command-bearing interfaces.
- Return structured errors with code, message, and recoverability.
- Route normal CLI commands through the `stackchan_bridge` facade.
- Reserve direct CLI-to-device ROS calls for diagnostics and bring-up.
- Do not use command topics for normal control.

## Device identity and namespace

Every ROS interface belongs to a device namespace:

```text
/stackchan/<device_id>/...
```

Rules:

- `default` is the standard single-device id.
- `device_id` should use only ASCII letters, numbers, `_`, and `-`.
- `device_id` is part of the ROS namespace and should also appear in status, events, logs, and command results.
- `device_id` is not a substitute for `command_id`; they solve different problems.
- Mock devices use the same namespace and `device_id` rules as physical devices.
- Write full ROS resource names when documenting implementation work. Bare
  `/device/...` is only an informal suffix, not an actual ROS path.
- Firmware-owned resources live under `/stackchan/<device_id>/device/...`.
  Bridge facade commands live under `/stackchan/<device_id>/cmd/...`.
  Bridge-owned public status, telemetry, and events live directly under
  `/stackchan/<device_id>/...`.
- Multi-StackChan support is achieved by separate `device_id` namespaces.
  Multiple sensor elements on one StackChan stay on the same device topic and
  are identified by message fields such as `sensor_index`.

Examples:

```text
/stackchan/default/status
/stackchan/default/cmd/face/set
/stackchan/default/device/events
/stackchan/desk/status
/stackchan/desk/cmd/motion/run
/stackchan/desk/device/proximity/raw
```

## Bridge facade and device interface

The public command surface is the bridge facade. `stackchanctl` calls only facade services and actions during normal operation.

Facade namespace:

```text
/stackchan/<device_id>/cmd/...
```

Device-side namespace:

```text
/stackchan/<device_id>/device/...
```

Rules:

- `cmd` resources are owned by `stackchan_bridge` and are the stable CLI-facing ROS surface.
- `device` resources are owned by firmware and may be lower-level, but they must still use `stackchan_msgs` contracts.
- Do not shorten device-side resources to `/device/...` in plans or issues
  unless the surrounding sentence explicitly says it is a suffix. The actual
  resource always includes `/stackchan/<device_id>`.
- Bridge facade calls validate input, verify target device availability, route to the device side, aggregate status, and normalize errors.
- CLI code must not call `device` resources except in explicit diagnostics or bring-up commands.
- Firmware must not depend on CLI-specific behavior.

## Baseline shared messages

### `CommandMeta`

IDL shape:

```text
string<=32 device_id
string<=36 command_id
string<=32 source
builtin_interfaces/Time created_at
uint8 priority

uint8 PRIORITY_LOW=0
uint8 PRIORITY_NORMAL=1
uint8 PRIORITY_HIGH=2
uint8 PRIORITY_SAFETY=3
```

This metadata lets `stackchanctl`, bridge nodes, firmware, logs, and status messages refer to the same request.
MCP-originated commands use the same metadata contract; the recommended
`source` value is `mcp_agent`.

Priority values:

- `LOW`
- `NORMAL`
- `HIGH`
- `SAFETY`

`SAFETY` is reserved for bridge and firmware internal use.

### `Result`

IDL shape:

```text
bool ok
uint8 state
string<=48 error_code
string<=160 message
bool recoverable

uint8 STATE_ACCEPTED=1
uint8 STATE_COMPLETED=2
uint8 STATE_REJECTED=3
uint8 STATE_TIMEOUT=4
```

State mapping:

- `ACCEPTED`: bridge validated the request, confirmed the target device path is available, and accepted or forwarded the request.
- `COMPLETED`: the requested behavior completed successfully.
- `REJECTED`: bridge or firmware rejected the request.
- `TIMEOUT`: acceptance or completion exceeded the caller's timeout.

For `ACCEPTED` and `COMPLETED`, `ok` is true. For `REJECTED` and `TIMEOUT`, `ok` is false. CLI JSON uses these states directly rather than inventing separate result names.

### Field type defaults

Use these field types unless a message definition documents a narrower type:

```text
string<=32 name
string<=32 pattern
string<=16 color
uint32 duration_ms
float32 intensity
string<=512 text
string<=64 voice
string<=32 face_hint
string<=32 motion_hint
string<=16 format
uint32 sample_rate
uint8 channels
uint8 quality
```

Rules:

- `intensity` is 0.0 to 1.0.
- `quality` is 1 to 95 for JPEG capture.
- media `format` values are lower-case strings such as `pcm_s16le` or `jpeg`, except `AudioChunk` which uses compact numeric constants.

### `CompressedImagePayload`

`CompressedImagePayload` is retained for compatibility with the initial
camera action shape:

```text
string<=16 format
uint8[<=98304] data
```

`format` is `jpeg` for the baseline camera contract. The payload limit is
96 KiB. New default camera transport must not put JPEG bytes in action result
responses; use `/stackchan/<device_id>/device/camera/chunks` instead and leave
the compatibility action-result payload empty.

### `CameraFrameChunk`

Camera snapshot payload bytes use bounded chunks:

```text
uint8 JPEG=1

string<=32 device_id
string<=36 command_id
uint32 sequence
uint32 total_chunks
uint32 total_bytes
uint8 format
uint32 width
uint32 height
uint8 quality
bool end_of_stream
uint8[<=256] data
```

`format=JPEG`, `width=320`, `height=240`, and `total_bytes<=98304` are the
baseline. Firmware sends these chunks over best-effort topic transport with a
small inter-chunk pace rather than putting the JPEG in the action result.
Receivers correlate chunks by `device_id` and `command_id`, require contiguous
`sequence` values from `0`, and write payload bytes only to the explicit
capture output file.

Baseline error codes:

- `UNKNOWN_COMMAND`
- `UNSUPPORTED_FEATURE`
- `SERVO_LIMIT_EXCEEDED`
- `SERVO_READ_FAILED`
- `MOTION_INTERRUPTED`
- `CALIBRATION_INVALID`
- `AUDIO_UNDERRUN`
- `MIC_OVERRUN`
- `AUDIO_CAPTURE_FAILED`
- `AUDIO_FORMAT_UNSUPPORTED`
- `MALFORMED_AUDIO_CHUNK`
- `ASR_UNAVAILABLE`
- `ASR_TIMEOUT`
- `ASR_WORKER_FAILED`
- `ASR_EMPTY_RESULT`
- `ASR_INVALID_OUTPUT`
- `TRANSCRIPT_NOT_FOUND`
- `STALE_TELEMETRY`
- `CAMERA_CAPTURE_FAILED`
- `NFC_READ_FAILED`
- `TRANSPORT_DISCONNECTED`
- `FIRMWARE_BUSY`
- `TIMEOUT`
- `INVALID_DEVICE_ID`
- `DEVICE_NOT_FOUND`
- `DEVICE_ID_CONFLICT`
- `INVALID_PRIORITY`

## Device discovery and conflicts

The bridge owns device registry and conflict handling.

Rules:

- `stackchanctl` does not wait for discovery by default.
- Unknown `device_id` returns `DEVICE_NOT_FOUND`.
- A configured but disconnected device returns `TRANSPORT_DISCONNECTED`.
- Duplicate physical devices claiming or mapping to the same `device_id` return `DEVICE_ID_CONFLICT`.
- The bridge keeps the first healthy device binding and rejects conflicting bindings until configuration or hardware state changes.
- Physical serial or hardware identity is mapped to `device_id` in bridge configuration, not in CLI arguments.

## Priority execution semantics

Command priority affects queueing and preemption:

- `LOW`: queued behind `NORMAL` and `HIGH`; never preempts active behavior.
- `NORMAL`: default; FIFO within the same device and resource class.
- `HIGH`: may preempt `LOW` and `NORMAL` face, LED, and motion behaviors; should not preempt safety handling.
- `SAFETY`: bridge/firmware internal only. Externally supplied `/cmd/...`
  requests with `SAFETY` priority are rejected with `INVALID_PRIORITY`; do not
  treat caller-provided `source` as authentication.
- Same-priority commands are FIFO unless a resource-specific safety rule overrides them.

## Baseline topics

### `/stackchan/<device_id>/status`

Purpose: publish current device and bridge state.

Fields:

- `device_id`
- `connected`
- `state`
- `face`
- `motion`
- `last_command_id`
- `last_error`
- `firmware_version`
- `capabilities`

Recommended IDL details:

- strings are bounded to 32 characters unless the field is an error/message field.
- `last_error` uses the shared `Result` shape.
- `connected` reflects current registry/transport availability, not whether the
  previous command succeeded. A healthy device may still report a historical
  command rejection in `last_error` until a later command result replaces it.
- A configured device may transition to connected when `stackchan_bridge`
  observes a firmware-origin event on `/stackchan/<device_id>/device/events`,
  such as `firmware_ready`. The bridge should not require a static
  `device_connected=true` override for real hardware smoke once firmware events
  are flowing.
- Firmware publishes `/stackchan/<device_id>/device/status` at 1 Hz while the
  micro-ROS Agent session is healthy. `stackchan_bridge` treats this as the
  liveness heartbeat, republishes the aggregated public
  `/stackchan/<device_id>/status`, and returns `TRANSPORT_DISCONNECTED` after
  3 missed status heartbeats unless `liveness_timeout_sec` is overridden.
- `capabilities` is a bounded additive status field and does not replace
  feature-specific interfaces. Capability records include `name`, `state`,
  `detail_code`, `active`, `queued`, and `last_update`, where `state` is one of
  `available`, `unavailable`, `degraded`, or `fault`.
- Capability status is for diagnostics and routing hints only. Commands must
  still return their own shared `Result`, and telemetry/payload data must stay
  on explicit topics, services, or actions.
- Useful aggregated activity hints include audio `queued`/`playing`, camera
  snapshot availability, firmware version, and adapter initialization state.
  These hints must not include PCM bytes, speech text, image bytes, NFC tag IDs,
  raw IR codes, or protocol dumps.

### `/stackchan/<device_id>/imu/raw`

Purpose: bridge-facing raw IMU telemetry for `stackchanctl imu stream` and PC-side consumers.

Fields mirror `/stackchan/<device_id>/device/imu/raw`.

The bridge may downsample or filter device telemetry, but it must preserve `device_id` and timestamps.

### `/stackchan/<device_id>/device/imu/raw`

Purpose: publish raw IMU telemetry.

Baseline rate: 10-30 Hz.

Fields:

- `device_id`
- `stamp`
- `accel`
- `gyro`
- `mag`
- `temperature`

The current K151 bring-up publishes this stream at the firmware scheduler's
10 Hz cadence when the CoreS3 IMU is available. High-level posture/activity
events remain separate on `/stackchan/<device_id>/device/events`, preserving the
rule that raw samples do not appear in `observe` or normal event payloads.

### `/stackchan/<device_id>/touch/state`

Purpose: public bridge-facing three-zone touch state for the official StackChan K151 body touch panel.

Fields mirror `/stackchan/<device_id>/device/touch/state`.

Message: `stackchan_msgs/TouchState`.

Fields:

- `device_id`
- `stamp`
- `zone_mask`
- `zone_count`
- `intensities`
- `surface`

Rules:

- `surface` defaults to `head` for the body touch panel.
- `zone_mask` uses `ZONE_1`, `ZONE_2`, and `ZONE_3`.
- `intensities` is bounded to 3 entries.
- Firmware may use the Si12T `OUTPUT1` register as a bounded fallback source
  when the BSP intensity array reports all zeros. The raw `OUTPUT1` byte is
  firmware-only diagnostic data and must not appear in normal `observe`, public
  events, or semantic touch event payloads.
- Raw capacitive baselines are not published in normal telemetry.

### `/stackchan/<device_id>/device/touch/state`

Purpose: firmware-origin touch telemetry that the bridge republishes publicly.

Fields mirror `/stackchan/<device_id>/touch/state`.

### `/stackchan/<device_id>/proximity/raw`

Purpose: public low-rate proximity telemetry for calibration, debugging, and future local behavior.

Fields mirror `/stackchan/<device_id>/device/proximity/raw`.

Message: `stackchan_msgs/ProximityRaw`.

Fields:

- `device_id`
- `stamp`
- `sensor_index`
- `distance_m`
- `signal`
- `raw`
- `saturated`

Rules:

- Baseline rate is 2-10 Hz.
- `distance_m` may be NaN when the sensor is not calibrated for distance.
- `signal` is normalized `0.0..1.0` when available.
- K151 semantic events use a low LTR553 signal threshold because early live
  capture observed `raw=3` / `signal≈0.001465` as the first usable manual
  stimulus. Firmware emits `proximity_near` at `signal >= 0.0010` and
  `proximity_clear` at `signal <= 0.0005`; raw samples remain telemetry-only
  and semantic event payloads stay bounded.

### `/stackchan/<device_id>/device/proximity/raw`

Purpose: firmware-origin LTR-553ALS-WA proximity telemetry.

Fields mirror `/stackchan/<device_id>/proximity/raw`.

### `/stackchan/<device_id>/light/raw`

Purpose: public low-rate ambient light telemetry.

Fields mirror `/stackchan/<device_id>/device/light/raw`.

Message: `stackchan_msgs/LightRaw`.

Fields:

- `device_id`
- `stamp`
- `sensor_index`
- `illuminance_lux`
- `raw`
- `saturated`

Rules:

- Baseline rate is 1-5 Hz.
- `illuminance_lux` may be NaN when calibration is unavailable.

### `/stackchan/<device_id>/device/light/raw`

Purpose: firmware-origin LTR-553ALS-WA ambient light telemetry.

Fields mirror `/stackchan/<device_id>/light/raw`.

### `/stackchan/<device_id>/power/status`

Purpose: public power and battery telemetry from INA226 and AXP2101 surfaces.

Fields mirror `/stackchan/<device_id>/device/power/status`.

Message: `stackchan_msgs/PowerStatus`.

Fields:

- `device_id`
- `stamp`
- `voltage_v`
- `current_ma`
- `power_mw`
- `percentage`
- `power_source`
- `charging`
- `powered`
- `low_battery`
- `brownout_risk`
- `fault_code`

Rules:

- Baseline rate is 0.2-1 Hz.
- Use NaN for unsupported numeric fields such as uncalibrated `percentage`.
- `percentage` is `0.0..1.0` when available.
- Raw power telemetry is not stuffed into `/status`; `/status.connected` remains transport/registry availability.

### `/stackchan/<device_id>/device/power/status`

Purpose: firmware-origin power telemetry for bridge republishing and `stackchanctl power status`.

Fields mirror `/stackchan/<device_id>/power/status`.

### `/stackchan/<device_id>/motion/pose`

Purpose: public bridge-facing current head pose for explicit absolute head control and `stackchanctl motion status`.

Fields mirror `/stackchan/<device_id>/device/motion/pose`.

Message: `stackchan_msgs/HeadPose`.

Fields:

- `device_id`
- `stamp`
- `pan_deg`
- `tilt_deg`
- `moving`
- `frame`

Rules:

- `frame` is `home` in the baseline contract.
- `pan_deg` and `tilt_deg` are degrees in the home frame.
- BSP `X/Y` naming maps to yaw/pan and pitch/tilt angle axes, not a planar XY coordinate system.
- The bridge republishes only telemetry with the expected `device_id`.

### `/stackchan/<device_id>/device/motion/pose`

Purpose: firmware-origin current head pose.

Fields mirror `/stackchan/<device_id>/motion/pose`.

### `/stackchan/<device_id>/events`

Purpose: publish normalized high-level events useful to Codex and PC-side orchestration.

This is a public bridge-owned topic. Firmware does not publish directly to this
topic during normal operation; it publishes hardware-origin observations to
`/stackchan/<device_id>/device/events`, and `stackchan_bridge` normalizes,
redacts, debounces, buffers, and republishes them here.

Fields:

- `event_id`
- `device_id`
- `event_name`
- `source`
- `stamp`
- `command_id`
- `payload_json`

IDL constraints:

- `event_id` is `string<=36`.
- `device_id` and `event_name` are `string<=32`.
- `source` is `string<=32`.
- `command_id` is `string<=36`.
- `payload_json` remains `string<=256`.

Field semantics:

- `event_id`: event correlation id. Bridge must set one on public events and
  may preserve a firmware-provided id when valid.
- `device_id`: selected StackChan device id.
- `event_name`: bounded known event name.
- `source`: recommended values include `firmware`, `bridge`,
  `speech_session`, and `test`.
- `stamp`: event occurrence time. Bridge may use receive time when a device
  timestamp is unavailable or unreliable.
- `command_id`: command correlation id for command-origin events. Sensor-origin
  events may leave this empty.
- `payload_json`: bounded metadata only. It must not carry speech transcripts,
  image payloads, PCM audio, raw NFC tag IDs, raw IR/protocol dumps, or large
  data.

Baseline firmware/device event names:

- `picked_up`
- `placed_down`
- `shaken`
- `tilted`
- `face_up`
- `face_down`
- `button_pressed`
- `button_released`
- `button_held`
- `nfc_detected`
- `nfc_removed`
- `nfc_read_failed`
- `mic_overrun`
- `audio_playback_load`
- `audio_playback_underrun`
- `audio_capture_started`
- `audio_capture_finished`
- `audio_capture_failed`
- `camera_capture_failed`
- `battery_low`
- `battery_recovered`
- `charging_started`
- `charging_stopped`
- `power_source_changed`
- `brownout_risk`
- `power_fault`
- `touched`
- `touch_released`
- `touch_held`
- `proximity_near`
- `proximity_clear`
- `light_changed`
- `dark_detected`
- `bright_detected`
- `remote_button_pressed`
- `remote_button_released`
- `remote_button_held`
- `remote_command_received`
- `ir_transmit_started`
- `ir_transmit_finished`
- `ir_transmit_failed`
- `transport_unstable`

The `ir_transmit_*` event names are observations for explicitly contracted or
diagnostic transmit adapters. They do not define a normal `/cmd/ir` command
surface; IR transmit behavior needs a separate command contract before Codex or
MCP can request it.

Baseline bridge/PC event names:

- `speech_detected`
- `transcript_ready`
- `transcript_failed`
- `voice_semantic_event`
- `tts_started`
- `tts_finished`
- `tts_failed`
- `device_connected`
- `device_disconnected`
- `device_conflict_detected`

`transcript_ready` carries an `utterance_id` in `payload_json`; full transcript
text is retrieved through the speech transcript query service, not embedded in
the event.

`voice_semantic_event` carries metadata such as `utterance_id`, `confidence`,
`intent_hint`, `requires_codex`, `safety_action`, `echo_state`, and
`suppressed_reason`. It must not carry transcript text.

### `/stackchan/<device_id>/device/events`

Purpose: carry hardware-origin high-level events from firmware to the bridge.

Fields mirror `StackChanEvent`.

Rules:

- Firmware publishes only device facts such as button, IMU posture/activity,
  NFC presence, battery, transport, camera error, and audio buffer events.
- Firmware must not assign application meaning to tags, gestures, or speech.
- Bridge owns public normalization, redaction, and consumer buffering.
- Firmware may leave `event_id` empty; bridge fills it before republishing.
- Public events should use bounded correlation references such as `tag_ref` or
  `remote_ref` when identifier correlation is needed. Raw NFC tag IDs, raw IR
  codes, and protocol dumps are debug-only and require an explicit local
  diagnostic path.
- Firmware normal diagnostics must not print raw `payload_json` values that can
  bypass bridge redaction.
- K151 bring-up firmware sources high-level IMU, NFC, and IR/remote events from
  device adapters while keeping raw IMU samples, raw NFC IDs/UIDs, and raw IR
  codes out of public events. StackChan-BSP 1.1.0 has examples rather than
  dedicated NFC/IR wrapper members: NFC follows the BSP `M5UnitUnifiedNFC` on
  `M5.In_I2C` example, and IR follows the BSP `IRremoteESP8266` GPIO 10 receive
  example. These adapters may expose only safe diagnostic metadata such as
  bus/pin selection, I2C object availability, and counters. NFC uses `tag_ref`;
  IR uses `remote_ref`.

### `/stackchan/<device_id>/cmd/audio/chunks`

Purpose: carry bounded CLI-origin playback chunks from `stackchanctl` to the
bridge. This is a command payload ingress, not a firmware-owned topic. The
bridge buffers chunks by `device_id` and `command_id`, then relays them to
`/stackchan/<device_id>/device/audio/playback/chunks` only after the matching
firmware-owned playback action goal is accepted. A local diagnostic mode may
move sequence `0` into the public `PlayAudio` goal instead of this ingress
topic while the first-payload handoff is being validated.
The bridge also exposes
`/stackchan/<device_id>/audio/playback/next_chunk` so firmware can pull the
next bounded chunk after action acceptance when serial micro-ROS topic delivery
is unreliable.

Fields and bounds are the same as
`/stackchan/<device_id>/device/audio/playback/chunks`.
This ingress accepts `direction=PLAYBACK` only. Capture chunks are firmware
observations and must not be published on this command topic.
CLI-origin playback chunks include `total_chunks`, decoded `total_bytes`, and
`end_of_stream=true` on the final chunk. When the complete payload fits the
bounded command preload threshold, the bridge may preload it through the
firmware loaded-playback transaction before starting the firmware action.
Larger or incomplete payloads remain on the streaming relay path.
QoS is reliable, volatile, keep last 64. This is local command ingress between
`stackchanctl` and the bridge, not the serial micro-ROS firmware topic.

### `/stackchan/<device_id>/device/audio/playback/chunks`

Purpose: carry bounded playback audio chunks from the bridge to firmware for
playback flows coordinated by `/stackchan/<device_id>/device/audio/play`.

Fields, IDL constraints, and baseline format are the same as
`/stackchan/<device_id>/device/audio/chunks`. QoS is reliable, volatile, keep
last 16 because physical smokes showed best-effort playback chunks can be lost
even for short prompts. Missing or late sequences are still recoverable through
the `/stackchan/<device_id>/audio/playback/next_chunk` helper when possible,
and otherwise become structured `AUDIO_UNDERRUN`.
This firmware-owned input topic accepts `direction=PLAYBACK` only. It is
separate from capture output so the firmware does not need to publish and
subscribe on the same audio chunk topic
while micro-ROS is running over serial.

The same topic also carries loaded-playback payloads before the playback action
goal. In that mode, every chunk sets `total_chunks`, decoded `total_bytes`, and
`end_of_stream` on the final chunk. Firmware buffers and decodes those chunks
locally, then the normal `/stackchan/<device_id>/device/audio/play` action
provides the terminal confirmation. This avoids per-chunk application
request/response while preserving a final action result for the speech command.
The bridge paces loaded topic chunks with a local serial transport interval
instead of requiring per-chunk ACKs; current hardware validation uses 0.02 s.
The COM3 micro-ROS serial path completed short and longer loaded ADPCM TTS at
0.02 s, while 0.01 s and 0.005 s topic pacing caused sequence gaps.

`sequence` is monotonic per `command_id` plus `direction`. At most one playback
session may be active per device; same-direction concurrent sessions are
rejected with `FIRMWARE_BUSY`. Malformed chunk size, wrong `direction`, wrong
`command_id`, sequence gaps, and disconnects mid-stream are structured
result/event conditions. A small first PLAYBACK payload may be handed to
firmware in the `/stackchan/<device_id>/device/audio/play` action goal as
`first_chunk_sequence=0` plus `first_chunk_pcm`; this is currently a local
diagnostic path, disabled by default. Physical hardware smokes showed that a
64 byte first-goal payload can be accepted, while 320 byte and 640 byte
payload transfers still time out or stall on the serial micro-ROS path.
Remaining playback chunks, if any, continue on this topic starting at the next
sequence. The CLI bridge backend may temporarily split diagnostic playback
transport chunks below the 20 ms / 640 byte speaker-frame size to isolate
payload-size limits. K151 currently uses 160 byte transport chunks by default,
but this is not a new high-level audio quality mode.
Before relaying buffered topic chunks, the bridge may wait briefly for the
firmware subscription to be matched because the topic is volatile and serial
micro-ROS discovery can lag action-goal acceptance. Firmware must ignore
duplicate chunks whose sequence is already accepted for the active `command_id`.

### `/stackchan/<device_id>/device/audio/playback/acks`

Purpose: carry firmware-origin playback ACK/window observations so the bridge
can advance the topic relay without waiting for an audio-bearing helper service
response.

Message: `stackchan_msgs/AudioPlaybackAck`.

Fields:

- `device_id`
- `command_id`
- `has_acknowledgement`
- `acknowledged_sequence`
- `has_missing_sequence`
- `missing_sequence`
- `free_buffer_chunks`

Rules:

- This topic is firmware-owned metadata, not a command surface. It never carries
  PCM bytes or speech text.
- `acknowledged_sequence` is the highest contiguous playback sequence accepted
  for the active `command_id` when `has_acknowledgement=true`.
- `missing_sequence` is the first playback sequence firmware wants republished
  when `has_missing_sequence=true`.
- `free_buffer_chunks` advertises remaining firmware future-chunk slots so the
  bridge can cap the topic lookahead window.
- The bridge may republish `missing_sequence` plus bounded lookahead chunks on
  `/stackchan/<device_id>/device/audio/playback/chunks` when the matching
  playback relay session is active. It may throttle duplicate ACKs for the
  same `missing_sequence` and window size so firmware retry cadence does not
  multiply topic traffic. The first chunk in each ACK-triggered topic window is
  republished twice by default to reduce best-effort topic loss while avoiding
  the heavier pull-fallback retry count; this diagnostic tuning is bounded by
  `STACKCHAN_AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT=1..3`.
- QoS is best effort, volatile, keep last 8. Firmware republishes bounded
  metadata periodically while a gap remains, so this topic should not block
  safety, motion, or audio callback budgets.

### `/stackchan/<device_id>/audio/playback/next_chunk`

Purpose: bridge-owned playback helper service used by firmware to request the
next CLI-origin playback chunk for an already accepted
`/stackchan/<device_id>/device/audio/play` session. This is not a Codex command
surface and does not live under `/cmd`; it is also not firmware-owned and does
not live under `/device`.

Request fields:

- `meta`
- `next_sequence`
- `has_acknowledgement`
- `acknowledged_sequence`
- `has_missing_sequence`
- `missing_sequence`
- `free_buffer_chunks`

Response fields:

- `result`
- `has_chunk`
- `chunk`
- `end_of_stream`
- `buffered_chunks`
- `should_publish_window`
- `publish_from_sequence`
- `publish_window_chunks`

Rules:

- `meta.device_id` and `meta.command_id` identify the active playback session.
- The bridge returns at most one `AudioChunk(direction=PLAYBACK)` with bounded
  PCM payload.
- This helper is best treated as diagnostic or fallback transport for serial
  hardware. The normal bridge-owned TTS path should prefer the paced playback
  chunk topic after `/stackchan/<device_id>/device/audio/play` goal acceptance,
  because audio-bearing service responses can add enough round-trip latency to
  make speech start late or time out.
- For topic-first sessions, a pull request for a buffered sequence is first
  treated as a bounded NACK: the bridge republishes the requested sequence plus
  a small topic lookahead window on
  `/stackchan/<device_id>/device/audio/playback/chunks` and returns an accepted
  empty response. After repeated NACKs for the same sequence, the bridge may
  serve that one fallback chunk in the service response and republish the same
  sequence on the playback topic. Use pull-only diagnostics when
  service-response PCM is the behavior under test.
- Firmware may use the optional ACK/window fields to keep this service as a
  small control plane instead of a per-chunk PCM response. When
  `has_acknowledgement=true`, `acknowledged_sequence` is the highest contiguous
  playback sequence firmware has accepted for the active `command_id`, and the
  bridge must not republish earlier sequences. When
  `has_missing_sequence=true`, `missing_sequence` identifies the first sequence
  firmware wants republished on
  `/stackchan/<device_id>/device/audio/playback/chunks`. `free_buffer_chunks`
  advertises the remaining firmware jitter-buffer capacity so the bridge can
  cap the topic window. The bridge echoes the selected topic window through
  `should_publish_window`, `publish_from_sequence`, and
  `publish_window_chunks`; these fields are control metadata and never carry
  PCM.
- Firmware may publish the same ACK/window metadata on
  `/stackchan/<device_id>/device/audio/playback/acks` before or while a
  `NextAudioChunk` request is pending. The bridge should treat that topic as
  the low-latency topic-window trigger and keep this helper as fallback and
  end-of-stream confirmation.
- The ACK/window mode is the preferred next transport direction for K151 TTS
  latency work. Blindly increasing the initial topic window is not sufficient:
  physical smokes with 64-byte chunks and a 64-chunk initial window reached
  `AUDIO_UNDERRUN` after firmware detected a sequence gap while its bounded
  future-chunk buffer was already full.
- `has_chunk=false` with an accepted `result` means no matching chunk is
  currently buffered; firmware may retry on a bounded cadence.
- `end_of_stream=true` is advisory and only applies after the bridge has closed
  the matching playback relay session.
- Firmware still validates `device_id`, `command_id`, direction, format,
  sequence, and payload size before playback. The service is a transport
  helper, not a raw speaker control.

### Loaded playback transaction

K151 hardware smokes originally showed that the topic-plus-pull playback relay
could complete very short prompts, but could not carry TTS-sized PCM reliably:
minimal TTS `あ` produced 21 x 160 byte transport chunks and failed near
sequence 3, while `こんにちは` produced 56 chunks and failed before completion.
The ACK/window transport later completed minimal local TTS with smaller 64-byte
chunks, but still has high latency and residual duplicate/orphan chunk cleanup.
The standard speech transport therefore avoids synchronous audio-bearing
service responses on the real-time speaker path.

The standard loaded playback transaction for bridge-owned local TTS is:

1. The bridge allocates a local `command_id` and synthesizes or decodes bounded
   PCM locally.
2. The bridge sends audio to firmware before playback using bounded
   `/stackchan/<device_id>/device/audio/playback/chunks` messages with loaded
   payload metadata. The older
   `/stackchan/<device_id>/device/audio/playback/load` service remains a
   diagnostic fallback only.
3. Each loaded topic chunk carries format, sample rate, channel count, decoded
   total byte count, total chunk count, monotonic `sequence`, and a bounded
   payload. Firmware responses must not carry PCM.
4. Firmware stores the payload in a bounded per-device playback buffer keyed by
   `command_id`. It rejects overflow, format mismatch, duplicate active loads,
   out-of-order writes, and stale command IDs with structured errors.
5. After firmware emits the matching transaction-level `audio_playback_load`
   completion event, the bridge starts
   `/stackchan/<device_id>/device/audio/play` with the same `command_id`, but no
   streaming chunks. Firmware then passes the stable loaded buffer directly to
   M5Unified playback.

This is the standard local speech reliability path, not a new public raw-audio
command surface. `stackchanctl say` and `stackchanctl audio play` remain the
user-facing commands. The load path must stay device-scoped, bounded, redacted
in normal logs, and covered by mock, bridge, firmware, and hardware-smoke
validation. The topic-first relay and synchronous load service remain
diagnostic paths, not the default TTS payload path.

### `/stackchan/<device_id>/device/audio/playback/load`

Purpose: experimental firmware-owned service that loads bounded PCM into a
device RAM playback buffer before `/stackchan/<device_id>/device/audio/play`
starts. It is intended for KOIZUMI-146 speech bring-up only.

Request fields:

- `meta`
- `sequence`
- `total_chunks`
- `total_bytes`
- `format`
- `sample_rate`
- `channels`
- `end_of_stream`
- `pcm`

Response fields:

- `result`
- `accepted_sequence`
- `buffered_chunks`
- `buffered_bytes`
- `complete`

Rules:

- `meta.device_id` and `meta.command_id` identify the load transaction and the
  subsequent playback action.
- `sequence` must be monotonic and contiguous from 0. Firmware rejects gaps
  rather than buffering out-of-order load writes.
- `total_bytes` must fit the firmware-owned bounded RAM buffer. The K151
  bring-up profile currently reserves 32 KiB, enough for short local TTS
  prompts but not a general audio-file transfer.
- `format=PCM_S16LE` or `IMA_ADPCM_4BIT`, `sample_rate=16000`, and
  `channels=1` are required.
- `pcm` is bounded by the same `uint8[<=1280]` IDL limit as `AudioChunk`.
  On the current serial micro-ROS path, PCM bridge load chunks should stay much
  smaller than that limit; 640 byte synchronous PCM service requests timed out
  during K151 host-serial validation. Synchronous compressed ADPCM service-load
  requests completed at 96 bytes while 128 bytes and above timed out before the
  first firmware callback response, but the default loaded topic path completed
  three consecutive short local TTS smokes with 128 byte ADPCM chunks at 0.9 s
  pacing and a 30 s final completion wait. Use 64 or 96 bytes as conservative
  service-load fallbacks; larger topic values remain diagnostic-only until the
  serial micro-ROS MTU/resource path is revalidated.
- `end_of_stream=true` marks the final chunk. The bridge may start
  `/stackchan/<device_id>/device/audio/play` only after `complete=true`.
- If an incomplete load transaction stalls, firmware may accept a new
  `sequence=0` request after its playback inter-chunk timeout and reset the
  stale loaded buffer. This recovery path is for failed local transfers; it does
  not make concurrent loaded playback sessions valid.
- Responses carry counters and structured `Result` only; they must not echo PCM.
- Firmware plays a complete loaded buffer only when the playback action uses the
  same `command_id` and no first-goal chunk. Normal topic/pull playback remains
  available for diagnostics and short prompts.

KOIZUMI-162 compressed loaded playback decision:

| Candidate | Transport reduction | Firmware cost | License/dependency stance | Decision |
| --- | ---: | --- | --- | --- |
| PCM_S16LE | 1:1 | Already implemented | In-repo contract | Keep baseline and fallback |
| IMA ADPCM 4-bit | about 4:1 | Tiny integer decoder, decode into existing loaded PCM buffer | Prefer small in-repo implementation after test-vector review | Adopt for next implementation issue |
| G.711 A-law/u-law | about 2:1 at 16 kHz | Very small table/math decoder | Acceptable fallback if ADPCM quality is poor | Defer |
| G.726 ADPCM | 4:1 at 32 kbit/s | More stateful telephony codec | Needs deeper implementation/license review | Defer |
| Opus/Speex | Higher speech compression | Larger codec runtime and heap/stack risk | Permissive upstream licenses exist, but firmware fit is unproven | Defer |

The first compressed-audio implementation extends the numeric audio format
contract rather than adding a new service. `AudioChunk.format` includes
`IMA_ADPCM_4BIT=2`; `LoadAudioChunk.format=IMA_ADPCM_4BIT` means the bounded
byte field carries encoded ADPCM payload while `total_bytes` remains the
decoded PCM byte count that must fit firmware RAM. The field is still named
`pcm` in the current IDL for compatibility; docs, tests, and implementation
must treat it as format-dependent audio payload for non-PCM formats and must
keep payload bytes redacted from logs, events, CLI JSON, and MCP responses.
The ADPCM stream uses a tiny project-local framing: `sequence=0` starts with a
4 byte header (`int16_le predictor`, `uint8 step_index`, `uint8 reserved=0`)
followed by IMA nibbles packed low nibble first. Later chunks continue the same
decoder state. Firmware decodes into the loaded PCM buffer and may ignore one
final padding nibble only on the `end_of_stream=true` chunk. Bridge-owned TTS
uses this compressed loaded path by default when loaded playback is enabled,
and falls back to `PCM_S16LE` loaded writes if firmware returns
`UNSUPPORTED_FEATURE` for the compressed format.
For the topic-loaded path, the bridge defaults to paced topic publishes and then
waits for the final transaction-level firmware `audio_playback_load`
completion event before starting playback. It does not wait for per-chunk
progress by default. A diagnostic progress timeout can be enabled to make the
bridge wait at bounded loaded chunk windows and republish the same chunk within
a bounded retry count if progress stalls; firmware treats duplicate loaded
topic chunks for the same command id as idempotent and must not decode
duplicate payload bytes twice.
Firmware progress events may expose redacted transport counters such as
`expected_seq`, `received_seq`, `buf_chunks`, `chunks`, `complete`, `result`,
and a short `detail`, but must not expose PCM, ADPCM payload bytes, speech text,
provider request bodies, or raw provider identifiers.
For normal topic-loaded playback, successful intermediate chunks should not
publish progress events; publish final completion and rejection diagnostics only.
The firmware subscription depth is kept at 16 for this loaded-topic path so a
short ADPCM transaction has more subscriber-side room. The micro-ROS input
reliable stream history remains 8 because larger stream histories overflow
CoreS3 DRAM in the full bring-up profile.

### `/stackchan/<device_id>/device/audio/chunks`

Purpose: carry bounded capture audio chunks from firmware to bridge for capture
flows coordinated by actions.

Fields:

- `device_id`
- `command_id`
- `direction`
- `sequence`
- `total_chunks`
- `total_bytes`
- `format`
- `sample_rate`
- `channels`
- `end_of_stream`
- `pcm`

Baseline audio format is PCM 16 kHz mono 16-bit.

IDL constraints:

- `direction` is `PLAYBACK=1` or `CAPTURE=2`.
- `format` is `PCM_S16LE=1` for baseline capture/playback chunks.
- `IMA_ADPCM_4BIT=2` is reserved for compressed loaded playback payloads and is
  not a baseline capture format.
- `total_chunks` and `total_bytes` are zero for ordinary streaming chunks.
  Loaded playback sets them on every chunk; `total_bytes` is the decoded PCM
  byte count.
- `end_of_stream` is false for ordinary streaming chunks and true on the final
  loaded playback chunk.
- `pcm` is `uint8[<=1280]`.
- 20 ms chunks are 640 bytes.
- 40 ms chunks are 1280 bytes and are the maximum baseline chunk size.

This firmware-owned output topic publishes `direction=CAPTURE` chunks only.
Backpressure is not acknowledged per chunk; if a receiver overruns, it drops the
current chunk, publishes a structured event/error, and keeps the flow
recoverable. Malformed chunk size, wrong `direction`, wrong `command_id`,
sequence gaps, and disconnects mid-stream are structured result/event
conditions. QoS is best effort, volatile, keep last 8. The chunk stream is
bounded and has no per-chunk acknowledgement.

## Baseline services

### `/stackchan/<device_id>/cmd/face/set`

Purpose: request a named face expression and receive acceptance/rejection.

Request fields:

- `meta`
- `name`
- `duration_ms`

Response fields:

- `result`

Rules:

- `stackchan_bridge` exposes this facade service for `stackchanctl`; after
  facade metadata, availability, priority, and policy checks pass, it forwards
  the command to `/stackchan/<device_id>/device/face/set`.
- `duration_ms=0` means persistent until replaced by another command,
  safety/fault handling, or device reset.
- Face commands are idempotent by expression and duration; repeating the same
  request updates current state and does not enqueue another animation.
- Unknown expressions return `UNKNOWN_COMMAND`.
- Face work must be non-blocking and must not delay safety, fault, or motion
  neutral handling.

### `/stackchan/<device_id>/cmd/led/set`

Purpose: request a named LED pattern and receive acceptance/rejection.

Request fields:

- `meta`
- `pattern`
- `color`
- `duration_ms`

Response fields:

- `result`

Rules:

- `duration_ms=0` means persistent until replaced by another command,
  safety/fault handling, or device reset.
- LED commands are idempotent by pattern, color, and duration; repeating the
  same request updates current state and does not enqueue another animation.
- Unknown patterns return `UNKNOWN_COMMAND`.
- LED firmware policy owns brightness/current limits. LED work must be
  non-blocking and must not delay safety, fault, or motion neutral handling.
- On connected hardware, the bridge forwards validated facade requests to
  `/stackchan/<device_id>/device/led/set` and reports the firmware result.
  Bridge-only LED simulation must not be reported as physical LED success.

### `/stackchan/<device_id>/cmd/get_status`

Purpose: return the latest status snapshot for `stackchanctl observe`.

Request fields:

- `meta`

Response fields mirror `/stackchan/<device_id>/status`.

IDL constraints:

- `meta` is `stackchan_msgs/CommandMeta`.

Device-side service mirrors:

- `/stackchan/<device_id>/device/face/set`
- `/stackchan/<device_id>/device/led/set`

The bridge facade may reject requests before forwarding them if metadata, device
availability, priority, or policy checks fail. The device-side face service is
implemented by the bring-up firmware and returns the same `Result` contract as
the public facade service.

### `/stackchan/<device_id>/cmd/events/list`

Purpose: return recent buffered public events for one device.

Service type: `stackchan_msgs/srv/ListEvents`.

Request fields:

- `meta`
- `limit`
- `since_event_id`

Response fields:

- `result`
- `events`
- `cursor`

IDL constraints:

- `limit` is `uint8`, with service constant `MAX_EVENTS=32`.
- `meta` is `stackchan_msgs/CommandMeta`.
- `since_event_id` and `cursor` are `string<=36`.
- `events` is `StackChanEvent[<=32]`.

### `/stackchan/<device_id>/cmd/events/next`

Purpose: return the next unread public event for a consumer cursor.

Service type: `stackchan_msgs/srv/NextEvent`.

Request fields:

- `meta`
- `consumer_id`
- `after_event_id`
- `timeout_ms`

Response fields:

- `result`
- `events`
- `cursor`

No unread event is a successful empty event list, not a protocol error.

IDL constraints:

- `consumer_id` is `string<=64`.
- `meta` is `stackchan_msgs/CommandMeta`.
- `after_event_id` and `cursor` are `string<=36`.
- `events` is `StackChanEvent[<=1]`.

### `/stackchan/<device_id>/cmd/events/clear_cursor`

Purpose: clear the caller's unread cursor without deleting the bridge event ring buffer.

Service type: `stackchan_msgs/srv/ClearEventCursor`.

Request fields:

- `meta`
- `consumer_id`

Response fields:

- `result`
- `cursor`

IDL constraints:

- `consumer_id` is `string<=64`.
- `meta` is `stackchan_msgs/CommandMeta`.
- `cursor` is `string<=36`.

### `/stackchan/<device_id>/cmd/speech/transcript/get`

Purpose: retrieve a transcript by `utterance_id` after a `transcript_ready` event.

Service type: `stackchan_msgs/srv/GetTranscript`.

Request fields:

- `meta`
- `utterance_id`

Response fields:

- `result`
- `utterance_id`
- `transcript`
- `confidence`
- `expires_at`

IDL constraints:

- `meta` is `stackchan_msgs/CommandMeta`.
- `utterance_id` is `string<=64`.
- `transcript` is `string<=2048`, with service constant `MAX_TRANSCRIPT_CHARS=2048`.

Bridge stores transcripts in memory with a default 10 minute TTL. Persistent
transcript storage is out of scope unless a later design decision changes it.

### `/stackchan/<device_id>/cmd/power/status`

Purpose: return the latest bridge-observed power telemetry for `stackchanctl power status`.

Service type: `stackchan_msgs/srv/GetPowerStatus`.

Request fields:

- `meta`

Response fields:

- `result`
- `status`
- `stale`

Rules:

- Missing telemetry returns `UNSUPPORTED_FEATURE`.
- Stale telemetry returns `STALE_TELEMETRY` with `recoverable=true`.
- CLI JSON converts unsupported NaN numeric values to JSON `null`.

### `/stackchan/<device_id>/cmd/motion/status`

Purpose: return the latest bridge-observed current head pose for `stackchanctl motion status`.

Service type: `stackchan_msgs/srv/GetHeadPose`.

Request fields:

- `meta`

Response fields:

- `result`
- `pose`
- `stale`

Rules:

- Unsupported firmware or missing pose capability returns `UNSUPPORTED_FEATURE`.
- Previously observed pose older than the bridge stale threshold returns
  `STALE_TELEMETRY` with `recoverable=true` and is not a successful result.
  The default threshold is 15 seconds so a successful `motion pose` or
  `motion home` response remains fresh for the immediate follow-up
  `motion status` check even when serial/micro-ROS scheduling is slow.
- A successful firmware response to `motion pose` or `motion home` refreshes
  the bridge-owned latest pose snapshot and republishes
  `/stackchan/<device_id>/motion/pose`; firmware-origin
  `/stackchan/<device_id>/device/motion/pose` telemetry may also refresh the
  same snapshot.
- Servo read failure returns `SERVO_READ_FAILED` with `recoverable=true`.
- Invalid calibration or corrupted home basis returns `CALIBRATION_INVALID` with `recoverable=true`.

## Baseline actions

Baseline action feedback fields:

- `progress`
- `message`

`progress` is a `float32` from 0.0 to 1.0 when the action can estimate progress. `message` is a bounded human-readable status string for local diagnostics and should not carry speech text, image payloads, NFC tag IDs, or secrets.

### `/stackchan/<device_id>/cmd/say`

Purpose: request speech output from text.

This is a bridge facade action. The bridge owns TTS, voice selection, speech policy, and coordination with face/motion hints. Firmware must not receive `text` or `voice` fields. After TTS, the bridge sends audio through `/stackchan/<device_id>/cmd/audio/play` or the corresponding device audio path.

The bridge implementation uses a local TTS provider boundary. The first
supported provider is a local VOICEVOX Engine HTTP service. That service is an
operator-started local dependency, not a cloud account, mobile app, firmware
module, or Codex-facing API. The bridge selects a documented voice profile and
maps that profile to provider-local details such as a VOICEVOX `speaker_id`.
CLI, MCP, public events, and normal logs must expose only the voice profile
name, not raw provider IDs, speech text, synthesized PCM, or provider request
bodies.

When TTS is enabled, `/stackchan/<device_id>/cmd/say` completes only after the
bridge has synthesized bounded local audio and the firmware-owned audio
playback action returns a terminal result. Provider-disabled, unknown-profile,
synthesis-failed, unsupported-audio, playback-failed, and timeout cases return
structured `Result` failures. Firmware still receives only audio playback
goals and chunks; it must not receive `text`, `voice`, provider endpoint
configuration, or provider credentials.

If no TTS provider is configured, the action returns `UNSUPPORTED_FEATURE`.
The earlier accept-only scaffold behavior remains a historical bring-up note,
not the completion contract for local TTS.

Goal fields:

- `meta`
- `text`
- `voice`
- `face_hint`
- `motion_hint`

Result fields:

- `result`

Feedback fields:

- `progress`
- `message`

Bridge-owned TTS events:

- `tts_started`
- `tts_finished`
- `tts_failed`

These events may include bounded metadata such as `device_id`, `command_id`,
`voice_profile`, provider kind, and audio format. They must not include speech
text, provider request payloads, raw VOICEVOX speaker names/IDs as the public
voice selector, PCM bytes, transcript text, or secrets.

### `/stackchan/<device_id>/cmd/motion/run`

Purpose: request a named motion primitive with progress and cancellation.

The public CLI-facing resource remains an action. During bring-up, the bridge
may forward the immediate device-side accept/reject portion to
`/stackchan/<device_id>/device/motion/run` as a `stackchan_msgs/srv/SetMotion`
service so firmware can validate calibration, safety, and command metadata
before the full device-side action implementation exists.

Goal fields:

- `meta`
- `name`
- `intensity`
- `duration_ms`

Result fields:

- `result`

Feedback fields:

- `progress`
- `message`

### `/stackchan/<device_id>/cmd/motion/pose`

Purpose: request an explicit home-frame absolute head pose with progress and cancellation.

This is separate from named motion. `motion/run` remains intent-like, while `motion/pose` accepts only constrained absolute `pan_deg` and `tilt_deg` values in degrees.

Goal fields:

- `meta`
- `home`
- `pan_deg`
- `tilt_deg`
- `speed`
- `duration_ms`

Result fields:

- `result`
- `pose`

Feedback fields:

- `progress`
- `message`
- `pose`

Rules:

- `pan_deg` range is `-128.0..128.0` inclusive.
- `tilt_deg` range is `0.0..90.0` inclusive.
- `speed` range is `0..1000`; `0` means firmware default speed.
- `duration_ms` is `0` or `100..2000`; `0` means firmware default duration/planning bound.
- `home=false` means `pan_deg` and `tilt_deg` are explicit external absolute pose targets.
- `home=true` means firmware-owned home/neutral behavior; `pan_deg` and `tilt_deg` are ignored by the device-side planner and should be published as the resulting home pose when accepted.
- External explicit pose values outside limits are rejected with `SERVO_LIMIT_EXCEEDED` or `MOTION_INTERRUPTED`; they are not clamped.
- Non-finite explicit pose values are rejected before they can be published as state.
- Firmware owns the final safety validation even if the CLI or bridge rejected obvious invalid input earlier.
- When a real device is connected, bridge-only pose/home simulation must not be
  reported as physical actuation success. The bridge forwards valid pose/home
  action goals to `/stackchan/<device_id>/device/motion/pose/set` and reports
  the firmware `Result`.
- `/stackchan/<device_id>/motion/pose` public telemetry is updated only after
  firmware returns a completed pose with a matching `device_id`. Rejected
  requests must not update telemetry to the rejected target.
- `motion home` is a CLI/MCP command that sends `home=true`; it uses firmware-owned home behavior and is not a raw calibration command or a `pose(0,0)` alias.
- Firmware may reject pose/home with `FIRMWARE_BUSY` when a pose action is already active or the command rate exceeds the configured minimum interval.

### `/stackchan/<device_id>/cmd/audio/play`

Purpose: play speech or prompt audio on the device speaker.

Do not put large PCM payloads in a single service request. Coordinate playback
with this action and send CLI-origin payload through
`/stackchan/<device_id>/cmd/audio/play` plus the bounded chunk path. The public
playback action goal may carry a small first PCM payload as
`first_chunk_present=true`, `first_chunk_sequence=0`, and
`first_chunk_pcm` bounded to the same 1280 byte maximum as `AudioChunk.pcm`.
The CLI baseline leaves this field empty and sends all playback chunks through
the bounded chunk path. Developers may opt into a small first-goal payload for
local diagnostics, but it must remain bounded and must not become the
high-volume payload path. The bridge forwards any first-goal payload inside the
firmware-owned playback action goal, then relays accepted remaining chunks to
`/stackchan/<device_id>/device/audio/playback/chunks` only after the
firmware-owned playback action goal is accepted.
The bridge accepts and forwards the public action to
`/stackchan/<device_id>/device/audio/play` only after firmware status reports
`audio_playback` as available. Missing device action servers return structured
transport or timeout results, not synthetic success.

The bridge accepts playback goals only when firmware status reports
`audio_playback` as available. Otherwise it rejects playback goals with
`UNSUPPORTED_FEATURE` until it can return success only after
firmware-confirmed device transport acceptance.
Implementations must keep actual PCM chunks on the bounded audio chunk path and
must not inline bytes in action results, MCP output, events, or normal logs.
The CLI/bridge playback path may validate the action/capability before opening
the local audio file, so unsupported hardware smokes can remain metadata-only.
Once `audio_playback` is available, CLI-origin playback chunks use the pending
command's `command_id` and monotonic `sequence` values on
`/stackchan/<device_id>/cmd/audio/chunks`. When the diagnostic first-goal
payload path is enabled, topic chunks start at the next sequence instead. The
CLI marks the final topic chunk with `end_of_stream=true` and includes
`total_chunks` plus decoded `total_bytes` so the bridge can distinguish a
complete payload from an open streaming relay. The bridge may buffer a
complete payload and load it into the firmware-owned playback buffer before
starting `/stackchan/<device_id>/device/audio/play`. Payloads that exceed the
preload limit, incomplete payloads, or diagnostic first-goal-only transport
fall back to the streaming relay. On that fallback, the bridge must forward
buffered chunks to
`/stackchan/<device_id>/device/audio/playback/chunks` only while the matching
firmware-owned playback session is active.
If the loaded playback transaction reaches the firmware
`loaded_playback_drained` event before the action result response returns, the
bridge may complete the public action from that same-command drain observation
to avoid reporting a local timeout after firmware playback already completed.
The CLI preload decoded-byte threshold defaults to the firmware loaded buffer
limit and can be lowered with
`STACKCHAN_AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES` during streaming
relay experiments.
Firmware may alternatively pull the next buffered chunk through the
bridge-owned `/stackchan/<device_id>/audio/playback/next_chunk` helper after
action acceptance. This helper keeps PCM out of action goals while avoiding
topic delivery as the only playback ingress.
The pull helper chunk size is transport plumbing, not the speaker frame size.
On K151, firmware may pull diagnostic chunks of different sizes, but it must
aggregate accepted PCM into M5Unified `playRaw()` runtime buffers sized around
the 20 ms baseline before handing them to the speaker task.
When chunks arrive through the serial micro-ROS topic path, firmware may hold a
small fixed in-RAM jitter buffer for future sequences and process them only
after the missing expected sequence arrives. Duplicate future chunks are ignored
inside that bounded window. The standard K151 build keeps 8 future-chunk slots
for this diagnostic relay because loaded playback is the preferred audible TTS
path. A firmware build may enable an extended 24-slot topic relay buffer for
transport diagnostics, but that spends roughly 10 KiB more static RAM and
should not be the default speech path. Larger future chunks may be rejected to
keep device RAM bounded. A missing expected sequence that stops progressing past
the firmware gap timeout remains `AUDIO_UNDERRUN`; the jitter buffer is only an
ordering cushion, not a reliable retransmission contract.
The bridge may mark the pull stream end-of-stream after the CLI-origin chunk
input has been idle for a bounded interval and the buffered queue is empty; it
must not wait for the device action result callback before exposing
`end_of_stream=true`, because firmware may need that observation to finish the
action.
For prebuffered topic TTS, the bridge must defer pull-helper
`end_of_stream=true` until the paced topic publish loop has finished. An idle
pull request during topic publishing should return no chunk and no
end-of-stream so firmware does not complete after only the action-goal fragment.
The bridge should keep those prebuffered chunks available to
`/stackchan/<device_id>/audio/playback/next_chunk` as a fallback for topic
loss; duplicate sequences from topic and pull delivery remain firmware-ignored.
On the standard topic-first path, that fallback may republish the requested
sequence on the playback topic instead of carrying PCM in the service response,
so the serial link is not forced to deliver audio in synchronous service
payloads. If repeated requests show the same sequence still missing, the bridge
may return that one chunk in the service response after bounded topic NACKs.
For longer audio, the bridge must not publish the full buffered TTS payload at
once. It publishes only a bounded initial playback-topic window, then advances
the topic window from firmware pull requests so future chunks do not exceed the
firmware jitter buffer. Pull-triggered lookahead publishing must not delay the
`NextAudioChunk` response past the firmware pull timeout.
The default topic relay does not duplicate every chunk and should pace
prebuffered chunks conservatively on serial links because pull helper traffic,
fragmentation, and topic bursts can starve the Agent. Firmware should likewise
treat pull as a fallback: while topic chunks are making recent progress and no
sequence gap is buffered, it should not continuously request the next chunk
over the service. If future chunks are already buffered and the next expected
sequence is missing, firmware may request that missing sequence immediately.
The pull helper is used when expected-sequence progress goes idle or when the
device needs a small end-of-stream confirmation.
For local TTS audible-quality checks, the bridge should prefer loaded playback
when the synthesized PCM fits the bounded device buffer. The default loaded
path sends format-dependent audio payloads over
`/stackchan/<device_id>/device/audio/playback/chunks` before the playback
action and uses the action result as the final confirmation, not per-chunk
application ACK. The bridge may pace topic chunks slightly to avoid overrunning
bounded publisher/subscriber queues; this pacing is not an acknowledgement
loop. Before starting the playback action, the bridge waits for the
transaction-level firmware `audio_playback_load` completion event for the
matching `command_id`; this confirms the preloaded buffer is ready without
requiring a response for each payload chunk. The older synchronous load service
remains available as a diagnostic fallback. Serial load-service chunks should
stay small enough for the current micro-ROS/host-serial bridge; larger
synchronous PCM service payloads may time out even when the total loaded buffer
would fit.
The bridge must not use the short synchronous device-command timeout for media
action result delivery. Playback and capture need a media-action timeout, 35
seconds by default in the bridge, large enough for goal acceptance, firmware
buffering, chunk transfer, and terminal result delivery.
If a firmware-owned media action times out at the bridge, the bridge treats the
device media path as settling before it accepts another playback, capture, or
camera media action for that device. During this bounded settle window, a new
media command returns structured `FIRMWARE_BUSY` with the previous
`command_id`; this prevents a late goal/result response from a timed-out smoke
from contaminating the next audible or camera check. Late media goal/result
future completion diagnostics include `device_id`, `command_id`, action label,
phase, and structured result metadata only. They must not log PCM, image bytes,
speech text, or provider payloads.

Baseline format: PCM 16 kHz mono 16-bit.

Privacy and result rules:

- CLI JSON, MCP tool results, public events, normal logs, and diagnostics must
  not include PCM bytes, speech text, or transcript text.
- Results may expose metadata such as `command_id`, input/output path,
  duration, byte count, sample rate, channels, and structured errors.
- Action acceptance means the bridge and firmware accepted the playback session,
  not that speaker output has completed. Playback start, queued depth,
  completion, underrun, and terminal failure should be observable through action
  feedback, status, or bounded events.
- Firmware must not mark playback completed solely because the speaker has
  drained after one accepted chunk. Completion requires end-of-stream plus
  speaker drain; missing next chunks are `AUDIO_UNDERRUN` after a bounded
  inter-chunk timeout.
- Device-side playback chunks are valid only for an active firmware-owned
  playback session with a matching `command_id`. Firmware must reject orphaned
  chunks rather than treating the chunk topic as a raw speaker-control command.
- Playback underrun returns `AUDIO_UNDERRUN` and stops playback.
- Mic overrun drops the current chunk and publishes `MIC_OVERRUN`; capture may
  continue unless the failure is terminal.
- Terminal capture failure returns `AUDIO_CAPTURE_FAILED`.
- Audio work must use bounded queues/callback budgets and must not block safety
  or fault handling.

Goal fields:

- `meta`
- `format`
- `sample_rate`
- `channels`
- `face_hint`
- `motion_hint`

Result fields:

- `result`

Feedback fields:

- `progress`
- `message`

### `/stackchan/<device_id>/cmd/camera/capture`

Purpose: request a constrained camera snapshot.

Goal fields:

- `meta`
- `format`
- `width`
- `height`
- `quality`

Result fields:

- `result`
- `image` compatibility field; default implementations leave it empty and
  deliver JPEG bytes on `/stackchan/<device_id>/device/camera/chunks`

Feedback fields:

- `progress`
- `message`

Baseline camera behavior:

- snapshot only
- no continuous stream
- no follow mode or video-like frame sequences
- QVGA JPEG target
- `quality` range is 1-95
- maximum JPEG payload is 96 KiB, delivered as `CameraFrameChunk` messages
  on `/stackchan/<device_id>/device/camera/chunks`
- Action acceptance means the snapshot request was accepted, not that a valid
  JPEG is already available. Frame acquisition, JPEG encode, size validation,
  chunk delivery, reassembly, and output-file write are separate failure
  points.
- CLI JSON, MCP tool results, public events, and normal logs report metadata
  only; they must not inline base64, JPEG bytes, or image payloads
- oversize frames are discarded and mapped to `CAMERA_CAPTURE_FAILED` with
  `recoverable=true` unless a later contract adds a narrower error code
- timeout returns a structured `CAMERA_CAPTURE_FAILED` result when the device
  camera action accepted the goal but did not deliver a result within the
  bridge media-action timeout
- the bridge rejects capture goals with `UNSUPPORTED_FEATURE` until firmware
  status reports `camera_snapshot` as available
- after capability confirmation, the bridge forwards the goal to
  `/stackchan/<device_id>/device/camera/capture`; missing or rejecting device
  action servers return structured transport/rejection results, while accepted
  device goals that time out before result delivery return bounded
  `CAMERA_CAPTURE_FAILED` instead of an unclassified CLI timeout
- the bridge uses the media-action timeout for camera result delivery because
  firmware frame acquisition and JPEG encoding may exceed the short synchronous
  service timeout
- chunk transport must enforce the 96 KiB maximum before exposing metadata to
  callers

### `/stackchan/<device_id>/device/camera/chunks`

Purpose: firmware-owned QVGA JPEG snapshot payload chunks.

Message type: `stackchan_msgs/CameraFrameChunk`

Rules:

- published only for an accepted camera capture action
- `device_id` and `command_id` match the capture goal metadata
- `format=JPEG`, `width=320`, `height=240`, and `quality` echoes the accepted
  goal
- `sequence` starts at `0`, `total_chunks` is stable across the frame, and
  the final chunk has `end_of_stream=true`
- `total_bytes` is the final JPEG byte count and must be `1..98304`
- each chunk is at most 256 bytes; bridge subscribers should use a deeper local
  receive queue than the firmware publisher to absorb short callback stalls
- payload bytes must not appear in normal logs, public events, CLI JSON, or MCP
  results

### `/stackchan/<device_id>/cmd/perform`

Purpose: run a longer behavior such as a combined speech, face, LED, and motion sequence.

This is reserved until the simpler service and action interfaces are useful. It
is out of the MVP baseline and should not block the baseline command set.

If implemented later, this must be bridge-side orchestration over existing
`say`, `face`, `led`, `motion`, `audio`, and explicitly approved camera
contracts. It is not a generic command bus, not a firmware sequence language,
and must not include maintenance or calibration operations. Result aggregation
must keep bounded per-step summaries with parent and child `command_id` values,
per-step result state/error summary, cancellation/preemption state, partial
failure semantics, and recoverability. It must not include raw speech text, PCM
payloads, image bytes, NFC/IR raw identifiers, or maintenance data.

### Maintenance and calibration

Calibration write, reset, import/export, raw servo controls, and maintenance
unlock operations are not part of the normal public bridge facade under
`/stackchan/<device_id>/cmd/...`. They must not be reachable through routine
`face`, `motion`, `led`, `observe`, `perform`, Codex skill, or MCP command
flows.

If a maintenance calibration interface is added, it must be documented as a
separate local maintenance path before implementation. The write/reset must
terminate in firmware-owned logic that validates the complete calibration
record, writes only firmware-owned NVS data, and preserves hard safety limits in
firmware constants. It must not accept raw servo ticks, PWM, torque, relative
movement, continuous rotation, arbitrary NVS blobs, or CLI config-derived safety
limits.

For early K151 bring-up, a firmware-local serial maintenance seed or build-time
maintenance mode is acceptable only when it requires an explicit operator
confirmation, is documented in `docs/hardware-validation.md`, and is disabled
or unreachable from normal
Codex/MCP flows. Hardware validation must prove both invalid calibration
rejection with `CALIBRATION_INVALID` and valid calibration progression to the
servo-read/motion-safety stage before real-servo motion is marked complete.

### `/stackchan/<device_id>/cmd/audio/capture`

Purpose: capture microphone audio and stream chunks to the PC side.

Baseline format: PCM 16 kHz mono 16-bit.

Goal fields:

- `meta`
- `format`
- `sample_rate`
- `channels`
- `duration_ms`

Result fields:

- `result`

Feedback fields:

- `progress`
- `message`

Microphone capture uses this action for duration, progress, cancellation, and overrun behavior. Captured chunks are published on `/stackchan/<device_id>/device/audio/chunks`.
The bridge accepts and forwards the public action to
`/stackchan/<device_id>/device/audio/capture` only after firmware status reports
`audio_capture` as available. Missing device action servers return structured
transport or timeout results, not synthetic success.

The bridge accepts microphone capture goals only when firmware status reports
`audio_capture` as available. Otherwise it rejects capture goals with
`UNSUPPORTED_FEATURE` until it can return success only after
firmware-confirmed device transport acceptance. Captured chunks remain on the
bounded audio chunk path and must not be surfaced as raw bytes in action
summaries, MCP output, events, or normal logs.

Baseline chunk policy:

- 20 ms chunks by default.
- 40 ms chunks are allowed when transport overhead matters.
- Mic overrun drops the current chunk, publishes an overrun event/error, and keeps capture recoverable.
- Playback underrun stops playback, publishes an error, and returns to a neutral speaking state.
- Same-direction concurrent playback/capture sessions are rejected with
  `FIRMWARE_BUSY`.
- Playback and capture may run concurrently only if the documented echo/VAD
  policy preserves safety and transcript privacy.

Target device-side action mirrors:

- `/stackchan/<device_id>/device/motion/run`
- `/stackchan/<device_id>/device/audio/play`
- `/stackchan/<device_id>/device/audio/capture`
- `/stackchan/<device_id>/device/camera/capture`

The bridge facade is allowed to implement a richer policy than the device mirror, but it must return the shared `Result` shape.

Bring-up device-side service mirrors:

- `/stackchan/<device_id>/device/motion/run`
- `/stackchan/<device_id>/device/motion/pose/set`

The motion bring-up service uses `stackchan_msgs/srv/SetMotion` and is limited
to immediate firmware accept/reject. It is expected to return
`CALIBRATION_INVALID`, `SERVO_READ_FAILED`, `SERVO_LIMIT_EXCEEDED`,
`MOTION_INTERRUPTED`, `UNKNOWN_COMMAND`, or `INVALID_PRIORITY` through the
shared `Result` shape until the full action mirror owns progress and
cancellation.

The head pose bring-up service uses `stackchan_msgs/srv/SetHeadPose`. It is a
firmware-owned validation and actuation boundary for the public
`/stackchan/<device_id>/cmd/motion/pose` action. The service name uses
`/pose/set` so it does not collide with the existing
`/stackchan/<device_id>/device/motion/pose` telemetry topic. On success it
returns a completed `Result` and the confirmed home-frame `HeadPose`; on
invalid calibration, out-of-range servo target, servo read failure, busy/fault,
or device mismatch it returns a structured rejection and leaves pose telemetry
unchanged.

## QoS and heartbeat baseline

Baseline QoS:

- Status heartbeat is published at 1 Hz.
- A device is considered disconnected after 3 missed heartbeats unless config overrides it.
- `/stackchan/<device_id>/status`: reliable, transient local, keep last 1.
- `/stackchan/<device_id>/device/status`: reliable, volatile, keep last 2.
- `/stackchan/<device_id>/events`: reliable, volatile, keep last 32.
- `/stackchan/<device_id>/device/events`: reliable, volatile, keep last 32.
- `/stackchan/<device_id>/device/imu/raw`: best effort, volatile, keep last 10.
- `/stackchan/<device_id>/touch/state`: reliable, transient local, keep last 1.
- `/stackchan/<device_id>/device/touch/state`: reliable, volatile, keep last 4.
- `/stackchan/<device_id>/proximity/raw`: best effort, volatile, keep last 10.
- `/stackchan/<device_id>/device/proximity/raw`: best effort, volatile, keep last 10.
- `/stackchan/<device_id>/light/raw`: best effort, volatile, keep last 5.
- `/stackchan/<device_id>/device/light/raw`: best effort, volatile, keep last 5.
- `/stackchan/<device_id>/power/status`: reliable, transient local, keep last 1.
- `/stackchan/<device_id>/device/power/status`: reliable, volatile, keep last 2.
- `/stackchan/<device_id>/motion/pose`: reliable, transient local, keep last 1.
- `/stackchan/<device_id>/device/motion/pose`: reliable, volatile, keep last 2.
- `/stackchan/<device_id>/cmd/audio/chunks`: reliable, volatile, keep last 64.
- `/stackchan/<device_id>/device/audio/playback/chunks`: reliable, volatile, keep last 16.
- `/stackchan/<device_id>/device/audio/playback/acks`: best effort, volatile, keep last 8.
- `/stackchan/<device_id>/device/audio/chunks`: best effort, volatile, keep last 8.
- `/stackchan/<device_id>/device/camera/chunks`: best effort, volatile.
  Firmware keeps last 16; bridge receivers should keep at least 64.
- Service and action request/response paths use reliable QoS.
- Safety/fault signals use reliable QoS and must not be blocked by camera or audio work.

## Package boundaries

- `ros/stackchan_msgs` owns message, service, and action definitions.
- `ros/stackchan_bridge` owns PC-side routing and CLI-facing integration.
- `firmware/m5stackchan-microros` owns device-side service/action handlers, publishers, and safety checks.
- `apps/stackchanctl` owns the user-facing command surface and backend selection.
- `apps/stackchanctl` also owns the MCP stdio adapter; it does not define new ROS resources.
