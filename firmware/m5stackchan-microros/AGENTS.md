# AGENTS.md

Instructions for agents editing `firmware/m5stackchan-microros`.

This directory owns the device firmware. Follow this file for firmware-specific rules, and use the repository root `AGENTS.md` for repository-wide policy.

## Ownership

Firmware owns:

- micro-ROS connection setup.
- Command subscribers and status/error publishers.
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
- Command-bearing interfaces must preserve `command_id`, `source`, `created_at`, and `priority`.
- Publish structured status and errors whenever possible.

## Device Capabilities

Firmware capability set includes:

- face
- motion
- LED
- audio playback
- microphone capture
- camera snapshot
- NFC events
- raw IMU stream
- high-level IMU events
- other local sensors

Audio is a first-class capability. Device exchange uses PCM 16 kHz mono 16-bit unless a documented decision changes it.

Camera owns snapshot support. Continuous streaming requires a documented resource and transport decision.

NFC reports tag IDs and presence events. Tag meaning belongs on the PC/Codex side.

IMU exposes raw telemetry plus high-level events such as picked up, shaken, and tilted.

## Resource Priority

Preserve this device-side priority:

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
