# m5stackchan-microros

Firmware area for the M5StackChan side of the bridge.

The intended role of this firmware is to receive constrained commands from ROS 2 through micro-ROS and drive the device-side behavior: face display, neck servos, LEDs, touch input, IMU, NFC, proximity, and other local hardware features.

Design details live in [../../docs/firmware.md](../../docs/firmware.md).

## Firmware boundary

This package should own:

- micro-ROS connection setup
- command subscribers and status publishers
- display, servo, LED, audio, and sensor adapters
- local safety limits
- fallback behavior when ROS 2 is disconnected

It should not own:

- Codex skill logic
- high-level conversation planning
- cloud authentication
- raw ROS 2 command construction for humans
- a fork of the M5Stack factory firmware

## First target

The first useful firmware target is a minimal loop that connects to micro-ROS, publishes status, accepts a named face command, accepts one named motion command, and enforces servo limits locally.

Audio, camera, NFC, and raw IMU are part of the intended firmware capability set. They should be added as independent adapters rather than by forking the factory firmware.

## Initial build direction

Use PlatformIO with the Arduino framework.

Initial dependency stance:

- `StackChan-BSP` pinned to Git tag `1.1.0`
- `micro_ros_platformio` pinned to a verified commit SHA
- ROS 2 / micro-ROS distro: Jazzy
- micro-ROS transport: USB Serial

See [../../docs/firmware.md](../../docs/firmware.md) for the full dependency pinning policy.
