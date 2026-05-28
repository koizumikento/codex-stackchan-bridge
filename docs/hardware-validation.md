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
  $env:STACKCHAN_TTS_SPEED_SCALE='1.0'
  $env:STACKCHAN_TTS_PRE_PHONEME_LENGTH='0.03'
  $env:STACKCHAN_TTS_POST_PHONEME_LENGTH='0.03'
  $env:STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD='256'
  $env:STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS='30.0'
  $env:STACKCHAN_TTS_LOADED_PLAYBACK='1'
  $env:STACKCHAN_TTS_LOADED_TRANSPORT='topic'
  $env:STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES='96'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC='0.02'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS='1'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC='3'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES='3'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC='0.15'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC='30'
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 190 --say-check "はい" --say-voice default
  ```

  The smoke expects `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `STACKCHAN_BRIDGE_SAY_VOICE_PROFILE_SEEN=1`, and
  `STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=1`. Also record whether the operator
  heard the speaker output; `tts_finished` alone is not an audible-playback
  pass. For audible-quality checks, prefer loaded playback
  (`STACKCHAN_TTS_LOADED_PLAYBACK=1`) so firmware can pass a stable loaded PCM
  buffer to M5Unified. The current default sends loaded ADPCM over the playback
  chunk topic and uses the final playback action result, not per-chunk service
  ACKs. Use `STACKCHAN_TTS_LOADED_TRANSPORT=service` only when comparing
  against the older synchronous load service. Keep
  `STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES=96` on the current COM3 host
  serial TCP bridge; the previous service-load path completed short ADPCM TTS
  at 96 bytes while 128, 256, and 512 byte compressed load requests timed out
  before the first firmware callback response.
  Keep `STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS=1` for the current
  host-serial TCP path. The bridge waits for bounded firmware
  `audio_playback_load` progress before sending the next loaded topic window so
  sequence gaps show up as redacted `expected_seq`/`received_seq` diagnostics
  instead of an opaque malformed payload.
  Keep `STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC=3` and
  `STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES=3` unless explicitly
  tuning the serial path. The bridge republishes the same loaded topic chunk
  only after progress stalls, and firmware treats same-command duplicate
  loaded chunks as idempotent observations instead of decoding them twice.
  PCM loaded-transfer diagnostics should still keep
  `STACKCHAN_AUDIO_PLAYBACK_LOAD_CHUNK_BYTES=64` unless the target has been
  revalidated with larger synchronous requests.
  The smoke harness should preserve startup events such as `firmware_ready`
  across the whole run; a later event page may no longer include early readiness
  events after a long TTS check. On repeated smokes where firmware was already
  running before the bridge started, a connected `/stackchan/<device_id>/status`
  sample is also a valid readiness observation for the harness-level smoke
  result.

  Before running a full TTS smoke, isolate the firmware loaded-playback service
  without a provider request or bridge TTS path:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-loaded-audio-probe --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 30 --chunk-bytes 32,64,160 --total-bytes 160
  ```

  The probe waits for `/stackchan/default/device/status` to report
  `connected: true`, then calls
  `/stackchan/default/device/audio/playback/load` directly with silent PCM. It
  prints `STACKCHAN_LOAD_PROBE_CHUNK_RESPONSE` or
  `STACKCHAN_LOAD_PROBE_CHUNK_TIMEOUT` lines with chunk size, sequence, byte
  count, result state, and buffered counters only. It must not print PCM,
  speech text, provider request bodies, transcripts, images, NFC tag IDs, IR
  codes, or protocol dumps.
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
- After a successful `motion pose --wait` or `motion home --wait`, confirm the
  immediate `motion status --json` check reports the returned firmware pose as
  non-stale. The bridge default head-pose stale threshold is 15 seconds; stale
  status is still a valid failure for older telemetry, but it should not trip
  the same smoke that just received a successful firmware pose response.
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
- 2026-05-28 KOIZUMI-160 local VOICEVOX smoke completed the loaded ADPCM topic
  path on COM3 with `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=1`, and firmware
  `audio_playback_load` `complete=true` for 13 chunks / 4778 decoded PCM bytes.
  The same smoke recorded `loaded_playback_started`, `loaded_playback_queued`,
  and `loaded_playback_drained`. That initial successful focused run used a
  conservative 0.25 s loaded-topic publish interval and
  `--allow-missing-firmware-ready`
  because `firmware_ready` appeared in the first event page but the later smoke
  summary cursor did not include it. Treat that cursor check as harness work,
  not a TTS transport failure.
- 2026-05-28 KOIZUMI-169 lowered loaded ADPCM topic pacing on the same COM3
  path. Short `say` smoke passed at 0.10 s, 0.05 s, and twice at 0.02 s.
  A longer `say` smoke also passed at 0.02 s with 36 chunks / 13528 decoded
  PCM bytes. The 0.01 s run failed with `MALFORMED_AUDIO_CHUNK`: firmware
  accepted `seq=0`, then saw `seq=5` while still expecting the contiguous next
  chunk. Keep 0.02 s as the fastest validated default until repeated longer
  prompts prove a lower value is stable.
- 2026-05-28 KOIZUMI-163 software-side TTS tuning compared local provider
  output without recording speech text in public logs. The old transport-fast
  profile used speed 3.0, zero phoneme padding, threshold 512, and 20 ms trim
  margin; it produced a very short 149 ms / 4778 byte short prompt. The
  transport-balanced profile used speed 1.6, 0.03 s pre/post phoneme padding,
  threshold 256, and 30 ms trim margin. It produced 295 ms / 9436 bytes for
  the short prompt and 797 ms / 25504 bytes for the longer prompt, staying
  under the 32 KiB loaded playback buffer. The balanced longer-prompt smoke
  completed on COM3 with 67 ADPCM chunks,
  `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=1`, and
  `loaded_playback_drained`.
- KOIZUMI-163 operator-listening then confirmed the natural-speed audible
  profile as words for a short-word prompt: speed 1.0, 0.03 s pre/post phoneme
  padding, threshold 256, 30 ms trim margin, loaded playback topic, IMA ADPCM,
  and 96 byte ADPCM load chunks. The machine smoke completed with text length
  5, 70 ADPCM chunks, 26792 decoded bytes, `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=1`, `loaded_playback_queued`, and
  `loaded_playback_drained`. Use this as the recommended audible short-word
  smoke profile; do not treat it as proof that longer prompts are natural.
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
- After a timed-out playback smoke, do not treat the next media smoke as clean
  until the helper reports the same `command_id` reaching a terminal
  `audio_playback_action` event or the run fails. The bridge also keeps a
  bounded media-settle gate after timed-out playback, audio capture, or camera
  actions; a command during that window should return structured
  `FIRMWARE_BUSY` with the previous `command_id` instead of accepting a
  possibly contaminated media session.
- For focused KOIZUMI-145 stale-media diagnostics, a playback-only smoke may
  pass with `stackchanctl audio play --wait` returning `TIMEOUT` only when the
  helper also observes the same `command_id` reaching a terminal
  `audio_playback_action` event and reports
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_TIMEOUT_SETTLED_SEEN=1`. This is a media
  cleanup result, not audible playback proof.

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

  For focused media reruns after a playback timeout or another settling media
  action, use `--media-mode` instead of the default all-in-one media sequence:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --allow-stale-install --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 35 --stimulus-window-seconds 0 --media-mode camera-only --media-camera-quality 50
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --allow-stale-install --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 35 --stimulus-window-seconds 0 --media-mode audio-capture-only --media-audio-capture-seconds 0.02
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --allow-stale-install --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 35 --stimulus-window-seconds 0 --media-mode playback-only --media-audio-playback-wait
  ```

  The legacy `--media-playback-only` flag is kept as an alias for
  `--media-mode playback-only`. The default `--media-mode all` waits for the
  playback command's own terminal `audio_playback_action` event before running
  audio capture or camera. If the terminal event is not observed, the helper
  reports `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED_DUE_TO_ACTIVE_MEDIA=1`
  and `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED_DUE_TO_ACTIVE_MEDIA=1`
  instead of misclassifying later `FIRMWARE_BUSY` results as capture or camera
  regressions.

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
  `touch_output_read_ok`, `touch_output_raw`, `touch_output_read_failures`,
  `ltr553_manufacturer_ok`, `ps_read_ok`, `ps_raw`, `als_read_ok`, `als_raw`,
  `power_voltage_v`, and `in_i2c_released_for_camera`. If
  `touch_output_read_ok=true` and `touch_output_raw` changes while
  `touch_i0..touch_i2` remain zero, treat it as a BSP intensity mapping issue.
  If `touch_output_read_ok=false`, treat it as an Si12T/I2C read path issue.
  The profile keeps the
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
  `_OK_SEEN` markers when firmware-owned transport succeeds. Focused media
  runs also emit `STACKCHAN_SENSOR_SWEEP_MEDIA_MODE`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OUTPUT_BYTES`,
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OUTPUT_BYTES`,
  `STACKCHAN_SENSOR_SWEEP_*_FIRMWARE_BUSY_SEEN`, and camera-specific
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_CAMERA_FAILED_SEEN` markers. Treat a
  structured unsupported result, bounded `MIC_OVERRUN`, bounded
  `CAMERA_CAPTURE_FAILED`, or an accepted firmware-confirmed result as a
  transport smoke classification while that feature is being brought up. A
  focused run that reports `FIRMWARE_BUSY` is not a target-feature result; let
  the media path settle and rerun the focused mode. The normal redaction scan
  must still report no PCM, transcript, image, JPEG, or base64 payloads.
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

2026-05-28, device `default`, COM3 through Windows serial TCP bridge, firmware
version `bringup`, KOIZUMI-172 focused media rerun after NFC init ordering
change:

```powershell
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --allow-stale-install --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 35 --stimulus-window-seconds 0 --media-mode camera-only --media-camera-quality 50
uv run --no-project python scripts/microros_agent_container.py tcp-pty-sensor-sweep --skip-build --allow-stale-install --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 35 --stimulus-window-seconds 0 --media-mode audio-capture-only --media-audio-capture-seconds 0.02
```

Observed results:

- Camera-only smoke: pass. The command returned `ok=true` /
  `result_state: ACCEPTED`, `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=1`,
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OUTPUT_BYTES=5465`,
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_FIRMWARE_BUSY_SEEN=0`, and
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_CAMERA_FAILED_SEEN=0`.
- Audio-capture-only smoke: pass. The command returned `ok=true` /
  `result_state: ACCEPTED`, `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OK_SEEN=1`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OUTPUT_BYTES=684`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_FIRMWARE_BUSY_SEEN=0`, and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_MIC_OVERRUN_SEEN=0`.
- Redaction checks: pass on both focused runs.
  `STACKCHAN_SENSOR_SWEEP_EVENTS_SENSITIVE_PAYLOAD_SEEN=0` and
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0`. JPEG/WAV file bytes
  were not printed or copied into Linear; only sizes and result markers were
  recorded.
- Harness behavior: pass for focused-mode separation. The camera run printed
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_SKIPPED=1` and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_SKIPPED=1`; the audio-capture run
  printed `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_SKIPPED=1` and
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_SKIPPED=1`. Neither focused media
  command was contaminated by a previous playback `FIRMWARE_BUSY`.

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
- Later manual live capture for KOIZUMI-131 observed the first usable LTR553
  stimulus around `raw=3` / `signal=0.001465...`; firmware semantic proximity
  thresholds are therefore intentionally low and hysteretic until a broader
  distance fixture is collected.
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

2026-05-28 KOIZUMI-75 follow-up, device `default`, COM3 through the Windows
serial TCP bridge, after moving UnitNFC initialization after camera probing so
camera `M5.In_I2C.release()` cannot detach an already-registered NFC unit:

- `uv run --no-project python -m unittest firmware.m5stackchan-microros.tests.test_firmware_contract`:
  pass.
- `uv run --no-project python scripts/firmware_platformio.py build`: pass.
- `uv run --no-project python scripts/firmware_platformio.py upload --port COM3
  --upload-speed 115200 --no-stub`: pass.
- `tcp-pty-sensor-sweep --tcp-host host.docker.internal --tcp-port 11411
  --baud 921600 --verbose 4 --timeout 12 --stimulus-window-seconds 90
  --skip-media-smoke`: pass after rebuilding the ROS package in-container.
  The sweep observed `nfc_detected`, `nfc_removed`, `nfc_read_failed`,
  `remote_button_pressed`, and `remote_command_received`, with
  `STACKCHAN_EVENT_STIMULUS_NFC_STATUS=PASS`,
  `STACKCHAN_EVENT_STIMULUS_IR_STATUS=PASS`,
  `STACKCHAN_SENSOR_SWEEP_EVENTS_SENSITIVE_PAYLOAD_SEEN=0`, and
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0`.
- Public and device event payloads used bounded `tag_ref` and `remote_ref`
  values. Do not record raw tag IDs, UIDs, raw IR codes, or protocol dumps from
  this validation in issue trackers or normal logs.

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
  `next=0`. No `chunk_accepted`, `chunk_rejected`, speaker frame failure, or
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
  complete. At the time, 96 bytes was the fastest validated pull-only playback
  chunk size and 64 bytes was the conservative fallback. Later
  operator-listening checks did not hear speech, and KOIZUMI-143 supersedes this
  as a transport/result validation only; do not treat `tts_finished` alone as
  audible speaker validation.
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

### 2026-05-26 KOIZUMI-143 M5Unified speaker buffering diagnosis

- Operator-listening `say` smoke with the local VOICEVOX path did not produce
  audible speech, even when bridge events reached `tts_finished` in one run.
  Treat `tts_finished` as TTS/relay metadata only; it is not proof that the
  K151 speaker emitted sound.
- StackChan-BSP 1.1.0 does not provide a speech-stream wrapper. Its audio
  examples only use simple `M5.Speaker.tone()` calls. Firmware speech playback
  therefore depends on M5Unified `M5.Speaker.playRaw()`.
- M5Unified `playRaw()` keeps runtime PCM buffer references for the speaker
  task and documents that generated data should use rotating buffers. Current
  firmware was handing 64 or 96 byte transport fragments directly to
  `playRaw()`. At 16 kHz mono s16le that is only 2-3 ms of audio per fragment,
  while the firmware pull loop had been paced around 20 ms, so playback could
  be far slower than real time or effectively discontinuous.
- The firmware playback adapter now aggregates accepted transport chunks into
  20 ms speaker frames before `playRaw()`, rotates fixed buffers, flushes the
  final partial frame only after end-of-stream, and explicitly switches from
  microphone to speaker ownership for playback.
- Firmware also holds a fixed in-RAM jitter buffer for future playback
  sequences, because K151 serial micro-ROS topic delivery can expose ordering
  jitter before the missing expected chunk arrives. The buffer is now sized for
  24 future 20 ms / 640 byte chunks, remains payload-private, and only avoids
  premature aborts; persistent gaps still end as `AUDIO_UNDERRUN`.
- Serial micro-ROS `NextAudioChunk` service responses are not suitable as the
  default TTS stream path on K151: 96 byte chunks were too slow for audible
  speech, while 640 byte responses produced repeated firmware
  `pull_response_timeout` diagnostics. Bridge-owned TTS therefore defaults to
  the paced playback topic relay after `/stackchan/<device_id>/device/audio/play`
  accepts the goal, while keeping the same buffered chunks available through
  `NextAudioChunk` as a fallback for missing topic sequences. Use
  `STACKCHAN_AUDIO_PLAYBACK_PULL_ONLY=1` only to reproduce pull-helper
  diagnostics.
- 2026-05-26 follow-up smoke with 96 byte topic chunks and per-chunk duplicate
  publishing disabled still failed with `chunk_jitter_window_exceeded`: the
  bridge buffered 94 chunks and published them faster than firmware could
  advance through a 24-slot future window. The firmware window was therefore
  revisited while keeping M5Unified
  speaker frames at the 20 ms / 640 byte baseline.
- After changing the gap timer to track expected-sequence progress, the
  96 byte smoke no longer failed with `AUDIO_UNDERRUN`, but it still timed out
  at the CLI after about 90 seconds because the utterance required 94 small
  chunks. That confirms the chunk size, not only speaker buffering, was the
  dominant latency source.
- The next iteration moves the standard bridge-owned TTS transport back to
  640 byte chunks and sizes the firmware future-chunk buffer for 24 such
  chunks. The action goal keeps the first segment at 64 bytes to keep goal
  acceptance light; firmware aggregates that first fragment with subsequent PCM
  before queuing M5Unified speaker frames.
- A 640 byte run after that change still timed out because firmware continued
  polling `NextAudioChunk` every few milliseconds; repeated pull timeouts and
  reliable topic retries starved the serial link before topic chunks reached
  the subscription. Firmware now treats pull as idle fallback instead of the
  primary transfer loop while topic chunks are making progress.
- A follow-up topic-first 640 byte run still showed no topic chunks reaching
  firmware before the fallback pulls began. The bridge now paces prebuffered
  topic chunks at 150 ms on serial hardware, and firmware waits 450 ms of
  chunk-idle time before falling back to pull/EOS checks.
- A connected `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=0` smoke confirmed
  the device audio action can accept an empty first-goal payload and the bridge
  can activate the relay. However, the firmware only observed a late
  out-of-order `seq=14` chunk while expected `seq=0` never arrived, then
  reported `chunk_jitter_gap_timeout`. That narrows the non-audible speech
  blocker to bridge-to-firmware playback chunk delivery rather than the
  StackChan-BSP/M5Unified speaker API.
- A follow-up reliable-QoS experiment for
  `/stackchan/<device_id>/device/audio/playback/chunks` built, uploaded, and
  connected, but it made the serial path worse: firmware accepted only the
  first 64 byte action-goal fragment, no topic chunks reached the playback
  subscription, and host bridge traffic climbed above 2 MB before timeout. Do
  not keep reliable playback QoS as the fix; the next design needs a different
  media transfer shape rather than more DDS retries on the serial link.
- The `tcp-pty-sensor-sweep` media smoke now exposes the short playback prompt
  duration, frequency, and amplitude. The default remains a 20 ms, 440 Hz,
  low-amplitude diagnostic sine; for operator-listening checks, set
  `--media-audio-playback-duration-ms` and
  `--media-audio-playback-amplitude` explicitly. Use
  `--media-playback-only` for focused speaker diagnostics so a timed-out
  playback action is not followed by capture or camera commands. Add
  `--media-audio-playback-wait` when the smoke must prove the firmware-owned
  terminal playback result instead of only the CLI handoff. Record whether the
  operator heard the output.
- A 1 ms, high-amplitude click with
  `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=64` completed and firmware emitted
  `speaker_partial_frame_queued`. This proves a tiny PCM payload can reach the
  M5Unified speaker queue, but it is not speech and may be too short to hear
  reliably.
- A 20 ms / 640 byte sine sent entirely as the first action-goal payload timed
  out and caused a liveness disconnect/reconnect cycle. Do not use 640 byte
  action-goal payloads as the audible-smoke path.
- A 20 ms sine split into 64 byte transport chunks still timed out at the CLI,
  but firmware accepted several chunks and queued a 448 byte partial speaker
  frame after end-of-stream. The bridge still reported pending chunks, so the
  remaining blocker is serial-friendly PCM transfer completion, not the basic
  `M5.Speaker.playRaw()` queue call.
- Follow-up implementation changes topic-first fallback behavior: firmware
  pull requests for a buffered sequence now cause the bridge to republish that
  chunk on `/stackchan/<device_id>/device/audio/playback/chunks` and return an
  accepted empty service response, instead of sending PCM in the synchronous
  `NextAudioChunk` response. Re-run the 20 ms / 64 byte short-audio smoke after
  rebuild/upload to confirm this reduces timeout and duplicate-pull behavior.
- `stackchanctl audio play` now returns after bridge action acceptance and CLI
  chunk handoff when `--wait` is not set. A playback-only 20 ms / 64 byte smoke
  then returned `ok=true`, but the firmware event list still showed stale
  delayed playback activity from the previous command rather than a clean
  terminal result for the new command. Treat this as a CLI handoff success only,
  not audible playback proof. The next hardware fix must clear or prevent late
  firmware media actions after a timed-out bridge action before using non-wait
  CLI success as a media smoke pass.
- Firmware now stops treating pull response timeouts as audio progress. A pull
  timeout clears the pending request but no longer refreshes
  `play_audio_last_chunk_ms`, so a playback session with no real PCM progress
  can reach the bounded inter-chunk timeout and release the media path instead
  of lingering into the next smoke.
- After that firmware upload, the 20 ms / 64 byte playback-only smoke used the
  current command id cleanly and the bridge no longer started the topic relay
  by publishing sequence 2 before sequence 1. The firmware still ended with
  `chunk_jitter_gap_timeout` and `audio_playback_underrun`, so `ok=true` from
  non-wait `stackchanctl audio play` is still only a CLI handoff result.
- The next bridge/firmware retry narrows the remaining gap case: the first
  topic chunk after a first action-goal fragment is retried like sequence 0,
  NACK-triggered topic republishes are sent a few times, and firmware skips the
  normal fallback idle wait when it already has future chunks buffered and is
  waiting for a missing sequence. Rebuild, upload, and re-run the same 20 ms /
  64 byte playback-only smoke before attempting speech.
- A pull-only comparison still timed out on a 20 ms / 64 byte playback smoke,
  so the recommended path remains topic-first. The bridge now keeps the topic
  NACK behavior first, but after bounded repeated requests for the same missing
  sequence it can return that one chunk in the `NextAudioChunk` service response
  as a last-mile fallback.
- The fallback path did fire on the 20 ms / 64 byte smoke, but the device still
  stalled near the final chunks. Playback chunks are now treated as reliable
  device command input instead of best-effort observation telemetry, while
  capture chunks remain best-effort. Firmware also aborts stale playback after
  the inter-chunk timeout even if repeated pull requests are still pending, so
  failed smokes return a firmware-owned result instead of hanging until the CLI
  timeout.
- A 20 ms playback-only smoke with `STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES=64`
  and `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES=160` completed successfully with
  `speaker_frame_queued`, `pull_end_of_stream`, bridge pending `0`, and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_OK_SEEN=1`. Use 160 byte playback
  transport chunks as the K151 bring-up default before attempting longer TTS.
- The first `こんにちは` TTS smoke synthesized 56 playback chunks, then failed
  with firmware `chunk_jitter_window_exceeded` because the bridge published the
  full prebuffered utterance faster than the firmware 24-slot jitter window
  could drain. The bridge now limits the initial topic publish and uses
  pull-triggered lookahead windows for later chunks.
- A follow-up windowed run reached sequence 10, then failed after repeated pull
  response timeouts because the pull callback slept while publishing lookahead.
  Pull-triggered lookahead publishing now avoids per-chunk sleeps so the helper
  response can return before the firmware pull timeout.
- A best-effort playback-topic experiment lost even a 20 ms prompt; restoring
  reliable playback topic QoS plus 160 byte transport chunks restored the 20 ms
  playback-only smoke. The passing run emitted `speaker_frame_queued`,
  `pull_end_of_stream`, bridge pending `0`, and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_OK_SEEN=1`.
- With the short prompt restored, `こんにちは` still failed: VOICEVOX produced
  56 transport chunks, firmware advanced only into the first few sequences, and
  missing-sequence pull fallback ended in `AUDIO_UNDERRUN`. A minimal TTS
  utterance, `あ`, still produced 21 chunks and failed the same way near
  sequence 3. This shows the remaining blocker is not the text length, but
  ordered delivery of more than a handful of playback chunks over serial
  micro-ROS.
- The bridge now keeps prebuffered TTS sessions active until buffered chunks
  drain, limits the initial topic window, and republish-fallback chunks on the
  playback topic when the firmware repeatedly NACKs the same sequence. This
  improved one `こんにちは` run from failing near sequence 3 to reaching
  sequence 7 and queuing at least one speaker frame, but it still did not
  complete speech.
- Do not switch the K151 bring-up default to 320 byte transport chunks yet. A
  320 byte `こんにちは` run stalled in `stackchanctl say`, and a 20 ms short
  playback smoke with 320 byte transport chunks also hung in `audio play` until
  the helper was killed. Keep 160 byte chunks for the validated short prompt
  while designing a different serial-friendly speech transfer shape.
- Next implementation should move beyond DDS topic/service retries for long
  PCM. Use KOIZUMI-144 for the transport redesign, and keep KOIZUMI-145 focused
  on stale media action cleanup between timed-out smokes.
- KOIZUMI-149 direct `LoadAudioChunk` probing showed that 32 and 64 byte
  requests reach the firmware callback on COM3 serial TCP bridge, while 96 and
  160 byte requests can time out at sequence 0. Keep loaded playback service
  requests at the 64 byte default unless specifically diagnosing the transport.
- A loaded TTS `say あ` smoke completed end-to-end with 3412 bytes split into
  54 service chunks and emitted `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `tts_finished`, `loaded_playback_started`, `speaker_frame_queued`,
  `loaded_playback_drained`, and `result_response_sent`. The smoke checks took
  about 116 seconds, so this path is correct but too slow for practical speech.
- `STACKCHAN_TTS_LOADED_PLAYBACK=0` must be passed through the container helper
  when comparing the older topic-first path. An initial comparison completed in
  about 56 seconds, but its events showed stale loaded buffer state from a prior
  timed-out load. Firmware now clears stale loaded buffers when a new non-loaded
  playback goal starts.
- After that guard, a clean topic-first `say あ` no longer mixed in loaded
  playback state, but failed with `AUDIO_UNDERRUN` around sequence 3 after
  repeated `pull_response_timeout` and out-of-order topic chunks. Treat the
  loaded path as the current correctness baseline and the topic-first path as a
  latency investigation path until sequence recovery is fixed.
- The follow-up hypothesis is that the 1000 ms firmware `NextAudioChunk`
  timeout is shorter than the observed serial service response timing during
  fallback. A diagnostic build raises the pull timeout to 2500 ms and pending
  gap timeout to 5000 ms for topic-first comparison; keep loaded playback as
  the default until the clean smoke result is known.
- For the next topic-first smoke, set
  `STACKCHAN_AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS=0` to bypass the
  bridge's topic-republish-first policy and answer `NextAudioChunk` with a
  fallback chunk immediately. This isolates whether serial latency comes from
  service response size or from the deliberate NACK/republish cycle.
- Topic-first smoke with
  `STACKCHAN_TTS_LOADED_PLAYBACK=0`,
  `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES=64`, and
  `STACKCHAN_AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS=0` completed
  `stackchanctl say あ` successfully. The device reached `pull_end_of_stream`
  and the bridge emitted `tts_finished`; smoke checks still took roughly 179 s,
  so this is a correctness baseline, not an acceptable latency profile.
- The same immediate-fallback test with the default 160-byte topic chunks still
  failed with `AUDIO_UNDERRUN`. Firmware saw repeated `pull_response_timeout`
  for later sequences even though the bridge logged served fallback chunks.
  Keep 64-byte service chunks as the current reliable serial ceiling for
  topic-first diagnostics.
- A pull-only diagnostic path avoids the topic window and duplicate topic
  traffic: set `STACKCHAN_TTS_LOADED_PLAYBACK=0`,
  `STACKCHAN_AUDIO_PLAYBACK_PULL_ONLY=1`,
  `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES=64`,
  `STACKCHAN_TTS_SPEED_SCALE=6.0`,
  `STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD=1024`, and
  `STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS=0.0`. With this profile, `say あ`
  completed with smoke checks around 72 s and `say こんにちは` completed with
  the action itself taking roughly 113 s. This is the current reliable
  ROS-mediated speech path, but it is still limited by about 1.8-2.0 s per
  64-byte pull service round trip.
- Follow-up firmware reduces audio chunk diagnostic event traffic by sampling
  routine per-chunk `audio_playback_chunk` events while preserving errors,
  first/terminal chunks, speaker-frame events, and every 16th sequence. This
  keeps the serial link focused on audio transport during latency smokes.
  With the same pull-only `say あ` profile, the sampled firmware completed in
  roughly 68 s versus the previous 72 s baseline. The small delta suggests
  event traffic is only a secondary factor; the dominant cost remains the
  per-chunk `NextAudioChunk` service round trip.
- The next topic-first latency probe uses
  `STACKCHAN_AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS` and
  `STACKCHAN_AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS` to expand the bridge's topic
  publish window without changing the ROS interface. The goal is to let
  firmware consume the 64-byte topic stream from its jitter buffer and use
  `NextAudioChunk` mainly for end-of-stream confirmation.
- The first expanded-window probe with 64-byte chunks,
  `STACKCHAN_AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS=64`,
  `STACKCHAN_AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS=32`, and
  `STACKCHAN_AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS=16` failed with
  `AUDIO_UNDERRUN`. Firmware accepted the first chunk but later reported a
  gap near sequence 3 while the bridge had already published more than 100
  topic chunks and had 24 pending jitter entries. Treat the window environment
  variables as diagnostic controls only. Reducing service round trips needs an
  explicit ACK/window or bundle contract instead of blind topic flooding.
- After adding ACK/window fields to `NextAudioChunk`, a topic-first smoke with
  64-byte chunks, speed 6, initial window 8, lookahead 8, and delayed service
  fallback still failed with `AUDIO_UNDERRUN`. Firmware timed out waiting for
  the empty helper response around sequence 2, then saw the republished missing
  chunks only after the action had already failed. Reducing lookahead to 1 also
  failed. This confirms that ACK metadata alone is not enough; topic-first
  playback needs a transport loop that does not depend on helper-service
  responses returning before the firmware gap timeout.
- The same firmware and bridge still completed the current reliable fallback:
  `STACKCHAN_TTS_LOADED_PLAYBACK=0`,
  `STACKCHAN_AUDIO_PLAYBACK_PULL_ONLY=1`,
  `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES=64`,
  `STACKCHAN_TTS_SPEED_SCALE=6.0`,
  `STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD=1024`, and
  `STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS=0.0` completed `stackchanctl say あ`
  with `tts_finished`. The smoke checks took roughly 133 s because the path is
  still service-round-trip bound, but it remains the known-good speech baseline.
- After adding firmware-origin
  `/stackchan/default/device/audio/playback/acks`, the topic-first ACK/window
  smoke completed `stackchanctl say あ` with `tts_finished` using 64-byte
  chunks, speed 6, initial window 2, lookahead 2, and delayed service fallback.
  Firmware accepted and drained the stream, queued speaker frames, and emitted
  the terminal playback result. Smoke checks took roughly 122 s, which is an
  improvement over the previous pull-only 133 s baseline but still not an
  acceptable latency profile. The run still showed occasional
  `pull_response_timeout` and many bridge republished topic chunks
  (`published=372` for 26 buffered chunks), so the next tuning target is to
  reduce redundant ACK-triggered republishes and keep the helper service mostly
  for end-of-stream confirmation.
- Reducing ACK duplicate cadence too aggressively caused regressions:
  `STACKCHAN_AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC=0.5` and `0.1`
  both ended in `AUDIO_UNDERRUN`, and publishing each ACK-requested topic chunk
  only once caused the bridge `say` action to time out before firmware playback
  progressed beyond startup. The current validated compromise keeps duplicate
  ACK throttling disabled by default and republishes the first chunk of each
  ACK-triggered window twice. With
  `STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES=64`,
  `STACKCHAN_AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS=2`,
  `STACKCHAN_AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS=2`,
  `STACKCHAN_AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS=16`,
  `STACKCHAN_TTS_SPEED_SCALE=6.0`,
  `STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD=1024`, and
  `STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS=0.0`, `stackchanctl say あ`
  completed with `tts_finished`. Smoke checks took roughly 106 s, and bridge
  relay stats improved to `published=248` for 26 buffered chunks. Residual
  `pull_response_timeout` diagnostics and post-completion duplicate/orphan
  chunks remain follow-up transport cleanup, not proof of audible quality.
- A firmware-side stale terminal diagnostic suppression fixed the post-result
  orphan event noise without stopping late recovery traffic. The failed bridge
  active-session guard proved too aggressive: it reduced bridge publishes to
  `77` but caused `AUDIO_UNDERRUN` with 20 pending chunks. After reverting that
  guard and suppressing late chunks or pull responses for the same recent
  terminal `command_id` in firmware, the same `say あ` smoke completed with
  `tts_finished`, no post-completion `chunk_without_active_goal` /
  `pull_response_without_active_goal` events in the observed event window,
  bridge relay stats `published=123` for 26 buffered chunks, and smoke checks
  around 28 s. This validates the cleanup as a diagnostics/noise fix; audible
  quality and longer prompts still need separate checks.
- Longer local TTS transport now completes through the same ACK/window path,
  but latency still scales with chunk count. With the same 64-byte chunk,
  initial window 2, lookahead 2, delayed fallback, speed 6, and silence-trim
  profile, `stackchanctl say こんにちは` completed with `tts_finished`,
  `pull_end_of_stream`, terminal playback result, `published=229` for 57
  buffered chunks, and smoke checks around 28 s. `stackchanctl say
  テスト終わったよ` also completed, with `published=327` for 80 buffered chunks
  and smoke checks around 133 s. These are ROS transport completion results;
  operator-listening audible quality, volume, and intelligibility still need a
  separate confirmation before claiming natural speech behavior.
- Operator-listening confirmed the topic-first longer-prompt path produced
  sound but was too broken up to recognize as speech. Treat the ACK/window
  topic-first path as transport bring-up, not audible-quality proof. A loaded
  playback comparison with 640 byte load-service chunks timed out on the first
  request even though the total PCM size fit the firmware buffer. Re-running
  with 64 byte load chunks completed a short loaded TTS smoke and showed
  `audio_playback_load`, `loaded_playback_started`, `loaded_playback_queued`,
  `loaded_playback_drained`, `tts_finished`, and terminal action result events.
  Firmware now queues the already-loaded PCM buffer directly into M5Unified
  rather than feeding 20 ms frames from the ROS loop, expands the fixed loaded
  buffer to 32 KiB, and keeps the loaded PCM alive until speaker release.
  Reducing normal per-load-chunk firmware diagnostics to sampled events reduced
  event volume but did not materially improve service round-trip latency on the
  host serial TCP bridge: 64 byte load chunks still took roughly 1.3-2.0 s each.
  A 128 byte loaded TTS smoke timed out after the first chunk took roughly 32 s,
  so 64 byte chunks remain the only observed reliable setting on this setup.
  Firmware now permits a new `sequence=0` loaded transaction to reset a stale
  incomplete load after the inter-chunk timeout, avoiding a reboot after a
  failed load-size experiment.
- A follow-up KOIZUMI-145 playback-only 20 ms smoke on 2026-05-28 used
  event-cursor walking after the pre-command event id and completed with
  `STACKCHAN_SENSOR_SWEEP_MEDIA_SETTLE_TERMINAL_SEEN=1` and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_TIMEOUT_SETTLED_SEEN=1` for the current
  `audio_playback_action` `command_id`. The focused smoke exited 0; this
  validates stale-media cleanup/observation, not audible playback quality.
- KOIZUMI-171 raised the bridge default head-pose stale threshold to 15 seconds
  and refreshes the latest pose snapshot from successful firmware
  `motion pose` / `motion home` responses. A 2026-05-28
  `tcp-pty-bridge-smoke --home-check` rebuilt `stackchan_bridge` and passed
  with `STACKCHAN_BRIDGE_HOME_COMPLETED=1`, `STACKCHAN_BRIDGE_HOME_STATUS_EXIT=0`,
  `pan_deg=0.0`, `tilt_deg=0.0`, and `stale=false`.
- KOIZUMI-161 follow-up reduces standard-build static RAM pressure by treating
  loaded playback as the default speech path and shrinking the diagnostic
  topic/pull future-chunk jitter buffer from the earlier 24-slot bring-up
  setting to 8 slots. Define
  `STACKCHAN_AUDIO_TOPIC_RELAY_EXTENDED_BUFFER=1` only when intentionally
  reproducing old topic relay diagnostics and accepting roughly 10 KiB more
  static RAM use. The standard PlatformIO build passed with RAM at 276440 /
  327680 bytes (84.4%). This change is build/contract validation only until
  another operator-listening smoke can confirm the audible result.
- KOIZUMI-162 comparison selects IMA ADPCM as the next compressed loaded
  playback experiment. The target is to cut bridge-to-firmware payload bytes by
  roughly 4:1 while decoding into the existing 32 KiB loaded PCM buffer before
  `playRaw()`. G.711 is kept as a simpler 2:1 fallback, and Opus/Speex are
  deferred until firmware footprint is proven. No audible claim is made until a
  later operator-listening smoke.
- KOIZUMI-165 adds the firmware-side IMA ADPCM loaded playback decoder and
  validates it by build only. The PlatformIO helper command timed out while the
  regenerated micro-ROS build was still running, but the remaining container
  completed successfully: RAM 276448 / 327680 bytes (84.4%), Flash 903105 /
  6553600 bytes (13.8%). This is not an upload or audible smoke result.
- KOIZUMI-173 moves camera JPEG bytes off the camera action result and onto
  `/stackchan/default/device/camera/chunks`. The first 1024 byte chunk smoke
  failed with firmware `camera JPEG chunk publish failed`. The 512 byte chunk
  build uploaded but the camera smoke rejected the frame as non-contiguous,
  confirming best-effort serial drops when the burst is too large. The 2026-05-28
  256 byte, 4 ms paced chunk build uploaded successfully to COM3 and passed
  camera-only smoke through the host serial TCP bridge:
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_EXIT=0`,
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=1`, and
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OUTPUT_BYTES=2660`. A follow-up direct
  capture through the same Agent/bridge path saved
  `tmp/stackchan_camera_preview.jpg` at 2651 bytes. Normal output/log redaction
  checks remained clean; JPEG bytes and base64 did not appear in CLI JSON,
  public events, or normal logs.

## Cleanup

- Save the command transcript and observed result codes in the PR or Linear
  issue.
- Reset temporary maintenance/debug firmware changes before merging production
  code.
