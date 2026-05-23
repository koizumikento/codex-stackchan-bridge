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

Camera action results use a compressed-image shaped project message:

```text
string<=16 format
uint8[<=98304] data
```

`format` is `jpeg` for the baseline camera contract. The payload limit is 96 KiB.

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

### `/stackchan/<device_id>/device/audio/chunks`

Purpose: carry bounded audio chunks for playback or capture flows coordinated by actions.

Fields:

- `device_id`
- `command_id`
- `direction`
- `sequence`
- `format`
- `sample_rate`
- `channels`
- `pcm`

Baseline audio format is PCM 16 kHz mono 16-bit.

IDL constraints:

- `direction` is `PLAYBACK=1` or `CAPTURE=2`.
- `format` is `PCM_S16LE=1`.
- `pcm` is `uint8[<=1280]`.
- 20 ms chunks are 640 bytes.
- 40 ms chunks are 1280 bytes and are the maximum baseline chunk size.

Playback and capture share the same chunk topic because `direction` and
`command_id` disambiguate flows. `sequence` is monotonic per `command_id` plus
`direction`. The baseline permits at most one playback session and one capture
session per device; same-direction concurrent sessions are rejected with
`FIRMWARE_BUSY`. Backpressure is not acknowledged per chunk; if a receiver
overruns, it drops the current chunk, publishes a structured event/error, and
keeps the flow recoverable. Malformed chunk size, wrong `direction`, wrong
`command_id`, sequence gaps, and disconnects mid-stream are structured
result/event conditions.

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
- Previously observed pose older than the stale threshold returns `STALE_TELEMETRY` with `recoverable=true` and is not a successful result.
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

The current bridge scaffold validates and accepts `say` requests but does not
claim speech playback completion until TTS/audio routing is implemented.

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

Do not put large PCM payloads in a single service request. Coordinate playback with this action and send payload through `/stackchan/<device_id>/device/audio/chunks`.
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
Once `audio_playback` is available, playback chunks use the accepted
`command_id` and monotonic `sequence` values on
`/stackchan/<device_id>/device/audio/chunks`.
The bridge must not use the short synchronous device-command timeout for media
action result delivery. Playback and capture need a media-action timeout large
enough for goal acceptance, firmware buffering, chunk transfer, and terminal
result delivery.

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
- `image`

Feedback fields:

- `progress`
- `message`

Baseline camera behavior:

- snapshot only
- no continuous stream
- no follow mode or video-like frame sequences
- QVGA JPEG target
- `quality` range is 1-95
- `image` uses `CompressedImagePayload`
- maximum image payload is 96 KiB
- Action acceptance means the snapshot request was accepted, not that a valid
  JPEG is already available. Frame acquisition, JPEG encode, size validation,
  and result delivery are separate failure points.
- CLI JSON, MCP tool results, public events, and normal logs report metadata
  only; they must not inline base64, JPEG bytes, or image payloads
- oversize frames are discarded and mapped to `CAMERA_CAPTURE_FAILED` with
  `recoverable=true` unless a later contract adds a narrower error code
- timeout returns a structured `TIMEOUT` or `CAMERA_CAPTURE_FAILED` result
- the bridge rejects capture goals with `UNSUPPORTED_FEATURE` until firmware
  status reports `camera_snapshot` as available
- after capability confirmation, the bridge forwards the goal to
  `/stackchan/<device_id>/device/camera/capture`; missing, rejecting, or timed
  out device action servers return structured transport/timeout/rejection
  results instead of synthetic success
- the bridge uses the media-action timeout for camera result delivery because
  firmware frame acquisition and JPEG encoding may exceed the short synchronous
  service timeout
- result transport must enforce the 96 KiB maximum before exposing metadata to
  callers

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
- `/stackchan/<device_id>/device/audio/chunks`: best effort, volatile, keep last 8.
- Service and action request/response paths use reliable QoS.
- Safety/fault signals use reliable QoS and must not be blocked by camera or audio work.

## Package boundaries

- `ros/stackchan_msgs` owns message, service, and action definitions.
- `ros/stackchan_bridge` owns PC-side routing and CLI-facing integration.
- `firmware/m5stackchan-microros` owns device-side service/action handlers, publishers, and safety checks.
- `apps/stackchanctl` owns the user-facing command surface and backend selection.
- `apps/stackchanctl` also owns the MCP stdio adapter; it does not define new ROS resources.
