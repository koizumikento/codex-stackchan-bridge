# K151 Hardware Validation Checklist

Use this checklist when a K151 StackChan device is available. Record the date,
firmware build, bridge branch/commit, device id, and operator before marking the
hardware bring-up issue complete.

## Factory Firmware Recovery

- Before flashing repository firmware, confirm M5Burner can see the official
  StackChan firmware for recovery. In M5Burner, search for `StackChan`, enable
  `Only Official`, and download the latest official firmware.
- If custom firmware needs to be removed, restore with M5Burner by selecting the
  StackChan device port and burning the official firmware. See the M5Stack
  StackChan restore instructions:
  <https://docs.m5stack.com/en/stackchan>.
- Treat recovery as restoring to the official M5Burner firmware, not
  necessarily the exact factory-shipped version. Wi-Fi, account binding, servo
  calibration, and other on-device settings may need to be configured again
  after restore.
- If the serial port does not appear in M5Burner, enter CoreS3 download mode by
  holding `RST` until the internal green LED turns on, then release it. See the
  CoreS3 factory firmware guide:
  <https://docs.m5stack.com/en/guide/restore_factory/m5cores3>.

## Setup

- Flash the firmware with `STACKCHAN_DEVICE_ID=default`.
- Start the micro-ROS Agent over serial at 921600 baud.
- On Windows with Docker Desktop, verify the host serial port is actually
  usable from the Agent container before counting this step as ready. COM3 may
  appear as `/dev/ttyS2` inside the Docker Desktop WSL VM, but that device can
  still fail with `Input/output error` when opened from a Linux container.
- If Docker Desktop cannot open `/dev/ttyS2` directly, keep the host serial
  port on Windows and bridge it into the Agent container as TCP plus a container
  PTY:

  ```powershell
  uv run --no-project --with pyserial python scripts/serial_tcp_bridge.py --serial-port COM3 --baud 921600 --host 0.0.0.0 --tcp-port 11411
  uv run --no-project python scripts/microros_agent_container.py tcp-pty --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4
  ```

  A successful Agent connection logs `session established`, then creates the
  participant, topic, publisher, and datawriter for
  `/stackchan/default/device/events`.
- If the Agent creates the graph but all topic echoes time out, isolate the
  transport/status path with the temporary minimal firmware profile:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-minimal-bringup
  ```

  This diagnostic build initializes only
  `/stackchan/default/device/status`; it should not be used to validate face,
  motion, audio, camera, events, or raw telemetry. Restore a normal PlatformIO
  upload before marking the standard bridge command path ready.
- If minimal status works, isolate the core command path with:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-command-bringup
  ```

  This profile keeps `/stackchan/default/device/status` and the firmware-owned
  face, LED, named-motion, and pose services so `stackchanctl --backend bridge
  face happy` can be validated before optional event, media, and raw telemetry
  entities are re-enabled.
- If full firmware still creates the graph but no samples arrive, test raw
  telemetry pressure separately from media actions:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-raw-telemetry-bringup
  ```

  This profile keeps the core command path and raw telemetry publishers, while
  skipping audio actions, camera action, and audio chunk transport.
- If core raw telemetry works but full firmware still stops samples, add only
  one media/action group at a time:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-audio-chunk-bringup
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-capture-audio-bringup
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-capture-camera-bringup
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-core-play-audio-bringup
  ```

  These profiles extend `/stackchan/default/device/status`, core command
  services, and raw telemetry with a single media/action entity group so status
  sample loss can be attributed before returning to the full firmware profile.
- To validate the first firmware event payload on Windows Docker Desktop, run
  the Agent and `ros2 topic echo` in the same container. This avoids a Docker
  Desktop cross-container DDS data path that may show the topic graph but still
  miss samples:

  ```powershell
  uv run --no-project python scripts/ros2_container.py build
  uv run --no-project --with pyserial python scripts/serial_tcp_bridge.py --serial-port COM3 --baud 921600 --host 0.0.0.0 --tcp-port 11411
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-event-echo --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 6
  ```

  Expected first payload includes `event_name: firmware_ready`, `device_id:
  default`, and `payload_json:
  '{"transport":"serial","agent":"micro_ros"}'`.
- For a bridge/CLI smoke on Windows Docker Desktop, keep the serial TCP bridge
  running and execute Agent, `stackchan_bridge`, and `stackchanctl` in the same
  container:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --face-check happy --motion-check nod --motion-expected-error CALIBRATION_INVALID --reconnect-check
  ```

  Expected output includes `STACKCHAN_BRIDGE_OBSERVE_EXIT=0`,
  `connected: true`, `STACKCHAN_BRIDGE_EVENTS_EXIT=0`, and
  `STACKCHAN_BRIDGE_FIRMWARE_READY_SEEN=1`. With `--face-check happy`, it also
  expects `STACKCHAN_BRIDGE_FACE_EXIT=0` and
  `STACKCHAN_BRIDGE_FACE_SEEN=1`, proving
  `stackchanctl --backend bridge face happy --json` reached
  `/stackchan/default/device/face/set` through the bridge facade. With
  current K151 bring-up firmware, also visually confirm that the CoreS3 display
  changes to the requested static expression. A face smoke can be run by itself
  with `--face-check neutral`, `--face-check happy`, or another baseline
  expression when motion validation is not being exercised. With
  `--reconnect-check`, the same smoke also expects
  `STACKCHAN_BRIDGE_DISCONNECT_SEEN=1`,
  `STACKCHAN_BRIDGE_RECONNECT_SEEN=1`, at least two `device_connected`
  events, and at least one `device_disconnected` event. With
  `--disconnect-face-command sleepy`, it also expects
  `STACKCHAN_BRIDGE_DISCONNECT_COMMAND_REJECTED=1` and
  `STACKCHAN_BRIDGE_RECONNECT_DELAYED_FACE_SEEN=0`, proving commands issued
  while disconnected are rejected and are not replayed after reconnect. With
  `--motion-disconnect-check nod`, it expects
  `STACKCHAN_BRIDGE_MOTION_DISCONNECT_SEEN=1`,
  `STACKCHAN_BRIDGE_MOTION_RECONNECT_SEEN=1`, and
  `STACKCHAN_BRIDGE_MOTION_RECONNECT_STALE_MOTION_SEEN=0`, proving a short
  motion interrupted by Agent disconnect does not remain as an active public
  motion after reconnect. With `--soak-seconds 600 --soak-interval-seconds 30`,
  it keeps Agent and bridge alive for a short soak and expects every periodic
  observe to report `connected: true` with no structured error. With
  `--motion-check nod --motion-expected-error CALIBRATION_INVALID`, it expects
  `STACKCHAN_BRIDGE_MOTION_EXPECTED_ERROR_SEEN=1` and
  `STACKCHAN_BRIDGE_MOTION_OBSERVE_ERROR_SEEN=1`, proving the named motion
  path reached firmware and was rejected by device-owned calibration safety
  rather than being handled only by the bridge. The runner
  starts `stackchan_bridge` with the normal disconnected default and relies on
  observed firmware status/event traffic to mark `/stackchan/default`
  available.
- With a valid calibration record, omit `--motion-expected-error`. The same
  smoke expects `STACKCHAN_BRIDGE_MOTION_EXIT=0` and
  `STACKCHAN_BRIDGE_MOTION_STREAM_SEEN=1`. The stream check captures
  `/stackchan/default/status` during the command and should show
  `state: acting`, `motion: nod`, and then return to `motion: idle`.

## Servo Calibration And Motion Safety

- Boot with no valid calibration record and confirm `motion pose`, `motion home`,
  and named servo motion reject with `CALIBRATION_INVALID`.
- Before loading valid calibration, confirm the maintenance path is documented
  and separated from normal CLI/MCP/Codex command surfaces. Normal resources
  such as `/stackchan/<device_id>/cmd/motion/run` must not write calibration,
  unlock maintenance mode, or import/export NVS.
- When explicit maintenance tooling exists, load a valid firmware-owned
  calibration record through the documented local maintenance path. For early
  K151 bring-up this may be a firmware-local serial maintenance seed or
  build-time maintenance mode, but it must require an explicit operator
  confirmation and must not be reachable from routine `stackchanctl face`,
  `stackchanctl motion`, `stackchanctl observe`, or MCP calls.
- The human CLI includes explicit maintenance command shapes:
  `stackchanctl maintenance calibration status --json`,
  `stackchanctl maintenance calibration capture-neutral --confirm --json`, and
  `stackchanctl maintenance calibration reset --confirm --json`. The mock
  backend can exercise these contracts; the bridge backend must return
  `UNSUPPORTED_FEATURE` until a firmware-owned maintenance service exists.
- Record the calibration seed values, firmware build, operator, and whether the
  write was a seed, update, or reset. Do not store these values in CLI config as
  hardware safety authority.
- After writing valid calibration, reboot or otherwise force firmware to reload
  NVS, then confirm the next motion validation command no longer returns
  `CALIBRATION_INVALID` while `stackchanctl --backend bridge observe --json`
  still reports the device as connected.
- Until that maintenance path exists, mark valid-calibration motion checks
  unavailable and only complete the invalid-calibration rejection checks.
- With a valid calibration record, confirm `stackchanctl --backend bridge motion pose --pan-deg 30 --tilt-deg 20 --json`
  accepts and moves to the expected absolute home-frame pose.
- With a valid calibration record, confirm `stackchanctl --backend bridge motion nod --json`
  reaches firmware and moves only within the documented named-motion limits.
  Record observed direction, approximate range, noise, interference, and return
  behavior.
- On the initial K151 bring-up, a seed record with home/correction values all
  zero allowed `motion nod` to return `ok=true` and publish
  `state: acting` / `motion: nod` through `/stackchan/default/status`. After
  maintenance reset and a normal firmware upload, the same command returned
  `CALIBRATION_INVALID` again.
- Confirm `--pan-deg 129`, `--tilt-deg -1`, and non-finite values are rejected
  without clamping or motion.
- Confirm valid `motion pose` and `motion home` requests route through firmware
  `/stackchan/<device_id>/device/motion/pose/set` validation and do not publish
  synthetic pose telemetry as real actuation. Confirm `motion home` uses
  firmware home behavior and is not implemented as a public `pose(0,0)` alias.
- Confirm servo read failure or unplugged servo paths return `SERVO_READ_FAILED`
  or a recoverable motion error and enter a safe fault/neutral behavior.
- Before marking real-servo calibration validation complete, reset or erase the
  calibration record and confirm the same motion commands return
  `CALIBRATION_INVALID` again.

## Audio

- Before firmware reports audio capabilities as available, confirm
  `stackchanctl --backend bridge audio play prompt.wav --json` and microphone
  capture return structured `UNSUPPORTED_FEATURE` results while still reporting
  metadata and never printing PCM bytes. The playback unsupported smoke does
  not require `prompt.wav` to exist because the bridge backend must not open the
  payload until `audio_playback` is firmware-confirmed. Once firmware status
  reports `audio_playback` or `audio_capture` as available, the same smoke
  should return success markers instead of unsupported markers.
- With firmware-confirmed audio chunk transport, confirm playback/capture return
  structured accepted or completed results, microphone capture publishes bounded
  16 kHz mono PCM chunks, and overrun/underrun events are visible through
  `stackchanctl events`.
- Confirm malformed format, sequence gaps, disconnect, and timeout cases produce
  structured recoverable errors.

## LED

- Confirm `stackchanctl --backend bridge led progress --json`,
  `stackchanctl --backend bridge led success --json`, and
  `stackchanctl --backend bridge led off --json` route through firmware
  `/stackchan/<device_id>/device/led/set` and visibly update the K151 RGB LEDs.
- Confirm an unknown pattern returns structured `UNKNOWN_COMMAND` and does not
  leave a stale success state.
- Confirm LED updates do not block face, motion, audio, camera, safety, or
  event handling.

## Camera

- Until firmware-confirmed camera transport exists, confirm
  `stackchanctl --backend bridge camera capture --output frame.jpg --quality 80 --json`
  returns structured `UNSUPPORTED_FEATURE` with metadata only and never prints
  JPEG/base64 bytes.
- With firmware-confirmed camera transport, confirm the device produces QVGA
  JPEG snapshots and rejects or discards frames larger than 96 KiB with
  `CAMERA_CAPTURE_FAILED`.
- Confirm camera failure does not block motion, audio, safety, or event handling.

## Events And Redaction

- Trigger NFC, IR/remote, audio, camera, button, IMU, and power events.
- During first micro-ROS bring-up, confirm ROS 2 can see the firmware-owned
  event topic:

  ```bash
  uv run --no-project python scripts/ros2_container.py --network host exec "source /opt/ros/jazzy/setup.bash && source install/setup.bash && timeout 25 ros2 topic list -t"
  ```

  Expected topics:
  `/stackchan/default/device/events [stackchan_msgs/msg/StackChanEvent]` and
  `/stackchan/default/device/status [stackchan_msgs/msg/StackChanStatus]`.
- Confirm the deterministic bring-up event can be echoed with the
  same-container Agent smoke command from Setup. If a separate ROS 2 container
  can list the topic but `ros2 topic echo --once` times out, record it as a
  Docker Desktop DDS networking limitation, not a firmware-to-Agent failure,
  when the same-container echo succeeds.
- Confirm public events use bounded payload JSON and normal CLI/MCP output does
  not include raw NFC IDs, raw IR codes, protocol dumps, PCM, transcripts, or
  image bytes.
- Confirm device id mismatches are dropped or reported as conflicts without
  crossing device namespaces.
- For a sensor/event/redaction sweep on Windows Docker Desktop, keep the serial
  TCP bridge running and execute:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 6
  ```

  The sweep starts Agent, bridge, and CLI probes in one container, then records
  `observe`, `power status`, metadata-only audio/camera unsupported smokes,
  device and public sensor topics, event output, and normal log redaction
  markers. K151 raw IMU validation expects samples on both
  `/stackchan/default/device/imu/raw` and `/stackchan/default/imu/raw` while
  `STACKCHAN_SENSOR_SWEEP_OBSERVE_RAW_TELEMETRY_SEEN=0` remains true.
- For IMU/NFC/IR hardware event fixtures, add a manual stimulus window:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 8 --stimulus-window-seconds 20
  ```

  During the printed stimulus window:

  | Stimulus group | Manual action | Expected event names | Normal-output redaction rule |
  | --- | --- | --- | --- |
  | Buttons | Press, release, and hold CoreS3 BtnA, BtnB, and BtnC. | `button_pressed`, `button_released`, `button_held` | Only bounded button ids `a`, `b`, and `c`; no maintenance/control payloads. |
  | IMU high-level events | Pick up, place down, tilt, face up/down, and shake within safe servo limits. | `picked_up`, `placed_down`, `tilted`, `face_up`, `face_down`, `shaken` | No raw accelerometer/gyroscope samples in `observe` or normal events. |
  | Touch | Touch, release, and hold the K151 touch surface. | `touched`, `touch_released`, `touch_held` | Only bounded zone metadata; no raw maintenance/control payloads. |
  | Proximity | Move a hand or object near and away from the LTR553 proximity sensor. | `proximity_near`, `proximity_clear` | Only bounded semantic state; raw samples stay on telemetry topics. |
  | Light | Cover the light sensor, expose it to brighter light, then return to ambient. | `light_changed`, `dark_detected`, `bright_detected` | Only bounded semantic state; raw samples stay on telemetry topics. |
  | Power | Connect/disconnect USB power or use a known safe low-power fixture. | `charging_started`, `charging_stopped`, `power_source_changed`, `battery_low`, `battery_recovered`, `brownout_risk`, `power_fault` | Only bounded power state/fault code; no raw maintenance/control payloads. |
  | NFC | Present one tag, remove it, then try a read-failure case such as quick removal. | `nfc_detected`, `nfc_removed`, `nfc_read_failed` | Public events/logs must not expose tag IDs, UIDs, or raw tag payloads. |
  | IR/remote | Press and release a known remote button near the receiver. | `remote_button_pressed`, `remote_button_released`, `remote_command_received` | Public events/logs must not expose raw IR codes, protocol dumps, or remote IDs. |

  The runner emits
  `STACKCHAN_EVENT_STIMULUS_{BUTTON,IMU,TOUCH,PROXIMITY,LIGHT,POWER,NFC,IR}_STATUS=PASS`
  when a matching event is observed and `UNAVAILABLE` when the current firmware
  does not publish that event family during the window. Keep `UNAVAILABLE` as a
  recorded fixture result until the corresponding firmware adapter exists.
- For NFC `UNAVAILABLE`, verify the UnitNFC is on the StackChan-BSP NFC example
  I2C path. If firmware-only serial diagnostics are needed, rebuild with
  `STACKCHAN_SERIAL_DIAGNOSTICS=1` and run the monitor with the micro-ROS Agent
  stopped; do not mix text diagnostics with the Agent on the same USB serial
  transport. Check for `nfc_bus=in_i2c`, non-negative `nfc_sda`/`nfc_scl`,
  `nfc_i2c_present=true`, increasing `nfc_detect_attempts`, and
  `nfc_detect_hits` while a tag is presented. If detect hits increase but no
  event appears, inspect `nfc_identify_failures` and tag family compatibility.
  Do not reinitialize the CoreS3 default `Wire` bus for this adapter during
  normal bring-up. The pinned StackChan-BSP 1.1.0 `examples/NFC/Detect` sketch
  adds `UnitNFC` to `M5UnitUnified` on `M5.In_I2C`; use that as the reference
  path unless a later BSP release changes the wrapper.
- For IR `UNAVAILABLE`, verify the receiver signal path to GPIO 10 and, in the
  same firmware-only diagnostic mode, check for `ir_rx_pin=10`, increasing
  `ir_decodes`, and `ir_overflows` while pressing a known remote button. Normal
  output must still keep raw IR values and protocol dumps redacted.
- The same sweep emits
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_UNSUPPORTED_SEEN`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_UNSUPPORTED_SEEN`, and
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_UNSUPPORTED_SEEN`, plus corresponding
  `_OK_SEEN` markers when firmware-owned transport succeeds. Treat either a
  structured unsupported result or an accepted firmware-confirmed result as a
  transport smoke pass while that feature is being brought up; the normal
  redaction scan must still report no PCM, transcript, image, JPEG, or base64
  payloads.
- Confirm liveness behavior by stopping the host serial TCP bridge or the
  micro-ROS Agent after `connected: true`; within the configured timeout,
  `stackchanctl --backend bridge observe --json` should return
  `TRANSPORT_DISCONNECTED`, and reconnecting should restore `connected: true`.
- While disconnected, run a normal command such as
  `stackchanctl --backend bridge face sleepy --json` and confirm it returns
  `TRANSPORT_DISCONNECTED`. After reconnect, confirm the requested disconnected
  command did not appear as the current face, last successful command, or a
  delayed device-side service call.
- When validation is complete, stop the serial TCP bridge or the process that
  owns TCP port 11411 so COM3 is released before rewiring or reflashing:

  ```powershell
  Get-NetTCPConnection -LocalPort 11411 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
  ```

## K151 Sensor/Event Sweep Results

Record each real-device sweep here until the sensor adapters move from
bring-up to routine regression coverage.

2026-05-22, device `default`, COM3 through Windows serial TCP bridge, firmware
version `bringup`, command:

```powershell
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 6
```

Observed results:

- `observe`: pass. `STACKCHAN_SENSOR_SWEEP_OBSERVE_EXIT=0`,
  `connected: true`, `device_state: ready`, and
  `STACKCHAN_SENSOR_SWEEP_OBSERVE_RAW_TELEMETRY_SEEN=0`. Raw touch,
  proximity, light, power, NFC, IR, audio, camera, and PCM payloads did not
  appear in normal observe output.
- `power status`: unavailable by current firmware capability. The command
  returned `UNSUPPORTED_FEATURE` with message `power telemetry for 'default'
  has not been received`, and
  `STACKCHAN_SENSOR_SWEEP_POWER_STATUS_STRUCTURED_ERROR_SEEN=1`.
- ROS graph: bridge/public and firmware/device resources were present for
  `/stackchan/default/{device/,}touch/state`,
  `/stackchan/default/{device/,}proximity/raw`,
  `/stackchan/default/{device/,}light/raw`, and
  `/stackchan/default/{device/,}power/status`.
- Topic samples: unavailable. Each touch, proximity, light, and power device
  and public `ros2 topic echo --once` probe timed out with exit `124`, so
  sample frequency, stale thresholds, saturation values, and noise examples
  could not be measured on this firmware build.
- Events: pass for normal event redaction. `stackchanctl events list` returned
  only bridge `device_connected` and firmware `firmware_ready` events with
  bounded payloads. `STACKCHAN_SENSOR_SWEEP_EVENTS_EXIT=0` and
  `STACKCHAN_SENSOR_SWEEP_EVENTS_SENSITIVE_PAYLOAD_SEEN=0`.
- Normal logs: pass for sensitive payload search.
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0` for NFC tag IDs, IR
  raw/remote codes, PCM, image/JPEG/base64 payloads, speech text, and
  transcript text.
- NFC, IR/remote, IMU high-level events, audio payload, and camera payload
  hardware stimuli: unavailable in this sweep because the current K151 bring-up
  firmware has no publishing adapter for those real hardware events yet.

Follow-up classification:

- Completed MVP follow-up: firmware-owned real telemetry publishers for power,
  touch, proximity, and light were implemented and repeated below.
- Post-MVP: add explicit firmware event adapters and hardware fixtures for IMU,
  NFC, and IR/remote stimuli before treating those redaction paths as
  hardware-validated.

2026-05-22, device `default`, COM3 through Windows serial TCP bridge, firmware
version `bringup` after K151 telemetry adapters, command:

```powershell
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 8
```

Observed results:

- `observe`: pass. `STACKCHAN_SENSOR_SWEEP_OBSERVE_EXIT=0`,
  `connected: true`, `device_state: ready`, and
  `STACKCHAN_SENSOR_SWEEP_OBSERVE_RAW_TELEMETRY_SEEN=0`. Raw touch,
  proximity, light, power, NFC, IR, audio, camera, and PCM payloads did not
  appear in normal observe output.
- ROS graph: bridge/public and firmware/device resources were present for
  `/stackchan/default/{device/,}touch/state`,
  `/stackchan/default/{device/,}proximity/raw`,
  `/stackchan/default/{device/,}light/raw`, and
  `/stackchan/default/{device/,}power/status`.
- Topic samples: pass for all K151 low-rate telemetry resources. Device and
  public topic probes returned samples for touch, proximity, light, and power:
  `STACKCHAN_SENSOR_SWEEP_TOPIC_{device,public}_{touch,proximity,light,power}_SAMPLE_SEEN=1`.
- Touch sample: `zone_count=3`, `zone_mask=0`, and intensities `[0, 0, 0]`
  with surface `stackchan_head` while untouched.
- Proximity sample: `sensor_index=0`, `raw=0`, `signal=0.0`,
  `distance_m=.nan`, and `saturated=false` in the sweep environment.
- Light sample: `sensor_index=0`, `raw=0`, `illuminance_lux=0.0`, and
  `saturated=false` in the sweep environment.
- Power sample: USB-powered and charging with `voltage_v=4.181250095367432`,
  current around `-6.5` to `-7.0` mA, `percentage=100.0`,
  `low_battery=false`, and `brownout_risk=false`.
- `power status`: pass. `STACKCHAN_SENSOR_SWEEP_POWER_STATUS_EXIT=0` and
  `ok=true`; the bridge returned non-stale power status sourced from the public
  telemetry relay.
- Events: pass for normal event redaction. `stackchanctl events list` returned
  bridge `device_connected`, firmware `firmware_ready`, and bounded light event
  `dark_detected` with empty payload. `STACKCHAN_SENSOR_SWEEP_EVENTS_EXIT=0`
  and `STACKCHAN_SENSOR_SWEEP_EVENTS_SENSITIVE_PAYLOAD_SEEN=0`.
- Event stimulus fixture markers: `STACKCHAN_EVENT_STIMULUS_IMU_STATUS=UNAVAILABLE`,
  `STACKCHAN_EVENT_STIMULUS_NFC_STATUS=UNAVAILABLE`, and
  `STACKCHAN_EVENT_STIMULUS_IR_STATUS=UNAVAILABLE`. The current firmware did
  not publish IMU high-level, NFC, or IR event families during the sweep.
- Normal logs: pass for sensitive payload search.
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0` for NFC tag IDs, IR
  raw/remote codes, PCM, image/JPEG/base64 payloads, speech text, and
  transcript text.
- NFC, IR/remote, IMU high-level events, audio payload, and camera payload
  hardware stimuli remain unavailable in this sweep because those real hardware
  event adapters are not yet part of the K151 bring-up firmware.

2026-05-23, device `default`, COM3 through Windows serial TCP bridge, firmware
version `bringup` after K151 IMU/NFC/IR event-adapter and audio/camera smoke
updates, commands:

```powershell
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 8 --stimulus-window-seconds 20
uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 8 --face-check happy --motion-check nod
```

Observed results:

- Host serial TCP bridge: pass after running it as a detached process. A
  shell-local PowerShell `Start-Job` can disappear when that shell exits, which
  causes Docker `socat` to report `Connection refused` and the Agent to wait for
  `/tmp/stackchan-tty`.
- Topic samples: pass for touch, proximity, light, and power on both
  `/stackchan/default/device/...` and public `/stackchan/default/...` resources.
- `power status`: pass with USB power, charging, `percentage=100.0`,
  `low_battery=false`, and `brownout_risk=false`.
- IMU event stimulus: pass. `STACKCHAN_EVENT_STIMULUS_IMU_STATUS=PASS`, and
  `stackchanctl events list` included bounded `picked_up` and `tilted` events
  with no raw accelerometer or gyroscope samples in normal output.
- NFC event stimulus: still unavailable in this sweep.
  `STACKCHAN_EVENT_STIMULUS_NFC_STATUS=UNAVAILABLE` and
  `STACKCHAN_EVENT_STIMULUS_NFC_EVENT_SEEN=0`; keep the NFC validation issue
  open until a physical tag present/remove/read-failure stimulus produces the
  expected events.
- IR/remote event stimulus: still unavailable in this sweep.
  `STACKCHAN_EVENT_STIMULUS_IR_STATUS=UNAVAILABLE` and
  `STACKCHAN_EVENT_STIMULUS_IR_EVENT_SEEN=0`; keep the IR validation issue open
  until a known remote/pin condition produces the expected events.
- Audio/camera checks: pass as metadata-only unsupported smokes until
  firmware-confirmed transport exists.
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_UNSUPPORTED_SEEN=1`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_UNSUPPORTED_SEEN=1`, and
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_UNSUPPORTED_SEEN=1`.
- Redaction checks: pass. `STACKCHAN_SENSOR_SWEEP_EVENTS_SENSITIVE_PAYLOAD_SEEN=0`
  and `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0` for raw NFC IDs,
  raw IR codes/protocol dumps, PCM, transcript, image/JPEG/base64 payloads, and
  speech text.
- Face/motion bridge smoke: pass. `STACKCHAN_BRIDGE_FACE_SEEN=1`,
  `STACKCHAN_BRIDGE_MOTION_EXIT=0`, and
  `STACKCHAN_BRIDGE_MOTION_STREAM_SEEN=1` confirmed the bridge facade reached
  firmware-owned face and `motion nod` paths. The final observe can return
  `motion: idle` after the tuned motion completes, so use the status stream
  marker for the in-motion observation.

Remaining physical checks:

- NFC present/remove/read-failure should make
  `STACKCHAN_EVENT_STIMULUS_NFC_STATUS=PASS`.
- IR remote input should make `STACKCHAN_EVENT_STIMULUS_IR_STATUS=PASS`.

2026-05-23 follow-up, device `default`, COM3 through Windows serial TCP bridge,
after changing UnitNFC initialization away from a direct Port A
`Wire.begin(...)` attempt, commands:

```powershell
uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 12 --face-check happy
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 8 --stimulus-window-seconds 20
```

Observed results:

- A firmware build that called `Wire.end()`/`Wire.begin(...)` for the UnitNFC
  path uploaded successfully but regressed micro-ROS Agent bring-up: the Agent
  stayed at setup logging, never established a session, and bridge probes
  returned disconnected. Revert that wiring strategy instead of treating it as
  a firmware or Docker transport failure.
- With a managed M5 I2C object, face smoke recovered:
  `STACKCHAN_BRIDGE_STATUS_CONNECTED=1`, `STACKCHAN_BRIDGE_FACE_EXIT=0`,
  `STACKCHAN_BRIDGE_FACE_SEEN=1`, and
  `STACKCHAN_BRIDGE_FIRMWARE_READY_SEEN=1`.
- The sensor sweep again passed low-rate touch, proximity, light, device/public
  power topics, `power status`, metadata-only audio/camera unsupported checks,
  and normal redaction checks.
- This follow-up did not capture manual IMU, NFC, or IR stimuli:
  `STACKCHAN_EVENT_STIMULUS_IMU_STATUS=UNAVAILABLE`,
  `STACKCHAN_EVENT_STIMULUS_NFC_STATUS=UNAVAILABLE`, and
  `STACKCHAN_EVENT_STIMULUS_IR_STATUS=UNAVAILABLE`.
  Use the earlier same-day IMU `PASS` fixture for IMU event confidence, and
  keep NFC/IR validation open until physical stimuli produce events.

StackChan-BSP wrapper check:

- The pinned `StackChan-BSP` 1.1.0 source has no dedicated NFC/IR high-level
  wrapper on `M5StackChan_Class`. Its NFC example includes `M5StackChan.h`,
  then uses `M5UnitUnified` / `M5UnitUnifiedNFC` and `NFCLayerA` directly. Its
  IR receive example includes `M5StackChan.h`, then uses `IRremoteESP8266`
  `IRrecv` directly on GPIO 10.
- Therefore the bridge firmware should stay aligned to those BSP examples:
  NFC through `M5UnitUnifiedNFC` on `M5.In_I2C`, and IR receive through
  `IRremoteESP8266` on GPIO 10. If a future BSP release adds first-class NFC or
  IR members, migrate to that wrapper before adding more direct adapter logic.

2026-05-23 BSP-alignment follow-up, device `default`, after changing UnitNFC
from `M5.Ex_I2C` to the StackChan-BSP example path `M5.In_I2C`:

- `uv run --no-project python scripts/firmware_platformio.py build`: pass.
- `uv run --no-project python scripts/firmware_platformio.py upload --port COM3
  --upload-speed 115200 --no-stub`: pass.
- `tcp-pty-bridge-smoke --skip-build ... --face-check happy`: pass.
  `STACKCHAN_BRIDGE_STATUS_CONNECTED=1`, `STACKCHAN_BRIDGE_FACE_EXIT=0`,
  `STACKCHAN_BRIDGE_FACE_SEEN=1`, and
  `STACKCHAN_BRIDGE_FIRMWARE_READY_SEEN=1`.
- `tcp-pty-sensor-sweep --skip-build ... --stimulus-window-seconds 10`: pass
  for touch, proximity, light, device/public power, `power status`,
  audio/camera unsupported smokes, and sensitive payload redaction. The initial
  observe can still race before liveness has flipped to connected, but the Agent
  tail showed `session established` and all sampled topics were received.
- NFC and IR are still not physically validated in this run:
  `STACKCHAN_EVENT_STIMULUS_NFC_STATUS=UNAVAILABLE` and
  `STACKCHAN_EVENT_STIMULUS_IR_STATUS=UNAVAILABLE`. Use an actual tag and a
  known remote while watching the safe counters before marking KOIZUMI-75 or
  KOIZUMI-76 done.

2026-05-23 ROS 2 command-path follow-up, device `default`, COM3 through the
Windows serial TCP bridge, after the BSP-aligned UnitNFC firmware upload:

```powershell
uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 12 --face-check happy --motion-check nod --pose-pan-deg 10 --pose-tilt-deg 20 --home-check
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 8 --stimulus-window-seconds 0
```

Observed results:

- micro-ROS transport and bridge liveness: pass. The first `observe` can race
  before the bridge flips to connected, but the ROS graph contained
  `/stackchan/default/device/motion/run`,
  `/stackchan/default/device/motion/pose/set`,
  `/stackchan/default/device/motion/pose`, and
  `/stackchan/default/motion/pose`; the bridge status marker reported
  `STACKCHAN_BRIDGE_STATUS_CONNECTED=1`.
- Face and named motion over ROS 2: pass. `face happy` returned
  `STACKCHAN_BRIDGE_FACE_EXIT=0` and `STACKCHAN_BRIDGE_FACE_SEEN=1`.
  `motion nod` returned `STACKCHAN_BRIDGE_MOTION_EXIT=0` and the status stream
  reported `STACKCHAN_BRIDGE_MOTION_STREAM_SEEN=1` while the final observation
  could already be back at `motion: idle`.
- Explicit head pose and home over ROS 2: pass. `motion pose --pan-deg 10
  --tilt-deg 20` returned `STACKCHAN_BRIDGE_POSE_COMPLETED=1`,
  `STACKCHAN_BRIDGE_POSE_PAN_SEEN=1`, and
  `STACKCHAN_BRIDGE_POSE_TILT_SEEN=1`; `motion status` reported
  `pan_deg=10.0`, `tilt_deg=20.0`, `stale=false`. `motion home` returned
  `STACKCHAN_BRIDGE_HOME_COMPLETED=1`,
  `STACKCHAN_BRIDGE_HOME_PAN_SEEN=1`, and
  `STACKCHAN_BRIDGE_HOME_TILT_SEEN=1`; `motion status` reported
  `pan_deg=0.0`, `tilt_deg=0.0`.
- Low-rate sensor and power topics: pass for touch, proximity, light, and
  device/public power samples plus `power status`.
- Audio acquisition/playback over ROS 2: structured unsupported, not a hardware
  transport failure. `/stackchan/default/device/audio/chunks` was present, but
  `stackchanctl --backend bridge audio play ...` and
  `stackchanctl --backend bridge audio capture --seconds 1 --output mic.wav`
  returned `UNSUPPORTED_FEATURE` with the expected
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_UNSUPPORTED_SEEN=1` and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_UNSUPPORTED_SEEN=1` markers because
  firmware-confirmed audio action transport is not implemented yet.
- Camera snapshot over ROS 2: earlier sweeps returned structured unsupported.
  With firmware-confirmed camera transport, the same command should return
  `ok=true` and `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=1`; failure or
  oversize frames should return structured `CAMERA_CAPTURE_FAILED` without
  exposing JPEG/base64 payloads.
- Privacy/redaction: pass. The sweep reported
  `STACKCHAN_SENSOR_SWEEP_EVENTS_SENSITIVE_PAYLOAD_SEEN=0` and
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0`; normal output and
  logs did not expose PCM payloads, image/JPEG/base64 payloads, NFC tag IDs, IR
  raw codes, speech text, or transcript text.
- IMU/NFC/IR stimulus checks were not exercised in this no-stimulus run:
  `STACKCHAN_EVENT_STIMULUS_IMU_STATUS=UNAVAILABLE`,
  `STACKCHAN_EVENT_STIMULUS_NFC_STATUS=UNAVAILABLE`, and
  `STACKCHAN_EVENT_STIMULUS_IR_STATUS=UNAVAILABLE`.

2026-05-23 implementation/update smoke, device `default`, COM3 through the
Windows serial TCP bridge, after LED, raw IMU relay, and media capability-gate
updates:

```powershell
uv run --no-project python scripts/firmware_platformio.py build
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 8 --stimulus-window-seconds 0
uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 12 --led-check --face-check happy --motion-check nod --pose-pan-deg 10 --pose-tilt-deg 20 --home-check
```

Observed results:

- Firmware build and upload: pass through repository PlatformIO helpers.
- Container ROS build: pass for `stackchan_msgs` and `stackchan_bridge`. Do not
  rely on `--skip-build` after bridge Python changes; it can run a stale
  installed bridge node.
- Bring-up failures found and fixed during this pass:
  - The bridge crashed after a fresh container build because `ActionClient` was
    not imported.
  - The first LED forwarding smoke crashed because `_set_led_type` was not kept
    on the node before building firmware-owned `SetLed` requests.
  - A stale `--skip-build` run hid the missing public `/stackchan/default/imu/raw`
    relay until the container install was rebuilt.
  - Device-owned media actions appeared in `ros2 action list -t` but standard
    action clients still reported the server unavailable until the bridge
    firmware-facing `ActionClient` feedback/status QoS was matched to the
    firmware action server's best-effort volatile feedback/status topics.
- LED command path: pass. `--led-check` sent `progress`, `success`, and `off`
  through `stackchanctl --backend bridge led ... --json`; all returned
  `ok=true`, and the bridge log recorded `led_set_accepted` for each pattern.
- Face, named motion, absolute pose, and home command paths: pass in the same
  smoke run. `face happy`, `motion nod`, `motion pose --pan-deg 10
  --tilt-deg 20 --wait`, and `motion home --wait` all completed or were
  accepted through the bridge/firmware path. The motion status stream observed
  `motion: nod`; pose status reported `pan_deg=10.0`, `tilt_deg=20.0`, then
  home reported `pan_deg=0.0`, `tilt_deg=0.0`.
- Raw IMU transport: pass. The sensor sweep received samples from both
  `/stackchan/default/device/imu/raw` and `/stackchan/default/imu/raw` while
  `observe` still reported `STACKCHAN_SENSOR_SWEEP_OBSERVE_RAW_TELEMETRY_SEEN=0`.
- Touch, proximity, light, and power telemetry: pass on both device-owned and
  bridge-public topics. `stackchanctl --backend bridge power status --json`
  returned `ok=true`.
- Audio and camera: the sweep accepts structured `UNSUPPORTED_FEATURE` during
  unavailable bring-up states. For audio capture, `MIC_OVERRUN` is also a valid
  transport-reached-firmware result during sensor sweep because it proves the
  bridge action path reached the firmware-owned action and received a bounded
  firmware error; a later audio-quality issue must still drive `audio capture`
  to `ok=true` with usable PCM/WAV output. Camera capture must still keep JPEG
  bytes/base64 out of normal output and logs.
- Privacy/redaction: pass. Normal event and log scans reported no sensitive
  payload exposure.
- Manual button/IMU/touch/proximity/light/power/NFC/IR stimulus checks were not
  performed in this no-stimulus sweep and remain recorded as `UNAVAILABLE`.

## Cleanup

- Save the command transcript and observed result codes in the PR or Linear
  issue.
- Reset temporary maintenance/debug firmware changes before merging production
  code.
