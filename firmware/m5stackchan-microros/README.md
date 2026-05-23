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

Normal builds keep text diagnostics off because USB serial is also the
micro-ROS transport. For a firmware-only monitor session with the Agent stopped,
enable `STACKCHAN_SERIAL_DIAGNOSTICS=1`; do not run those text diagnostics while
the micro-ROS Agent is attached to the same COM port.

If the Agent creates the ROS graph but no samples reach ROS 2, build a
temporary minimal bring-up profile before changing command behavior:

```bash
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-minimal-bringup
```

That profile initializes only `/stackchan/default/device/status` and skips
optional services, actions, events, and raw telemetry. It is a diagnostic build
flag, not the normal firmware surface; flash a normal build again after the
transport/resource isolation smoke.

For a narrower command-path smoke after status works, use the core command
profile:

```bash
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-command-bringup
```

This keeps `/stackchan/default/device/status` plus the firmware-owned face,
LED, named-motion, and pose services, while still skipping optional events,
media actions, and raw telemetry. Use it to prove bridge-routed face control
before re-enabling the full entity set.

To isolate raw telemetry from media/action pressure, add raw telemetry
publishers to the core command profile:

```bash
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-raw-telemetry-bringup
```

This leaves audio actions, camera action, and audio chunk transport disabled.

If that profile passes but the full firmware still shows the ROS graph without
status samples, add one media/action group at a time:

```bash
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-audio-chunk-bringup
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-capture-audio-bringup
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-capture-camera-bringup
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-play-audio-bringup
```

These temporary profiles keep the status publisher, core command services, and
raw telemetry enabled, then add only the named media/action group.

The runner syncs the canonical `ros/stackchan_msgs` package into
`extra_packages/` before build or upload so `micro_ros_platformio` can generate
firmware-side headers. When those messages change, regenerate the micro-ROS
cache with the container build first, then use the host PlatformIO runner for
the short build/upload loop.

The project uses `microros_stackchan.meta` as a `microros_user_meta` override.
The same path is also listed as `board_microros_user_meta` for forward
compatibility with PlatformIO-style board options. The default ESP32 meta in
the pinned `micro_ros_platformio` commit
allows one firmware service. StackChan bring-up currently needs four
firmware-owned services, playback, audio capture, and camera capture action
servers, eight telemetry/event publishers, one capture chunk publisher, and one
playback chunk subscription, so the meta raises
`RMW_UXRCE_MAX_SERVICES` to `16`, `RMW_UXRCE_MAX_PUBLISHERS` to `20`, and
`RMW_UXRCE_MAX_SUBSCRIPTIONS` to `4`. It also raises
`RMW_UXRCE_MAX_CLIENTS` to `8`, keeps `RMW_UXRCE_MAX_HISTORY` at `16`, and keeps
the input and output reliable stream history at `8` so the full entity set has
entity margin without overflowing CoreS3 DRAM. Firmware action servers also use
bounded QoS depths for goal/result/cancel, feedback, and status paths, with
best-effort volatile feedback/status topics, so action entities do not starve
the device status heartbeat on the serial transport.
If a media action server fails to initialize, the firmware reports that media
transport as unavailable and keeps status, face, motion, and LED services alive
for hardware validation.
Keep these counts aligned when adding more firmware-owned actions, publishers,
or subscribers.

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
services for face, named motion, LED, audio playback/capture, and camera
snapshot transport. Remaining raw sensor services/actions should stay explicit
follow-up work.
