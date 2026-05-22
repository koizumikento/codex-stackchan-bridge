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

When a board is connected to the host, use PlatformIO upload rather than
calling `esptool` directly. The repository runner invokes PlatformIO through
`uv` with the Python packages required by `micro_ros_platformio`:

```bash
uv run --no-project python scripts/firmware_platformio.py upload --port COM3
```

If upload reaches the ESP32-S3 stub and then fails with `No serial data
received` or `Unable to verify flash chip connection`, keep the PlatformIO path
and retry without the stub at a lower upload speed:

```bash
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub
```

For bring-up serial diagnostics:

```bash
uv run --no-project python scripts/firmware_platformio.py monitor --port COM3
```

The runner syncs the canonical `ros/stackchan_msgs` package into
`extra_packages/` before build or upload so `micro_ros_platformio` can generate
firmware-side headers. When those messages change, regenerate the micro-ROS
cache with the container build first, then use the host PlatformIO runner for
the short build/upload loop.

The project uses `microros_stackchan.meta` as a `microros_user_meta` override.
The same path is also listed as `board_microros_user_meta` for forward
compatibility with PlatformIO-style board options. The default ESP32 meta in
the pinned `micro_ros_platformio` commit
allows one firmware service; StackChan bring-up currently needs
`/stackchan/default/device/face/set` and
`/stackchan/default/device/motion/run` plus
`/stackchan/default/device/motion/pose/set`, so `RMW_UXRCE_MAX_SERVICES` is
raised to `3`.

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

The current firmware initializes the micro-ROS serial transport, pings the
Agent, creates a device event publisher on
`/stackchan/default/device/events`, and publishes a bounded `firmware_ready`
bring-up event when an Agent is reachable. It also exposes bring-up device-side
services for face and named motion. LED, audio, camera, and sensor
services/actions remain follow-up work.
