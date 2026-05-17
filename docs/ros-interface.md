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

Examples:

```text
/stackchan/default/status
/stackchan/default/cmd/face/set
/stackchan/desk/status
/stackchan/desk/cmd/motion/run
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
- `MOTION_INTERRUPTED`
- `AUDIO_UNDERRUN`
- `MIC_OVERRUN`
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
- `SAFETY`: bridge/firmware internal only; CLI-originated `SAFETY` requests are rejected with `INVALID_PRIORITY`.
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

Recommended IDL details:

- strings are bounded to 32 characters unless the field is an error/message field.
- `last_error` uses the shared `Result` shape.
- `connected` reflects current registry/transport availability, not whether the
  previous command succeeded. A healthy device may still report a historical
  command rejection in `last_error` until a later command result replaces it.

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
  image payloads, PCM audio, or large data.

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
- `transport_unstable`

Baseline bridge/PC event names:

- `speech_detected`
- `transcript_ready`
- `transcript_failed`
- `tts_started`
- `tts_finished`
- `tts_failed`
- `device_connected`
- `device_disconnected`
- `device_conflict_detected`

`transcript_ready` carries an `utterance_id` in `payload_json`; full transcript
text is retrieved through the speech transcript query service, not embedded in
the event.

### `/stackchan/<device_id>/device/events`

Purpose: carry hardware-origin high-level events from firmware to the bridge.

Fields mirror `StackChanEvent`.

Rules:

- Firmware publishes only device facts such as button, IMU posture/activity,
  NFC presence, battery, transport, camera error, and audio buffer events.
- Firmware must not assign application meaning to tags, gestures, or speech.
- Bridge owns public normalization, redaction, and consumer buffering.
- Firmware may leave `event_id` empty; bridge fills it before republishing.

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

Playback and capture share the same chunk topic because `direction` and `command_id` disambiguate flows. Backpressure is not acknowledged per chunk; if a receiver overruns, it drops the current chunk, publishes a structured event/error, and keeps the flow recoverable.

## Baseline services

### `/stackchan/<device_id>/cmd/face/set`

Purpose: request a named face expression and receive acceptance/rejection.

Request fields:

- `meta`
- `name`
- `duration_ms`

Response fields:

- `result`

### `/stackchan/<device_id>/cmd/led/set`

Purpose: request a named LED pattern and receive acceptance/rejection.

Request fields:

- `meta`
- `pattern`
- `color`
- `duration_ms`

Response fields:

- `result`

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

The bridge facade may reject requests before forwarding them if metadata, device availability, priority, or policy checks fail.

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

### `/stackchan/<device_id>/cmd/audio/play`

Purpose: play speech or prompt audio on the device speaker.

Do not put large PCM payloads in a single service request. Coordinate playback with this action and send payload through `/stackchan/<device_id>/device/audio/chunks`.

The current bridge scaffold returns `UNSUPPORTED_FEATURE` for playback until
audio chunk transport is implemented.

Baseline format: PCM 16 kHz mono 16-bit.

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
- QVGA JPEG target
- `quality` range is 1-95
- `image` uses `CompressedImagePayload`
- maximum image payload is 96 KiB
- timeout returns a structured `TIMEOUT` or `CAMERA_CAPTURE_FAILED` result
- the current bridge scaffold returns `UNSUPPORTED_FEATURE` until image result
  transport is implemented

### `/stackchan/<device_id>/cmd/perform`

Purpose: run a longer behavior such as a combined speech, face, LED, and motion sequence.

This is reserved until the simpler service and action interfaces are useful. It should not block the baseline command set.

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

The current bridge scaffold returns `UNSUPPORTED_FEATURE` for microphone
capture until audio chunk transport is implemented.

Baseline chunk policy:

- 20 ms chunks by default.
- 40 ms chunks are allowed when transport overhead matters.
- Mic overrun drops the current chunk, publishes an overrun event/error, and keeps capture recoverable.
- Playback underrun stops playback, publishes an error, and returns to a neutral speaking state.

Device-side action mirrors:

- `/stackchan/<device_id>/device/motion/run`
- `/stackchan/<device_id>/device/audio/play`
- `/stackchan/<device_id>/device/audio/capture`
- `/stackchan/<device_id>/device/camera/capture`

The bridge facade is allowed to implement a richer policy than the device mirror, but it must return the shared `Result` shape.

## QoS and heartbeat baseline

Baseline QoS:

- Status heartbeat is published at 1 Hz.
- A device is considered disconnected after 3 missed heartbeats unless config overrides it.
- `/stackchan/<device_id>/status`: reliable, transient local, keep last 1.
- `/stackchan/<device_id>/events`: reliable, volatile, keep last 32.
- `/stackchan/<device_id>/device/events`: reliable, volatile, keep last 32.
- `/stackchan/<device_id>/device/imu/raw`: best effort, volatile, keep last 10.
- `/stackchan/<device_id>/device/audio/chunks`: best effort, volatile, keep last 8.
- Service and action request/response paths use reliable QoS.
- Safety/fault signals use reliable QoS and must not be blocked by camera or audio work.

## Package boundaries

- `ros/stackchan_msgs` owns message, service, and action definitions.
- `ros/stackchan_bridge` owns PC-side routing and CLI-facing integration.
- `firmware/m5stackchan-microros` owns device-side service/action handlers, publishers, and safety checks.
- `apps/stackchanctl` owns the user-facing command surface and backend selection.
- `apps/stackchanctl` also owns the MCP stdio adapter; it does not define new ROS resources.
