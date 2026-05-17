# m5stackchan-microros

Firmware area for the M5StackChan side of the bridge.

The intended role of this firmware is to receive constrained commands from ROS 2 through micro-ROS and drive the device-side behavior: face display, neck servos, LEDs, touch input, IMU, NFC, proximity, and other local hardware features.

Design details live in [../../docs/firmware.md](../../docs/firmware.md).

## Firmware boundary

This package should own:

- micro-ROS connection setup
- device-side service/action handlers and status publishers
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

## Build direction

Use PlatformIO with the Arduino framework.

Dependency stance:

- `StackChan-BSP` pinned to Git tag `1.1.0`
- `micro_ros_platformio` pinned to a provisional commit SHA until the first
  ROS 2 Jazzy PlatformIO build verifies it
- ROS 2 / micro-ROS distro: Jazzy
- micro-ROS transport: USB Serial

See [../../docs/firmware.md](../../docs/firmware.md) for the full dependency pinning policy.

## Local development

The initial PlatformIO target is `stackchan-cores3`:

```bash
pio run -d firmware/m5stackchan-microros -e stackchan-cores3
```

The target keeps `-std=gnu++17` and `UART_SCLK_DEFAULT=UART_SCLK_XTAL` in
`platformio.ini` for compatibility with the pinned StackChan-BSP and
espressif32 toolchain.

To keep PlatformIO and ESP32 toolchains out of the host environment, use the
repository firmware container runner:

```bash
uv run --no-project python scripts/firmware_container.py build-image
uv run --no-project python scripts/firmware_container.py build
```

The firmware package also includes hardware-free contract checks:

```bash
uv run python -m unittest discover -s firmware/m5stackchan-microros/tests
```

Current dependency pins:

- `StackChan-BSP`: `1.1.0`
- `micro_ros_platformio`: `de7a61c` from the upstream repository line used while preparing the Jazzy PlatformIO skeleton
- micro-ROS serial baud: `921600`, chosen as the initial bring-up target for audio/camera transport headroom
- PlatformIO monitor speed: `921600`, matching the firmware serial baud for
  bring-up diagnostics

The micro-ROS README documents `board_microros_distro = jazzy` and serial transport configuration; the first real build should re-check the pinned commit in the ROS 2 Jazzy environment before hardware flashing.

The current firmware scaffold does not initialize micro-ROS publishers,
services, actions, or executor objects yet. `try_connect_microros_agent()` is a
guarded stub so firmware remains in degraded mode until the ROS 2 environment
and hardware bring-up path are available.
