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
  uv run --no-project python scripts/microros_agent_container.py build-image
  uv run --no-project --with pyserial python scripts/serial_tcp_bridge.py --serial-port COM3 --baud 921600 --host 0.0.0.0 --tcp-port 11411
  uv run --no-project python scripts/microros_agent_container.py tcp-pty --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4
  ```

  The host serial TCP bridge opens COM3 with DTR and RTS inactive by default.
  Keep that default for normal runtime Agent bridging on ESP32-S3/CoreS3 boards
  because active DTR/RTS can interact with auto-reset or boot control lines.
  Use `--dtr active`, `--rts active`, or `unchanged` only for a deliberate
  reset-line diagnostic.
  If repeated Agent sessions fail to re-establish XRCE while COM3 still shows
  byte traffic, restart the host bridge with `--reset-pulse rts`; this briefly
  pulses RTS active after opening COM3, then returns it inactive before
  accepting the Agent TCP client.

  The repository Agent image builds micro-ROS Agent from source against the
  same ROS 2 Jazzy base used by `stackchan_bridge`; prefer it for bridge/CLI
  smoke tests so Agent, `rclpy`, and generated type support remain
  ABI-aligned. The image also carries the smoke-time runtime tools such as
  `socat`; smoke scripts should not run `apt-get update` during each validation
  pass.

  The same-container bridge and sensor smoke commands build
  `stackchan_msgs` and `stackchan_bridge` incrementally by default with
  `--symlink-install`. Use the default path after source changes:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --face-check happy
  ```

  Use `--skip-build` only for repeated hardware smokes after a successful
  normal smoke build. The helper records `install/.stackchan_ros_build_stamp`
  and fails `--skip-build` if files under `ros/stackchan_msgs` or
  `ros/stackchan_bridge` are newer than that stamp. If a diagnostic must use an
  intentionally stale install, add `--allow-stale-install` and record that fact
  in the Linear issue. Use `--clean-ros-build` only after dependency, generated
  interface, or CMake cache problems; it restores the older clean-cache behavior
  for that run.

  Smoke output ends with `STACKCHAN_SMOKE_PHASE_*_SECONDS` lines for setup,
  ROS build or stale guard, PTY setup, bridge startup, Agent startup, smoke
  checks, and teardown. Paste those timing lines into the relevant Linear issue
  when build time is part of the investigation. The first normal smoke after
  this change resets only `build/stackchan_msgs` and `build/stackchan_bridge`
  if no smoke build stamp exists, because older non-symlink build caches can
  conflict with `--symlink-install`. Later normal smokes use per-package stamps:
  `stackchan_msgs` is rebuilt only when message/interface sources changed, while
  `stackchan_bridge` can be refreshed by itself for bridge-only edits.

  A successful Agent connection logs `session established`, then creates the
  participant, topic, publisher, and datawriter for
  `/stackchan/default/device/events`.
- For local TTS validation, start VOICEVOX as an operator-owned local service
  before running `say` smokes:

  ```powershell
  docker compose up -d voicevox
  ```

  If the bridge runs in a compose service on the same network, configure
  `STACKCHAN_TTS_ENDPOINT=http://voicevox:50021`. If the bridge runs through
  the repository Python Docker helpers and reaches the host-published port, use
  `STACKCHAN_TTS_ENDPOINT=http://host.docker.internal:50021`. From the host,
  use `http://localhost:50021` for direct diagnostics. Do not put provider
  endpoints, raw speaker IDs, generated audio, or speech text into Linear
  comments or normal logs; record only profile names, command IDs, result
  codes, and audible observations.

  The same-container smoke can run a TTS-backed `say` check with local TTS
  enabled on the bridge:

  ```powershell
  $env:STACKCHAN_TTS_ENDPOINT='http://host.docker.internal:50021'
  $env:STACKCHAN_TTS_SPEED_SCALE='3.0'
  $env:STACKCHAN_TTS_PRE_PHONEME_LENGTH='0.0'
  $env:STACKCHAN_TTS_POST_PHONEME_LENGTH='0.0'
  $env:STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD='512'
  $env:STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS='20.0'
  $env:STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES='64'
  $env:STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES='96'
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 190 --say-check "はい" --say-voice default
  ```

  The smoke expects `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `STACKCHAN_BRIDGE_SAY_VOICE_PROFILE_SEEN=1`, and
  `STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=1`.
- If the Agent creates the graph but all topic echoes time out, isolate the
  transport/status path with the temporary minimal firmware profile:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-minimal-bringup
  ```

  This diagnostic build initializes only
  `/stackchan/default/device/status` and skips board hardware adapters such as
  M5/BSP, servo, sensor, audio, and camera initialization; it should not be used
  to validate face, motion, audio, camera, events, or raw telemetry. Restore a
  normal PlatformIO upload before marking the standard bridge command path
  ready.
- If minimal status works but normal firmware drops the Agent handshake, add
  board initialization back incrementally before the same status-only loop:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --microros-board-init-bringup --board-init-stage 1
  ```

  Use stages `0` through `14`: status only, `M5.begin()`, IO expander/LED,
  servo UART, servo position read, touch sensor, IMU probe, power monitor,
  LTR553 proximity/light, NFC unit, IR receiver, audio probes, camera init,
  calibration plus servo health, and neutral face/display. Record the first stage that loses
  `/stackchan/default/device/status`, then restore normal firmware.
- Before rebuilding or uploading firmware during repeated smoke work, inspect
  the local PlatformIO state:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py plan --port COM3
  ```

  If `build_required: false` and `upload_status: current`, firmware sources,
  selected diagnostic build flags, and the last successful upload marker match
  the selected port. In that case, skip upload and continue with ROS smoke.
  If either value indicates work is needed, use the repository PlatformIO helper
  rather than direct flashing tools.
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
  uv run --no-project python scripts/microros_agent_container.py build-image
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
  uv run --no-project python scripts/microros_agent_container.py build-image
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

- For TTS-backed speech, confirm
  `stackchanctl --backend bridge say --voice default "テスト終わったよ" --json`
  synthesizes through the local provider, routes audio through the firmware
  playback action, and returns only metadata such as `text_length`,
  `voice_profile`, `device_id`, `command_id`, and structured result state.
  Public events may include `tts_started`, `tts_finished`, or `tts_failed` with
  bounded metadata only. They must not include speech text, provider request
  bodies, raw provider speaker IDs, PCM bytes, or transcript text.
- 2026-05-25 KOIZUMI-138 local VOICEVOX smoke reached the firmware-owned
  `PlayAudio` goal but did not complete audible TTS playback. The bridge
  synthesized local VOICEVOX output, normalized it to 16 kHz mono PCM, exposed
  only `text_length` and `voice_profile`, and emitted `tts_started`. The
  connected COM3 hardware reported `audio_playback` available. Remaining
  failure modes were firmware `NextAudioChunk` `pull_response_timeout` at
  sequence `0` with 640 byte chunks, and topic sequence gaps ending in
  `AUDIO_UNDERRUN` with 128 byte chunks. See `tmp/tts_bridge_smoke_10.log` and
  `tmp/tts_bridge_smoke_12.log` from that run, and track the transport fix in
  KOIZUMI-140 before marking KOIZUMI-138 complete.
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

  For a focused sensor/event rerun where audio and camera behavior is not under
  test, add `--skip-media-smoke` to avoid spending the sweep budget on unrelated
  media commands.

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

  While the stimulus window is open, the runner also captures live device-side
  samples from `/stackchan/default/device/touch/state`,
  `/stackchan/default/device/proximity/raw`,
  `/stackchan/default/device/light/raw`,
  `/stackchan/default/device/power/status`, and
  `/stackchan/default/device/events`. Use
  `STACKCHAN_SENSOR_SWEEP_LIVE_TOUCH_ACTIVE_SEEN`,
  `STACKCHAN_SENSOR_SWEEP_LIVE_PROXIMITY_NONZERO_SEEN`,
  `STACKCHAN_SENSOR_SWEEP_LIVE_LIGHT_NONZERO_SEEN`,
  `STACKCHAN_SENSOR_SWEEP_LIVE_POWER_SAMPLE_SEEN`, and
  `STACKCHAN_SENSOR_SWEEP_LIVE_EVENT_SAMPLE_SEEN` to distinguish "no event
  emitted" from "raw input never changed during the stimulus window".

  The runner emits
  `STACKCHAN_EVENT_STIMULUS_{BUTTON,IMU,TOUCH,PROXIMITY,LIGHT,POWER,NFC,IR}_STATUS=PASS`
  when a matching event is observed, `UNAVAILABLE` when a stimulus window ran
  but the current firmware/hardware did not publish that event family, and
  `NOT_RUN` when the sweep intentionally used `--stimulus-window-seconds 0`.
  Keep `UNAVAILABLE` as a recorded fixture result until the corresponding
  firmware adapter or physical stimulus path exists; do not count `NOT_RUN` as a
  failed physical stimulus.
- If touch, proximity, or light raw telemetry remains fixed at zero, stop the
  micro-ROS Agent and flash the firmware-only sensor diagnostic profile:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --sensor-input-diagnostics
  uv run --no-project python scripts/firmware_platformio.py monitor --port COM3 --baud 921600
  ```

  During manual touch, near/far, and light/dark stimuli, inspect the bounded
  `sensor_input_diag_stage` boot markers and then the `sensor_input_diag`
  fields: `touch_zone_mask`, `touch_i0..touch_i2`, `ltr553_part_ok`,
  `ltr553_manufacturer_ok`, `ps_read_ok`, `ps_raw`, `als_read_ok`, `als_raw`,
  `power_voltage_v`, and `in_i2c_released_for_camera`. The profile keeps the
  normal runtime serial baud, currently 921600 bps. The `--upload-speed 115200`
  examples are flashing-only settings and do not change the firmware runtime
  transport. The diagnostic waits briefly at `pre_m5_begin`; open the monitor
  immediately after upload so missing text can be separated from a later
  hardware-init hang. This diagnostic profile is local firmware
  maintenance only; do not run it with the Agent attached to the same USB
  serial transport, and restore a normal firmware build before standard ROS 2
  validation.
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

2026-05-23 MTU/QoS media follow-up, device `default`, COM3 through the Windows
serial TCP bridge, after moving `UCLIENT_CUSTOM_TRANSPORT_MTU=1024` to the
`microxrcedds_client` meta package and matching stackchanctl audio chunk QoS to
the firmware best-effort volatile topic:

```powershell
uv run --no-project python scripts/firmware_container.py build
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 20 --stimulus-window-seconds 0
```

Observed results:

- Firmware build and upload: pass. The generated micro-ROS client config now
  sets `UXR_CONFIG_CUSTOM_TRANSPORT_MTU` to `1024`; `SERIAL_TRANSPORT_MTU`
  remains `512`.
- Transport warning regression check: pass. The prior Agent warning
  `Trying to serialize 720 in 508 MTU stream` did not recur in this sweep.
- Low-rate telemetry, raw IMU relay, `power status`, and normal redaction:
  pass. Touch, proximity, light, power, device/public IMU, event redaction, and
  log redaction markers remained green.
- Audio playback: still not complete. `stackchanctl audio play prompt.wav`
  reached the firmware-owned action and returned structured `AUDIO_UNDERRUN`
  instead of missing local payload or unsupported transport.
- Audio capture: still not complete. The sweep observed bounded
  `audio_capture_started` but the command timed out before a terminal result or
  usable WAV output.
- Camera capture: still not complete. The public camera capture command timed
  out while waiting for the firmware-owned capture action to complete. JPEG
  bytes/base64 were still absent from normal output and logs.
- Manual button/touch/proximity/power/NFC/IR stimulus checks were not performed
  in this no-stimulus sweep. IMU and light semantic event markers were observed.

2026-05-23 bridge media-timeout follow-up, device `default`, same firmware and
serial bridge, after rebuilding `stackchan_bridge` with media actions using a
longer result timeout than short synchronous device commands:

- Container ROS build: pass for `stackchan_msgs` and `stackchan_bridge`.
- Low-rate telemetry, raw IMU relay, `power status`, and redaction: pass.
- Audio playback: unchanged structured `AUDIO_UNDERRUN`.
- Audio capture: still `TIMEOUT` after bounded `audio_capture_started`; this
  points at firmware capture chunk/terminal-result behavior rather than only
  the former 2 second bridge command timeout.

Implementation follow-up:

- Playback chunk publishing is now paced at the baseline 20 ms chunk interval
  after a short subscriber-discovery wait and firmware-session arm delay to
  reduce best-effort drops during short prompts. Firmware now allows a longer
  initial no-chunk window for the bridge-to-device action handoff. This is a
  bring-up workaround; a later fix should let bridge-owned device-goal
  acceptance trigger playback chunks directly.
- Firmware microphone capture now bounds each recording chunk with a device-side
  timeout and returns structured `AUDIO_CAPTURE_FAILED` if the chunk never
  completes. Capture is back on the baseline 20 ms chunk size because the real
  serial path reported `MIC_OVERRUN` when trying max-size 40 ms chunks.
- The media smoke now uses a one-chunk 0.02 s capture, one-chunk prompt, and
  quality 50 JPEG by
  default. This keeps the hardware smoke focused on proving the ROS path before
  longer audio captures or high-quality camera payloads become their own
  follow-up validations.
- Camera snapshot now requests QVGA JPEG directly from the camera driver and
  maps action quality onto the driver quality range before capture, with RGB565
  capture plus firmware JPEG encode retained as a fallback if driver-native
  JPEG init is unavailable. The next hardware sweep should show either a JPEG
  result or a structured camera failure instead of an unclassified action
  timeout.
- Camera capture: still `TIMEOUT`; inspect firmware camera acquisition and
  result delivery next.

2026-05-23 one-chunk media smoke after firmware loop arbitration and action
timing updates, device `default`, COM3 through host serial TCP bridge:

- PlatformIO build and upload passed through `scripts/firmware_platformio.py`.
- Low-rate touch, IMU, proximity, light, and power samples appeared on device
  and public relay topics; `power status` returned `ok=true`.
- Audio capture one-chunk smoke passed: `stackchanctl audio capture --seconds
  0.02 --json` returned `ok=true`, and events included matching
  `audio_capture_started` and `audio_capture_finished`.
- Audio playback still returned structured `AUDIO_UNDERRUN` even with a
  conservative fixed arm delay and longer firmware no-chunk window. Treat this
  as evidence that playback chunks should be routed by the bridge after
  device-goal acceptance instead of timed from the CLI.
- Follow-up implementation changes the playback payload ingress to
  `/stackchan/default/cmd/audio/chunks`; the bridge buffers these chunks and
  initially relayed them to `/stackchan/default/device/audio/chunks` only after
  firmware accepts `/stackchan/default/device/audio/play`. Later retry smoke
  narrowed the remaining issue to firmware chunk callback delivery, so playback
  input is being split to `/stackchan/default/device/audio/playback/chunks`.
  Re-run the media smoke before marking playback complete.
- Camera capture still returned `TIMEOUT`. Firmware now prefers native JPEG and
  the loop order keeps audio ahead of camera, but camera acquisition/result
  delivery still needs a focused nonblocking or bounded-driver follow-up.
- Follow-up bridge handling maps accepted device camera goals that miss the
  media-action result deadline to `CAMERA_CAPTURE_FAILED`, so the next smoke
  should show either `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=1` or a
  bounded camera failure instead of an unclassified CLI `TIMEOUT`.
- Redaction remained green: no audio PCM, speech text, JPEG bytes/base64, NFC
  tag IDs, or IR raw-code markers appeared in normal output/log scans.

2026-05-23 bridge relay/result-classification smoke, device `default`, COM3
through host serial TCP bridge, after rebuilding `stackchan_bridge` in the
container with playback command-ingress relay and camera timeout
classification:

```powershell
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 30 --stimulus-window-seconds 0 --media-audio-capture-seconds 0.02 --media-camera-quality 50
```

- ROS graph included both `/stackchan/default/cmd/audio/chunks` and
  `/stackchan/default/device/audio/chunks`.
- Audio playback still returned structured `AUDIO_UNDERRUN`:
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_UNSUPPORTED_SEEN=0` and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_OK_SEEN=0`. The next implementation
  needs payload-free diagnostics on the bridge relay and firmware playback
  consumer to determine whether the first PLAYBACK chunk reaches the active
  `command_id`.
- Follow-up implementation adds payload-free playback relay diagnostics on the
  bridge and firmware. The next connected smoke should inspect
  `audio playback relay buffered/activated/published/finished` bridge logs and
  firmware `stackchan audio_playback_diag` serial lines to classify the
  remaining `AUDIO_UNDERRUN` as relay timing, firmware chunk rejection,
  `playRaw` failure, or device-side no-chunk timeout.
- Audio capture one-chunk smoke still passed:
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OK_SEEN=1` and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_MIC_OVERRUN_SEEN=0`.
- Camera capture no longer surfaced an unclassified CLI `TIMEOUT`; it returned
  bounded `CAMERA_CAPTURE_FAILED` with message `firmware camera capture action
  for 'default' timed out`.
- Low-rate touch, IMU, proximity, light, and power samples appeared on device
  and public relay topics; `power status` returned `ok=true`.
- No manual stimulus window was run. Passive IMU, light, and IR events were
  observed, but button/touch/proximity/power/NFC manual-stimulus statuses remain
  `NOT_RUN`.
- Redaction remained green:
  `STACKCHAN_SENSOR_SWEEP_EVENTS_SENSITIVE_PAYLOAD_SEEN=0` and
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0`.

2026-05-23 playback relay diagnostic smoke after uploading `eb1cd21` diagnostic
firmware to COM3. The first upload attempt at the default high-speed stub path
failed with `No serial data received`; retrying through the repository
PlatformIO helper with `--upload-speed 115200 --no-stub` succeeded.

```powershell
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 30 --stimulus-window-seconds 0 --media-audio-capture-seconds 0.02 --media-camera-quality 50
```

- Audio playback still returned structured `AUDIO_UNDERRUN`:
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_UNSUPPORTED_SEEN=0` and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_OK_SEEN=0`.
- Bridge relay diagnostics show the first chunk was not lost in the bridge:
  `buffered=1`, `received=1`, `published=1`, `dropped=0`, `pending=0`, with
  `sequence=0`, `bytes=640`, `format=1`, `sample_rate=16000`, and
  `channels=1`.
- Relay activation to finish took about 6.2 seconds, matching firmware
  `kAudioPlaybackNoChunkTimeoutMs = 6000`. The remaining failure is therefore
  narrowed to firmware playback consumer delivery or arming on
  `/stackchan/default/device/audio/chunks`, not bridge command-ingress timing or
  speaker `playRaw` failure.
- Audio capture passed: `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OK_SEEN=1` and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_MIC_OVERRUN_SEEN=0`.
- Camera capture passed: `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=1`.
- Event/log redaction remained green:
  `STACKCHAN_SENSOR_SWEEP_EVENTS_SENSITIVE_PAYLOAD_SEEN=0` and
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0`.

2026-05-23 bounded first-chunk retry smoke after uploading the retry/duplicate
diagnostic firmware to COM3 with the same low-speed no-stub PlatformIO helper
path:

```powershell
uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 30 --stimulus-window-seconds 0 --media-audio-capture-seconds 0.02 --media-camera-quality 50
```

- Audio playback still returned structured `AUDIO_UNDERRUN`:
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_UNSUPPORTED_SEEN=0` and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_OK_SEEN=0`.
- Bridge relay diagnostics show the first chunk was published three times with
  no bridge drops: `received=1`, `buffered=1`, `published=3`, `dropped=0`, and
  `pending=0`.
- Firmware-visible `chunk_accepted` or `chunk_duplicate_ignored` diagnostics
  were not observed in the smoke logs. Retry therefore did not prove delivery to
  the firmware chunk callback.
- Audio capture passed: `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OK_SEEN=1` and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_MIC_OVERRUN_SEEN=0`.
- Camera capture passed: `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=1`.
- Event/log redaction remained green:
  `STACKCHAN_SENSOR_SWEEP_EVENTS_SENSITIVE_PAYLOAD_SEEN=0` and
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0`. Device/public event
  topic sampling timed out in this run, but `stackchanctl events list` returned
  cleanly.
- Follow-up implementation separates playback chunk input onto
  `/stackchan/default/device/audio/playback/chunks` while leaving capture output
  on `/stackchan/default/device/audio/chunks`, avoiding firmware same-topic
  publish/subscribe on the micro-ROS serial path. Re-run this smoke before
  marking playback complete.

2026-05-23 playback split-topic and subscription-match smokes:

- Split-topic firmware was uploaded successfully through the same no-stub
  PlatformIO helper path. ROS graph included
  `/stackchan/default/device/audio/playback/chunks`.
- With split-topic best-effort QoS, audio playback still returned
  `AUDIO_UNDERRUN`. The bridge observed `subscriptions=1` before publishing and
  still finished with `received=1`, `buffered=1`, `published=3`, `dropped=0`,
  and `pending=0`.
- Audio capture and camera capture remained healthy in the split-topic
  best-effort smoke:
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OK_SEEN=1`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_MIC_OVERRUN_SEEN=0`, and
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=1`.
- A follow-up attempt making only playback input reliable was uploaded and
  tested, but it regressed media actions to `TIMEOUT` for playback, capture, and
  camera. Do not keep that QoS direction; use best-effort split-topic as the
  safer baseline.
- The remaining playback failure is no longer explained by bridge buffering,
  action-goal acceptance timing, topic matching, or firmware same-topic
  publish/subscribe. Next implementation should avoid relying on a separate
  PC-to-firmware chunk topic for the first payload, for example by explicitly
  designing a small first-chunk handoff in the playback action contract or a
  firmware-owned pull/ack path.

2026-05-23/24 first-goal payload handoff smoke:

- The additive `PlayAudio` action fields for a bounded first playback payload
  were implemented across IDL, bridge, `stackchanctl`, and firmware, and the
  firmware uploaded successfully through the PlatformIO helper.
- With the first playback segment in the action goal, both the initial 20 ms
  payload and a reduced 10 ms / 320 byte payload caused the physical smoke to
  time out waiting for the firmware audio playback action result. After that
  playback timeout, audio capture and camera capture also timed out in the same
  smoke run even though sensor topics, power status, and event redaction still
  sampled successfully.
- Because this shifted the known failure from structured `AUDIO_UNDERRUN` to
  action `TIMEOUT`, the first-goal payload path remains a local diagnostic
  opt-in instead of the CLI baseline. The default playback path keeps all PCM
  chunks on `/stackchan/default/cmd/audio/chunks` and
  `/stackchan/default/device/audio/playback/chunks`.
- Next work should instrument the firmware action result path and micro-ROS
  action resource limits before making any action-goal payload handoff
  production behavior.

KOIZUMI-112 diagnostic firmware update:

- The next diagnostic build adds payload-free `audio_playback_action` firmware
  events, plus optional `stackchan audio_playback_action` serial lines when
  serial diagnostics are explicitly enabled, around playback goal request, goal
  response, first-goal chunk dispatch, result readiness, result request, and
  result response send. These diagnostics intentionally include only command id,
  accepted flag, first-chunk byte count, and action/session booleans.
- Use this build to decide whether the first-goal payload timeout occurs before
  firmware sees the goal, before first chunk dispatch, after result readiness,
  or while the result response is being requested/sent.

2026-05-23/24 KOIZUMI-112 first-goal event diagnostic smoke:

- Uploaded the event-diagnostic firmware through
  `scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200
  --no-stub`.
- Ran same-container Agent/bridge/sensor sweep with
  `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=320` and `--timeout 30`.
- Playback still returned firmware action `TIMEOUT`; audio capture and camera
  capture also timed out afterward. Touch, IMU, proximity, light, and power
  topics sampled, power status completed, and redaction stayed green.
- `stackchanctl events list` returned firmware events such as `firmware_ready`,
  `dark_detected`, `picked_up`, and `tilted`, but no `audio_playback_action`
  event. Because the new diagnostic event is emitted immediately after
  `rcl_action_take_goal_request()` succeeds, this points to the firmware not
  taking the playback goal request when the action goal contains the 320 byte
  first payload, rather than a later result-response stall.
- The same event diagnostic firmware with
  `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=0` reached
  `audio_playback_action` stages `goal_request_taken`, `goal_response_sent`,
  `goal_execute`, `result_request_taken`, `result_ready`, and
  `result_response_sent`. That run returned structured `AUDIO_UNDERRUN`, while
  audio capture and camera capture stayed OK. This confirms the topic-only
  baseline reaches firmware action handling and result delivery, while the
  320 byte first-goal payload prevents the playback goal request from being
  taken by firmware.

2026-05-24 KOIZUMI-113 pull/ack playback smoke:

- Implemented the bridge-owned pull helper
  `/stackchan/default/audio/playback/next_chunk` and firmware client-side pull
  path, then built ROS packages and both firmware profiles successfully.
- Uploaded the play-audio bring-up profile through the PlatformIO helper:
  `uv run --no-project python scripts/firmware_platformio.py upload --port COM3
  --upload-speed 115200 --no-stub --microros-core-play-audio-bringup`.
- With a host serial TCP bridge on COM3 and the same-container
  `tcp-pty-sensor-sweep`, the micro-ROS Agent connected to firmware and device
  topics sampled for touch, IMU, proximity, light, and power. The graph also
  exposed `/stackchan/default/audio/playback/next_chunk`.
- The same-container smoke could not validate bridge/CLI playback because the
  `microros/micro-ros-agent:jazzy` image combines a 2025-era ROS runtime with
  newer apt-installed ROS Python/type-support packages. `stackchan_bridge_node`
  and `stackchanctl` failed with a Fast-CDR symbol mismatch before commands
  reached the bridge.
- A split-container diagnostic kept the Agent in
  `microros/micro-ros-agent:jazzy` and ran bridge/CLI in
  `codex-stackchan-ros2:jazzy`. This avoided the ABI crash and showed firmware
  graph resources, but Docker Desktop did not deliver DDS samples such as
  `/stackchan/default/device/status` to the ROS 2 container. The bridge therefore
  reported `TRANSPORT_DISCONNECTED`, so face and audio commands were rejected
  before firmware command execution.
- Re-uploaded the default firmware profile through the same PlatformIO helper
  and repeated the split-container diagnostic. The graph exposed default
  firmware topics/services, but `/stackchan/default/device/status` and touch
  samples still did not arrive across containers, matching the known Docker
  Desktop cross-container DDS caveat.
- KOIZUMI-113 is therefore implementation-complete and hardware-connected at
  the Agent/topic discovery level, but not playback-complete. The next physical
  risk is a dedicated, reproducible same-container Agent/bridge smoke image or
  host-side ROS environment that keeps micro-ROS Agent and Python bridge
  dependencies ABI-aligned.

2026-05-24 KOIZUMI-114 ABI-aligned Agent image smoke:

- Added and built the repository Agent image with:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py build-image
  ```

  The image builds micro-ROS Agent from source with `micro_ros_setup` on top of
  `ros:jazzy-ros-base`, so the Agent, `rclpy`, and generated type support use
  the same ROS 2 Jazzy dependency set.
- With COM3 exposed through the host serial TCP bridge, same-container
  `tcp-pty-bridge-smoke --face-check happy` passed. The smoke observed
  `/stackchan/default/status` with `connected: true`, `firmware_version:
  bringup`, sent `stackchanctl --backend bridge face happy --json`, and a
  follow-up observe reported `face: happy`. `stackchanctl events list` also
  saw `firmware_ready`.
- This resolves the Fast-CDR symbol mismatch that blocked the previous
  same-container smoke, and also avoids Docker Desktop cross-container DDS
  sample loss for bridge/CLI validation.
- Running `tcp-pty-sensor-sweep --skip-build` with the new image reached the
  bridge and firmware media path. The bridge logged
  `audio playback pull served first chunk` for sequence 0 with 640 bytes, so
  `/stackchan/default/audio/playback/next_chunk` is callable from firmware.
- Audio playback still returned structured `AUDIO_UNDERRUN`. Firmware
  `audio_playback_action` events reached `goal_request_taken`,
  `goal_response_sent`, `goal_execute`, `result_request_taken`,
  `result_ready`, and `result_response_sent`, but the result remained
  underrun. This narrows the remaining playback fault to the firmware side
  after the first pull response is served, rather than Agent/bridge ABI,
  bridge buffering, or service discovery.
- Audio capture and camera capture timed out after the playback underrun in
  this run. IMU, proximity, light, power telemetry, power status, event listing,
  and redaction checks stayed healthy.

### 2026-05-24 KOIZUMI-115 playback pull response timeout diagnosis

- Added payload-free firmware `audio_playback_chunk` diagnostics and allowed
  media bring-up profiles to publish firmware events instead of dropping them
  as the pure raw-telemetry profile does.
- Firmware contract and build checks passed:

  ```powershell
  uv run --no-project python -m unittest firmware.m5stackchan-microros.tests.test_firmware_contract
  uv run --no-project python scripts/firmware_platformio.py build --microros-core-play-audio-bringup
  ```

- Upload through the repository PlatformIO helper succeeded only with the
  stable low-speed no-stub path:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --microros-core-play-audio-bringup --upload-speed 115200 --no-stub
  ```

  The same upload at the default 921600 bps and at 460800 bps with the esptool
  stub reached the ESP32-S3 and then failed after changing baud with
  `No serial data received`.
- Same-container smoke was run with COM3 exposed through the host serial TCP
  bridge:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 35 --stimulus-window-seconds 0 --media-audio-capture-seconds 0.02 --media-camera-quality 50
  ```

- The bridge again served the first pull chunk:

  ```text
  audio playback pull served first chunk ... bytes=640 buffered=0
  ```

- Firmware events now show the remaining failure is before speaker enqueue:
  `audio_playback_chunk` alternates between `pull_requested` and
  `pull_response_timeout`; counters remain `seen=0`, `ok=0`, `rej=0`,
  `next=0`. No `chunk_accepted`, `chunk_rejected`, `play_raw_failed`, or
  `pull_response_rejected` event appears.
- Therefore the current `AUDIO_UNDERRUN` is not a speaker `playRaw` failure or
  chunk validation rejection. The firmware micro-ROS `NextAudioChunk` client
  response callback is not receiving the accepted bridge response before the
  firmware timeout. Follow-up fix is tracked in KOIZUMI-116.
- This diagnostic profile intentionally does not enable audio capture or camera
  capture, so those commands correctly return `UNSUPPORTED_FEATURE` in this
  run. IMU, touch, proximity, light, power telemetry, event listing, and
  redaction checks still produced valid observations.

### 2026-05-24 KOIZUMI-116 small playback payload diagnosis

- Reused the KOIZUMI-115 play-audio bring-up firmware and same-container
  Agent/bridge smoke flow with COM3 exposed through the host serial TCP bridge.
- With `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=320`, `audio play` timed out
  before firmware emitted `audio_playback_action` diagnostics. This matches the
  earlier KOIZUMI-112 evidence that a 320 byte first-goal payload can prevent
  firmware from taking the action goal request.
- With `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=64`, firmware emitted
  `audio_playback_action` stages `goal_request_taken`, `goal_response_sent`,
  `goal_execute`, and `first_goal_chunk_dispatch`, followed by
  `audio_playback_chunk` stage `chunk_accepted` for sequence 0 with 64 bytes.
  This proves a small PC-to-firmware playback payload can cross the serial
  micro-ROS path and be accepted by the speaker adapter.
- The same run then timed out on the next pulled chunk, where the remaining
  bridge response was still 576 bytes. This narrows KOIZUMI-116 to a bounded
  payload-size issue on the serial micro-ROS playback transport rather than a
  generic action, service, or speaker enqueue failure.
- Follow-up validation should set both
  `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=64` and
  `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES=64` so the remaining topic/pull chunks
  are split to the same proven payload size.
- That follow-up smoke completed with `audio play` returning `ACCEPTED`.
  Firmware accepted sequence 0 from the first-goal payload, and the bridge
  buffered and published nine 64 byte remaining chunks with no bridge drops.
  Firmware then marked the playback action `result_ready` before sequence 1
  was accepted, and the next 64 byte chunk arrived as
  `chunk_without_active_goal`. The remaining blocker is therefore firmware
  playback session lifetime/result timing after the first accepted chunk, not
  the bridge's ability to split and publish small transport chunks.
- After fixing firmware to wait for end-of-stream before successful
  completion, the same 64 byte smoke accepted all playback chunks through
  sequence 9. It then timed out at the CLI because the bridge did not expose
  `end_of_stream=true` until its device action client timed out and closed the
  relay. KOIZUMI-118 tracks the bridge-side idle-input end-of-stream fix.
- After adding bridge idle-input end-of-stream and increasing the bridge media
  action timeout default to 35 seconds, a rebuild-backed same-container smoke
  with `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=64` and
  `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES=64` returned `stackchanctl audio play`
  `ok=true`, `result_state=ACCEPTED`. Firmware events showed sequence 0
  accepted from the first-goal payload, all remaining chunks accepted through
  sequence 9, `pull_end_of_stream` at sequence 10, `result_ready`, and
  `result_response_sent`. The bridge logged
  `audio playback pull closed idle input` before `audio playback relay
  finished` with `received=9`, `published=9`, `dropped=0`, and `pending=0`.
  Audio capture and camera capture remain `UNSUPPORTED_FEATURE` for this
  play-audio bring-up firmware profile.

### 2026-05-24 KOIZUMI-127 sensor diagnostic serial text isolation

- `--sensor-input-diagnostics` now keeps the same runtime serial baud as the
  normal firmware and no longer adds USB CDC build flags. `--upload-speed
  115200 --no-stub` was used only as the stable flashing path.
- Firmware contract tests passed:

  ```powershell
  uv run --no-project python -m unittest discover -s firmware/m5stackchan-microros/tests
  ```

- Diagnostic firmware built and uploaded on COM3 with:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --sensor-input-diagnostics
  ```

- A 20 second PlatformIO monitor capture at 921600 bps still showed only the
  PlatformIO monitor header and no `sensor_input_diag_stage` or
  `sensor_input_diag` firmware text. This means the remaining blocker is not a
  runtime baud change; it is the mismatch between the proven micro-ROS serial
  transport and the standalone `Serial.print` diagnostic path.
- Normal firmware was restored immediately after the diagnostic run:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub
  uv run --no-project python scripts/firmware_platformio.py plan --json --port COM3
  ```

  The plan reported `upload_status: current`.

### 2026-05-25 KOIZUMI-128 COM3 application serial zero-byte isolation

- Rechecked the normal firmware path after the 2026-05-24 baud clarification.
  Uploading the normal firmware to COM3 with the stable flashing path succeeded:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub
  ```

- A same-container sensor sweep over the host serial TCP bridge completed but
  reported `connected: false`; all touch, IMU, proximity, light, power, and
  event topic probes timed out with `SAMPLE_SEEN=0`.
- The host serial TCP bridge connected to the container `socat` peer, but its
  byte counters stayed at `serial_to_tcp=0 tcp_to_serial=0` throughout the
  Agent run. The micro-ROS Agent log showed startup only and no client session
  traffic.
- To isolate optional firmware initialization, the `--microros-minimal-bringup`
  profile was uploaded successfully and checked with:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-event-echo --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 6 --timeout 30
  ```

  The echo timed out, and the serial TCP bridge again reported
  `serial_to_tcp=0 tcp_to_serial=0`.
- This narrows the current blocker below K151 sensors and below normal firmware
  optional entities: COM3 still works for PlatformIO/esptool flashing, but the
  application runtime serial path is not producing observable XRCE or text
  bytes on COM3. KOIZUMI-128 tracks that transport-level isolation.
- Follow-up implementation changed `scripts/serial_tcp_bridge.py` so DTR and
  RTS are explicitly inactive before the COM port is opened. This prevents the
  host bridge from accidentally holding ESP32-S3 auto-reset or boot lines while
  the Agent is waiting for application runtime serial traffic.
- A local pyserial read-only check still saw zero bytes for DTR/RTS inactive,
  DTR active/RTS inactive, and both active. RTS active/DTR inactive returned
  `ClearCommError failed`, so the default runtime bridge should keep both
  control lines inactive. Windows port enumeration showed COM3 as
  `USB VID:PID=303A:1001 SER=44:1B:F6:E2:94:50`, matching the CoreS3 USB CDC
  runtime identity.
- Normal firmware was restored after the minimal profile, and
  `uv run --no-project python scripts/firmware_platformio.py plan --json --port
  COM3` reported `upload_status: current`.
- Follow-up firmware changes made `--microros-minimal-bringup` skip board
  hardware adapters before the Agent connection loop. Re-run this profile after
  building to distinguish a pure USB CDC/XRCE transport problem from a block or
  crash in M5/BSP, servo, sensor, audio, or camera initialization.
- With that true minimal profile on COM3, a direct ROS 2 echo of
  `/stackchan/default/device/status` succeeded through the host serial TCP
  bridge and same-container micro-ROS Agent. The sample reported
  `connected: true`, `state: ready`, `firmware_version: bringup`, and the Agent
  log showed status topic publisher/datawriter creation. This proves the
  Windows COM3 USB CDC path, serial TCP bridge, container Agent, and status
  publisher can work when board hardware adapters are skipped.
- Normal firmware was restored again after the true minimal status check, and
  `uv run --no-project python scripts/firmware_platformio.py plan --json --port
  COM3` reported `upload_status: current` with no diagnostic build flags.

### 2026-05-25 KOIZUMI-129 board-init staged status isolation

- Added `--microros-board-init-bringup --board-init-stage N` so board hardware
  initialization can be reintroduced before the same status-only micro-ROS loop.
  The stage map now separates touch, IMU, power, LTR553, NFC, IR, audio probes,
  and camera init instead of treating all sensor adapters as one opaque step.
- Stages `1` through `4` passed on COM3: `M5.begin()`, IO expander/LED, servo
  UART, and servo position read all preserved
  `/stackchan/default/device/status`.
- The original combined sensor stage stopped before the Agent saw any serial
  bytes. After splitting sensor stages, touch, IMU, and power passed, while the
  first LTR553 stage reproduced the zero-byte transport symptom.
- LTR553 register access was changed from direct `Wire` calls to the managed
  `M5.In_I2C` path, matching the earlier UnitNFC bring-up lesson that direct
  `Wire.begin(...)` style handling can regress micro-ROS Agent bring-up.
- After the LTR553 fix, stages `8` through `14` passed: LTR553, NFC, IR, audio
  probes, camera init, calibration plus servo health, and neutral face/display.
- Normal firmware was restored and confirmed current:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub
  uv run --no-project python scripts/firmware_platformio.py plan --json --port COM3
  ```

  The plan reported `upload_status: current` with no diagnostic build flags.
- A normal-firmware direct status echo through the host serial TCP bridge and
  same-container micro-ROS Agent reported `connected: true`, `state: ready`,
  and available `face`, `motion`, `led`, `audio_playback`, `audio_capture`, and
  `camera_snapshot` capabilities.
- A bridge-routed face smoke also passed:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 15 --face-check happy
  ```

  `stackchanctl face happy` returned `ok=true`, `result_state=ACCEPTED`, and
  the follow-up observe reported `connected: true` and `face: happy`.

### 2026-05-25 KOIZUMI-138/140 local TTS playback transport follow-up

- Added bridge-owned VOICEVOX transport tuning parameters for local `say`
  smokes: `tts_speed_scale`, `tts_pre_phoneme_length`,
  `tts_post_phoneme_length`, `tts_silence_trim_threshold`, and
  `tts_silence_trim_margin_ms`. The Docker helper passes matching
  `STACKCHAN_TTS_*` environment variables when `--say-check` is used.
- Added synthesized-audio silence trimming after WAV normalization. Direct
  local provider diagnostics against the operator-owned VOICEVOX service
  showed the short smoke utterance fell from 19796 PCM bytes to 4778 bytes
  with `speed_scale=3.0`, zero pre/post phoneme length, and threshold 512.
- Added a first-goal PCM path for TTS playback and made synthesized playback
  pull-only. This prevents the bridge from publishing remaining chunks on the
  topic faster than firmware can request them through
  `/stackchan/default/audio/playback/next_chunk`.
- Same-container smoke over COM3 with
  `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=64`,
  `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES=64`, and the TTS tuning above
  completed the `say` command and observed `tts_finished`. The bridge logged
  pull-only activation with `received=74`, then finished with `pending=0`.
  The overall smoke returned non-zero only because the active firmware profile
  did not emit `firmware_ready` during that run.
- An immediate repeat before the device had fully settled timed out with the
  previous `FIRMWARE_BUSY` state still visible in status, and a 128 byte
  follow-up run hit `TRANSPORT_DISCONNECTED` before audio chunk validation.
  Keep 128 byte and larger playback service responses tracked as follow-up
  risk; 320 byte service responses had already failed to advance beyond the
  next-chunk pull path.

### 2026-05-26 KOIZUMI-141 TTS chunk-size and recovery follow-up

- Rebuilt and uploaded the normal firmware to COM3 through the repository
  PlatformIO helper with `--upload-speed 115200 --no-stub`. The upload
  completed and hard-reset the board through the PlatformIO path.
- A build-backed same-container bridge smoke after upload confirmed the normal
  status path: `STACKCHAN_BRIDGE_STATUS_CONNECTED=1`,
  `STACKCHAN_BRIDGE_FIRMWARE_READY_SEEN=1`, and `firmware_version: bringup`.
- `scripts/microros_agent_container.py tcp-pty-bridge-smoke` now scales the
  public status wait loop with `--timeout` instead of always using 12 attempts.
  This prevents long TTS smokes from sending `say` before a slow Agent/session
  startup has had a fair chance to publish `/stackchan/default/status`.
- With a fresh PlatformIO reset and
  `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=64`,
  `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES=96`, and the documented VOICEVOX TTS
  tuning, the TTS smoke reached `STACKCHAN_BRIDGE_SAY_COMPLETED=1` and
  `STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=1`. The bridge logged pull-only
  activation with `received=50` and finish with `pending=0`.
- The 96 byte run emitted late `pull_response_without_active_goal` events after
  result completion, but the action result and `tts_finished` event were
  complete. Treat 96 bytes as the current fastest validated TTS playback chunk
  size for this hardware path; keep 64 bytes as the conservative fallback.
- With another fresh PlatformIO reset and
  `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES=128`, status connected in two attempts
  and `firmware_ready` was observed, but `stackchanctl say` timed out. The
  bridge buffered sequence 1 with 128 bytes, but the playback relay never
  activated before the action timeout. Treat 128 byte service responses as too
  large or too slow for the current serial micro-ROS playback path.
- A separate recovery issue remains: after one successful Agent session, later
  same-container Agent starts can fail to establish an XRCE session even though
  the host serial TCP bridge reports bytes in both directions. Restarting the
  host serial TCP bridge alone did not recover it; a PlatformIO upload/hard
  reset did. Track this as a reconnect/recovery blocker instead of a TTS chunk
  size result.

### 2026-05-26 KOIZUMI-142 serial Agent reconnect recovery

- Reproduced the stale reconnect shape where COM3 still had bidirectional byte
  traffic, but repeated same-container Agent starts did not publish bridge
  status or observe `firmware_ready`.
- A manual pyserial RTS pulse recovered the session without a PlatformIO upload
  or firmware rebuild. The next status smoke reported
  `STACKCHAN_BRIDGE_STATUS_CONNECTED=1`,
  `STACKCHAN_BRIDGE_FIRMWARE_READY_SEEN=1`, Agent `session established`, and
  `firmware_version: bringup`.
- `scripts/serial_tcp_bridge.py` now supports `--reset-pulse rts` so the host
  serial bridge can apply the same short RTS pulse immediately after opening
  COM3, then return RTS inactive before listening for the Agent TCP client.
- Validated the integrated recovery path with:

  ```powershell
  uv run --no-project --with pyserial python scripts/serial_tcp_bridge.py --serial-port COM3 --baud 921600 --host 0.0.0.0 --tcp-port 11411 --reset-pulse rts
  ```

  followed by `tcp-pty-bridge-smoke --skip-build`; the smoke exited 0 with
  `STACKCHAN_BRIDGE_STATUS_CONNECTED=1`,
  `STACKCHAN_BRIDGE_FIRMWARE_READY_SEEN=1`, and Agent `session established`.
- Do not run the reset pulse while another Agent, monitor, or bridge process
  owns COM3. Stop the existing host bridge first and confirm no non-shell
  `serial_tcp_bridge.py` process remains. Keep plain inactive DTR/RTS as the
  default for already healthy sessions.

## Cleanup

- Save the command transcript and observed result codes in the PR or Linear
  issue.
- Reset temporary maintenance/debug firmware changes before merging production
  code.
