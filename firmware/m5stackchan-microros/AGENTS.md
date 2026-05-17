# AGENTS.md

Instructions for agents editing `firmware/m5stackchan-microros`.

This directory owns the device firmware. Follow this file for firmware-specific rules, and use the repository root `AGENTS.md` for repository-wide policy.

## Ownership

Firmware owns:

- micro-ROS connection setup.
- Device-side service/action handlers and status/error publishers.
- Display, servo, LED, audio, camera, NFC, IMU, and sensor adapters.
- Firmware-side validation of named commands.
- Safety-critical defaults and hard limits.
- Degraded behavior when ROS 2 or the micro-ROS Agent disconnects.

Firmware does not own:

- Codex skill behavior.
- High-level dialog, TTS, STT, or VAD policy.
- Human-facing CLI behavior.
- PC-side routing or orchestration.
- A fork of the M5Stack factory firmware.

## Firmware Base Policy

- Do not fork `m5stack/StackChan` as this repository's firmware base.
- Treat factory firmware as reference material only.
- Prefer `m5stack/StackChan-BSP` for hardware access.
- Keep low-level hardware control in BSP/libraries where practical.
- This firmware should focus on behavior adaptation, ROS communication, status, and safety.

## Platform And Dependencies

- Use PlatformIO with the Arduino framework.
- Target ROS 2 / micro-ROS Jazzy.
- Use USB Serial transport.
- Prefer `StackChan-BSP` pinned by Git tag.
- Pin `micro_ros_platformio` to a verified commit SHA when release tags lag the needed ROS distro.
- Do not vendor large upstream firmware, app, server, or remote-control code without a documented reason.
- Verify licenses before copying upstream code and preserve notices.

## Command Model

- Accept named intent commands first.
- Raw servo angles are only for debug/calibration.
- Enforce servo, LED, audio, camera, and sensor safety limits in firmware.
- Command-bearing interfaces must preserve `device_id`, `command_id`, `source`, `created_at`, and `priority`.
- Publish structured status and errors whenever possible.
- Use `LOW`, `NORMAL`, `HIGH`, and `SAFETY` priority values.
- Reserve `SAFETY` for firmware and bridge internal use.

## Configuration And Calibration

- Hard safety limits live in firmware constants.
- Individual device calibration lives in firmware NVS.
- Normal operation tuning lives in ROS package YAML.
- CLI config must not be required for device safety.
- Calibration writes, raw hardware controls, NVS export/import, and other
  maintenance operations must use a documented maintenance path, not the normal
  Codex-facing command surface.

## Device Capabilities

Firmware capability set includes:

- face
- motion
- LED
- audio playback
- microphone capture
- camera snapshot
- NFC events
- raw IMU/sensor channels when explicitly contracted
- high-level IMU events
- other local sensors

Audio is a first-class capability. Device exchange uses PCM 16 kHz mono 16-bit unless a documented decision changes it.

Audio playback and capture use actions coordinated with bounded chunks. Chunk duration is 20 ms by default; 40 ms is allowed when transport overhead matters.

Camera owns QVGA JPEG snapshot support. Continuous streaming requires a documented resource and transport decision.

NFC reports tag presence and bounded metadata when the contract allows it. Tag
meaning belongs on the PC/Codex side, and raw identifiers should be minimized or
redacted outside explicit local diagnostic paths.

IMU exposes high-level events such as picked up, shaken, and tilted. Raw IMU or
sensor telemetry streams require an explicit contract and must stay bounded and
best-effort.

## Resource Arbitration

Preserve this device-side arbitration order:

```text
safety > motion stop/neutral > audio capture/playback > command handling > camera > LED/idle
```

Any code touching hardware scheduling, callbacks, or buffers must respect this order.

## Failure Behavior

Expected behavior:

- Disconnect: enter degraded mode and try to reconnect.
- Audio underrun: stop playback and publish an error.
- Mic overrun: drop the chunk and publish an overrun error.
- Camera failure: publish an error and keep motion/audio/safety alive.
- NFC failure: publish an event/error and keep other capabilities alive.
- Servo/safety failure: stop motion, move neutral if safe, enter fault, and publish reason.

Firmware events should describe device facts, not application meaning. Do not
turn NFC tags, IR/remote codes, gestures, speech fragments, or raw sensor values
into commands on the device.

## Testing And Validation

For firmware changes, run or document:

- PlatformIO build-only check for the supported board target.
- Static checks available in the local toolchain.
- Contract checks for command metadata when interfaces are touched.
- Manual hardware validation notes for behavior that cannot be tested without the device.

Do not rely on CLI-side validation as the only safety protection.

## Documentation

- Update `../../docs/firmware.md` when firmware responsibilities, dependencies, safety behavior, or resource policy changes.
- Update `../../docs/ros-interface.md` when firmware topics, services, actions, status, or error contracts change.
- Update `../../docs/quality-gates.md` if firmware validation expectations change.
