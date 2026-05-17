# K151 Hardware Validation Checklist

Use this checklist when a K151 StackChan device is available. Record the date,
firmware build, bridge branch/commit, device id, and operator before marking the
hardware bring-up issue complete.

## Setup

- Flash the firmware with `STACKCHAN_DEVICE_ID=default`.
- Start the micro-ROS Agent over serial at 921600 baud.
- Start `stackchan_bridge` with `device_connected=true`.
- Confirm `stackchanctl --backend bridge observe --json` reports the device as connected.

## Servo Calibration And Motion Safety

- Boot with no valid calibration record and confirm `motion pose`, `motion home`,
  and named servo motion reject with `CALIBRATION_INVALID`.
- When explicit maintenance tooling exists, load a valid firmware-owned
  calibration record. Normal CLI/MCP commands must not write calibration.
- Until that maintenance path exists, mark valid-calibration motion checks
  unavailable and only complete the invalid-calibration rejection checks.
- With a valid calibration record, confirm `stackchanctl --backend bridge motion pose --pan-deg 30 --tilt-deg 20 --json`
  accepts and moves to the expected absolute home-frame pose.
- Confirm `--pan-deg 129`, `--tilt-deg -1`, and non-finite values are rejected
  without clamping or motion.
- Confirm `motion home` uses firmware home behavior and is not implemented as a
  public `pose(0,0)` alias.
- Confirm servo read failure or unplugged servo paths return `SERVO_READ_FAILED`
  or a recoverable motion error and enter a safe fault/neutral behavior.

## Audio

- Confirm `stackchanctl --backend bridge audio play prompt.wav --json` returns a
  structured accepted or completed result without printing PCM bytes.
- Confirm microphone capture publishes bounded 16 kHz mono PCM chunks and that
  overrun/underrun events are visible through `stackchanctl events`.
- Confirm malformed format, sequence gaps, disconnect, and timeout cases produce
  structured recoverable errors.

## Camera

- Confirm `stackchanctl --backend bridge camera capture --output frame.jpg --quality 80 --json`
  returns metadata only and never prints JPEG/base64 bytes.
- Confirm the device produces QVGA JPEG snapshots and rejects or discards frames
  larger than 96 KiB with `CAMERA_CAPTURE_FAILED`.
- Confirm camera failure does not block motion, audio, safety, or event handling.

## Events And Redaction

- Trigger NFC, IR/remote, audio, camera, button, IMU, and power events.
- Confirm public events use bounded payload JSON and normal CLI/MCP output does
  not include raw NFC IDs, raw IR codes, protocol dumps, PCM, transcripts, or
  image bytes.
- Confirm device id mismatches are dropped or reported as conflicts without
  crossing device namespaces.

## Cleanup

- Save the command transcript and observed result codes in the PR or Linear
  issue.
- Reset temporary maintenance/debug firmware changes before merging production
  code.
