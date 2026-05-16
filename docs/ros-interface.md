# ROS 2 Interface Design

This document describes the contract between `stackchanctl`, PC-side ROS 2 nodes, and M5StackChan firmware.

The details will evolve as the packages are implemented, but the boundary should stay explicit: `stackchanctl` sends normalized intent, ROS 2 carries that intent, and firmware executes only safe device-side behavior.

## Interface principles

- Prefer named commands over raw hardware values.
- Support single-device and multi-device operation through the same `device_id` contract.
- Use topics for fire-and-forget state changes.
- Use services for request/response operations.
- Use actions for long-running behavior that needs progress or cancellation.
- Keep message definitions small and stable.
- Publish device state separately from command requests.
- Use USB Serial as the first micro-ROS transport.
- Keep audio, camera, NFC, and IMU as explicit interfaces instead of hiding them behind generic status blobs.
- Prefer feature-specific message, service, and action types over one generic command envelope.
- Include command correlation metadata in command-bearing interfaces.
- Return structured errors with code, message, and recoverability.

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
/stackchan/default/face/set
/stackchan/desk/status
/stackchan/desk/motion/run
```

## Common command metadata

Command-bearing interfaces should include:

- `device_id`
- `command_id`
- `source`
- `created_at`
- `priority`

This metadata lets `stackchanctl`, bridge nodes, firmware, logs, and status messages refer to the same request.

## Common error shape

Request/response interfaces should be able to represent:

- `ok`
- `error_code`
- `message`
- `recoverable`

Candidate error codes:

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

## Candidate topics

### `/stackchan/<device_id>/status`

Purpose: publish current device and bridge state.

Possible fields:

- `device_id`
- `connected`
- `state`
- `face`
- `motion`
- `last_command_id`
- `last_error`

### `/stackchan/<device_id>/imu/raw`

Purpose: publish raw IMU telemetry.

Initial rate: 10-30 Hz.

Possible fields:

- `device_id`
- `stamp`
- `accel`
- `gyro`
- `mag`
- `temperature`

### `/stackchan/<device_id>/events`

Purpose: publish high-level device events useful to Codex and PC-side orchestration.

Possible fields:

- `device_id`
- `event_name`
- `stamp`
- `command_id`
- `payload`

Initial event names:

- `picked_up`
- `shaken`
- `tilted`
- `nfc_detected`
- `nfc_removed`
- `audio_started`
- `audio_finished`
- `camera_capture_failed`

## Candidate services

### `/stackchan/<device_id>/face/set`

Purpose: request a named face expression and receive acceptance/rejection.

Possible request fields:

- `meta`
- `name`
- `duration_ms`

Possible response fields:

- `result`

### `/stackchan/<device_id>/led/set`

Purpose: request a named LED pattern and receive acceptance/rejection.

Possible request fields:

- `meta`
- `pattern`
- `color`
- `duration_ms`

Possible response fields:

- `result`

### `/stackchan/<device_id>/get_status`

Purpose: return the latest status snapshot for `stackchanctl observe`.

Possible response fields should mirror `/stackchan/<device_id>/status`.

## Candidate actions

### `/stackchan/<device_id>/say`

Purpose: request speech output.

Possible request fields:

- `meta`
- `text`
- `voice`
- `face_hint`
- `motion_hint`

Possible response fields:

- `result`

### `/stackchan/<device_id>/motion/run`

Purpose: request a named motion primitive with progress and cancellation.

Possible request fields:

- `meta`
- `name`
- `intensity`
- `duration_ms`

Possible result fields:

- `result`

### `/stackchan/<device_id>/audio/play`

Purpose: play speech or prompt audio on the device speaker.

This should avoid putting large PCM payloads in a single service request. Prefer an action plus chunked audio transport when implementation begins.

Initial format: PCM 16 kHz mono 16-bit.

Possible request fields:

- `meta`
- `format`
- `sample_rate`
- `channels`
- `face_hint`
- `motion_hint`

Possible response fields:

- `result`

### `/stackchan/<device_id>/camera/capture`

Purpose: request a constrained camera snapshot.

Possible request fields:

- `format`
- `width`
- `height`
- `quality`

Possible response fields:

- `result`
- `image`

### `/stackchan/<device_id>/perform`

Purpose: run a longer behavior such as a combined speech, face, LED, and motion sequence.

This should wait until the simpler topic and service interfaces are useful. It is likely too much for the first implementation slice.

### `/stackchan/<device_id>/audio/capture`

Purpose: capture microphone audio and stream chunks to the PC side.

Initial format: PCM 16 kHz mono 16-bit.

This may become an action rather than a service because microphone capture has duration, progress, cancellation, and overrun behavior.

## Package boundaries

- `ros/stackchan_msgs` owns message, service, and action definitions.
- `ros/stackchan_bridge` owns PC-side routing and CLI-facing integration.
- `firmware/m5stackchan-microros` owns device-side subscribers, publishers, and safety checks.
- `apps/stackchanctl` owns the user-facing command surface and backend selection.
