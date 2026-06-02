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
  $env:STACKCHAN_TTS_SAMPLE_RATE='8000'
  $env:STACKCHAN_TTS_PROGRESSIVE_TEXT_SEGMENT_MAX_CHARS='64'
  $env:STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD='256'
  $env:STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS='30.0'
  $env:STACKCHAN_TTS_LOADED_PLAYBACK='1'
  $env:STACKCHAN_TTS_LOADED_TRANSPORT='topic'
  $env:STACKCHAN_TTS_LOADED_AUDIO_SPLIT_TARGET_DECODED_BYTES='16384'
  $env:STACKCHAN_AUDIO_PLAYBACK_BUFFER_MAX_CHUNKS='4096'
  $env:STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES='128'
  $env:STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOADED_MAX_DECODED_BYTES='131072'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC='0.04'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS='8'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC='4'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES='3'
  # Optional CLI audio-play experiment only:
  # $env:STACKCHAN_AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES='32768'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC='0.15'
  $env:STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC='90'
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 190 --say-check "はい" --say-voice default --say-face happy --say-motion cheerful --say-after-face happy
  ```

  For the current compact detailed-speech naturalness candidate, use the
  dedicated helper flag instead of hand-copying the text:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 190 --say-naturalness-check
  ```

  After the operator listens and all listening checks pass, rerun the same
  candidate with an explicit verdict so the smoke log records the human result.
  Prefer the normal build path for this final evidence; use `--skip-build` only
  for repeated checks after a successful normal build and never with stale
  source changes:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 190 --say-naturalness-check --say-operator-listening-verdict pass
  ```

  This runs one public `say` with:
  `詳しく話すよ。中で分けて待ちを減らすよ。`
  and default `--face happy --motion cheerful --after-face happy` hints unless
  those hints are explicitly overridden.

  The smoke expects `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `STACKCHAN_BRIDGE_SAY_VOICE_PROFILE_SEEN=1`, and
  `STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=1`. When expression hints are passed,
  it also expects `STACKCHAN_BRIDGE_SAY_FACE_HINT_SEEN=1`,
  `STACKCHAN_BRIDGE_SAY_MOTION_HINT_SEEN=1`, and
  `STACKCHAN_BRIDGE_SAY_AFTER_FACE_SEEN=1`; these confirm that the facade
  command carried the hints, while the operator must still confirm the visible
  expression and motion timing. For `say` checks, the helper also prints
  `STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_REQUIRED=1`,
  `STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_CHECKS=...`, and
  `STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_VERDICT=unrecorded`, plus
  `STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_ISSUE=none`. These are a reminder
  to record the human listening result; they are not automatic pass markers.
  For `--say-naturalness-check` runs with an unrecorded verdict, the helper also
  prints `STACKCHAN_BRIDGE_SAY_OPERATOR_LISTENING_PASS_RERUN_HINT=...` with a
  source-rebuilding pass-record command that does not expose arbitrary speech
  text.
  Use `--say-operator-listening-verdict pass` only if the speech was
  intelligible, volume was acceptable, no word or sentence was truncated,
  phrase timing did not sound chopped, and the initial wait was acceptable.
  Use `--say-operator-listening-verdict fail` when any of those listening
  checks fail, and add `--say-operator-listening-issue` with one of
  `unintelligible`, `volume`, `truncation`, `phrase_chop`, `wait`,
  `expression_timing`, or `other`. Also record whether the operator heard the
  speaker output;
  `tts_finished` alone is not an audible-playback pass. For
  audible-quality checks, prefer loaded playback
  (`STACKCHAN_TTS_LOADED_PLAYBACK=1`) so firmware can play a stable loaded
  buffer. The current default sends loaded ADPCM over the playback chunk topic
  with bounded progress windows until firmware reports the contiguous loaded
  transaction complete, then starts normal playback for that stable buffer. Use
  `STACKCHAN_TTS_LOADED_TRANSPORT=carousel` only when comparing against the
  older carousel retry path, `STACKCHAN_TTS_LOADED_TRANSPORT=pull` only when
  comparing against firmware pull-loaded transfer, and
  `STACKCHAN_TTS_LOADED_TRANSPORT=service` only when comparing against the
  older synchronous load service. Keep
  `STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES=128` on the current COM3
  host serial TCP bridge for the loaded topic path. The previous service-load
  path completed short ADPCM TTS at 96 bytes while 128, 256, and 512 byte
  synchronous compressed service-load requests timed out before the first
  firmware callback response; use 96 bytes only when specifically diagnosing
  the synchronous service-load path.
  For normal loaded-topic path, keep
  `STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS=8` for the current
  host-serial TCP path and
  `STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC=4` for normal
  audible checks. The bridge waits for payload-free firmware progress at
  bounded windows and republishes the current sequence after progress stalls;
  firmware treats same-command duplicate loaded chunks as idempotent
  observations instead of decoding them twice. The bounded-window carousel
  sends only `seq0` until the loaded session starts, then repeats the current
  expected sequence before each lookahead window because firmware reports topic
  progress at sampled intervals rather than every accepted chunk;
  keep `STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_ANCHOR_REPEATS=2` on the current
  host-serial path unless a smoke proves a different value. A progress timeout
  of `0` still uses the bridge bounded-window carousel path; do not use it as a
  fire-and-wait full-payload burst on the current host-serial path. The current
  firmware keeps the loaded topic subscriber at 16 samples
  and the micro-ROS input reliable stream at 8 samples; if a smoke still reports
  `sequence_gap`, check that the rebuilt `libmicroros` cache picked up the
  matching `microros_stackchan.meta` values before changing TTS timing.
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
  Also sample `shake`, `cheerful`, `look-left`, `look-right`, and `look-user`
  before marking the preset set visually tuned. Record observed direction,
  approximate range, noise, interference, and return behavior.
- When `shake` visually disagrees with the configured preset envelope, build
  and upload the event-based motion diagnostic profile, then run a longer
  motion smoke so the terminal `motion_diag_writes` event can drain:

  ```powershell
  uv run --no-project python scripts/firmware_platformio.py upload --port COM3 --upload-speed 115200 --no-stub --motion-diagnostics
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-bridge-smoke --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 120 --motion-check shake --soak-seconds 5 --soak-interval-seconds 1
  ```

  Expected events are `motion_diag_plan` at scheduler acceptance and
  `motion_diag_writes` at completion/failure. Compare their planned target
  range, actual target range, raw servo range, servo time, and write count
  before changing amplitude or timing again. This diagnostic is event-based and
  may run with the micro-ROS Agent; do not use serial text diagnostics on the
  same COM port while the Agent is attached.
- Confirm `stackchanctl --backend bridge motion idle --json` is accepted as a
  no-op and does not actuate servos.
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
  chunk. This 0.02 s default was later superseded by KOIZUMI-179 full-firmware
  validation after media/entity pressure changed the loaded-topic behavior.
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
- For short `stackchanctl audio play` fixtures that fit the firmware loaded
  playback buffer, expect the CLI-origin chunks to carry final
  `end_of_stream=true` metadata and the bridge to attempt loaded playback
  before starting the firmware action. If the payload is larger than the loaded
  buffer or the final chunk never arrives, the bridge may fall back to the
  streaming relay and should log only metadata, never PCM bytes.
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

  After single-feature bring-up is complete, do not switch back to individual
  media diagnostic firmware profiles just to investigate routine
  `FIRMWARE_BUSY`. Use the standard/full firmware and first confirm
  `stackchanctl --backend bridge observe --json` reports `/stackchan/default`
  connected with `audio_playback`, `audio_capture`, and `camera_snapshot` all
  available. Then run the intentional overlap matrix:

  ```powershell
  uv run --no-project python scripts/microros_agent_container.py tcp-pty-media-overlap-matrix --skip-build --tcp-host host.docker.internal --tcp-port 11411 --baud 921600 --verbose 4 --timeout 45 --media-camera-quality 50 --media-audio-capture-seconds 2.0
  ```

  This helper deliberately overlaps camera capture, audio capture, and audio
  playback commands so bridge-side `MediaActionGate` and firmware-side media
  guards can be classified. It is not a normal smoke pass/fail helper: expected
  `FIRMWARE_BUSY` rows prove resource arbitration, while `UNSUPPORTED_FEATURE`
  means the standard firmware capability precondition was not met. The helper
  prints command ids, result codes, event/log markers, and output byte counts
  only; do not paste JPEG bytes, PCM, speech text, or base64 payloads into
  Linear. Individual profiles such as `--microros-core-capture-camera-bringup`
  remain fallback diagnostics only when the standard/full firmware cannot keep
  the connected media capabilities available.

  For audio playback and capture, bridge-side gate release may also be driven by
  firmware status after the relevant capability has been observed active or
  queued and later becomes idle. This prevents a delayed action-result future
  from holding `FIRMWARE_BUSY` forever, and audio playback idle release also
  closes the bridge chunk relay to stop stale republish traffic. It does not
  make raw PCM topic playback a healthy serial transport by itself; if
  `audio play --wait` still times out with large pending relay counts, treat
  that as a playback transfer-shape issue rather than a media gate issue.

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
- KOIZUMI-174 baseline before the warm-up fix reproduced first-frame
  instability without rebuilding or reflashing: two fresh CLI captures through
  the existing Agent/bridge path produced different hashes and sizes. The first
  file was dark at 2372 bytes, while a second capture three seconds later was
  bright and 8532 bytes. Treat this as camera warm-up or stale frame buffer
  behavior, not as old output-file reuse. The fix should validate that the
  first capture after camera bring-up is already usable under normal lighting.
- The KOIZUMI-174 warm-up fix drains three bounded camera frames before the
  final snapshot. After build and COM3 upload on 2026-05-29, the first direct
  CLI capture after reset saved `tmp/stackchan_camera_koizumi174_first.jpg` at
  8219 bytes and produced a visibly lit frame under the same room lighting.
  A follow-up camera-only smoke using `--skip-build --allow-stale-install`
  passed with `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_EXIT=0`,
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=1`, and
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OUTPUT_BYTES=7303`. Normal output and
  event redaction remained clean.
- KOIZUMI-175 treats the observed left-right camera reversal as board
  orientation, not a CLI display concern. The fix belongs in firmware camera
  sensor setup via horizontal mirror correction so the corrected JPEG is what
  reaches `/stackchan/<device_id>/device/camera/chunks`. The next hardware
  capture after flashing should verify that text or an asymmetric marker appears
  in the expected orientation; if it is still reversed, flip the firmware
  horizontal mirror value instead of adding CLI post-processing.
- The first KOIZUMI-175 hardware check with horizontal mirror enabled was a
  false positive: `tmp/stackchan_camera_koizumi175_mirror.jpg` was 8267 bytes
  and the camera command succeeded, but the captured label text was still
  mirrored. Treat `set_hmirror(..., 1)` as the wrong direction for this board
  orientation and verify again with the firmware mirror value disabled. On
  Windows Docker Desktop, this validation used the host serial TCP bridge via
  IPv4 `192.168.65.254` because `host.docker.internal` resolved to an IPv6
  address that refused the connection in this run.
- After disabling the firmware horizontal mirror value and reflashing the
  camera bring-up profile on 2026-05-29, a direct bridge capture saved
  `tmp/stackchan_camera_koizumi175_fixed.jpg` at 7928 bytes. The center label
  text was readable in the expected orientation, confirming that
  `set_hmirror(..., 0)` is the correct setting for this board.
- KOIZUMI-179 loaded-topic TTS latency follow-up on 2026-05-29 found that
  removing per-window progress waits and suppressing successful intermediate
  topic-load events was not enough: 96 byte ADPCM topic chunks still produced
  `MALFORMED_AUDIO_CHUNK(sequence_gap)`, including `expected_seq=3` with
  received sequences such as 8, 15, 21, and 25. Larger 256/512 byte ADPCM topic
  chunks avoided the visible sequence-gap event but timed out waiting for final
  load completion on the Windows host serial TCP bridge. The older synchronous
  `LoadAudioChunk` service path still completed the same short `say はい` smoke,
  but took roughly one minute because it remained service-round-trip bound.
  A 32-sample reliable history build overflowed DRAM by 925104 bytes, and a
  16-sample input reliable stream build still overflowed DRAM by 121264 bytes.
  The firmware therefore keeps the micro-ROS input stream history at 8 and only
  raises the playback loaded-topic subscription depth to 16. On the flashed
  full firmware, 96 byte ADPCM topic chunks still failed at 0.5 s and 0.75 s
  pacing, but completed at 1.0 s with 32 chunks / 12178 decoded bytes. A 0.9 s
  run with the previous 20 s final completion wait timed out after publish, but
  0.9 s plus a 30 s final completion wait completed three consecutive short
  local TTS smokes with `STACKCHAN_BRIDGE_SAY_COMPLETED=1` and
  `STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=1`. A follow-up 128 byte ADPCM topic
  run reduced the transaction from 32 chunks to 24 chunks and also completed
  three consecutive smokes at 0.9 s / 30 s. Keep 128 byte chunks, 0.9 s pacing,
  and 30 s final completion wait as the conservative defaults until a smaller
  reliable pacing or a different bounded transfer shape is validated. This was
  superseded by the KOIZUMI-180 firmware receive-counter validation below.
- KOIZUMI-160 follow-up on 2026-05-29 tried reducing only the 128 byte loaded
  ADPCM topic pacing. One 0.75 s run and three 0.6 s runs completed with
  `STACKCHAN_BRIDGE_SAY_COMPLETED=1` and
  `STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=1`, but the end-to-end load time did
  not materially improve. Larger 160 byte and 256 byte chunks at 0.6 s timed
  out waiting for the final `audio_playback_load` completion event. An initial
  default env-free smoke after adding bridge publish timing diagnostics showed
  the bridge finished publishing 24 x 128 byte chunks in about 20.8 s, while
  the firmware final completion event arrived about 17.8 s later, so the
  interval-only evidence was not enough to change defaults yet.
- KOIZUMI-180 firmware receive-counter follow-up on 2026-05-29 added
  payload-free `rx_ms`, `gap_ms`, `dec_ms`, and `last_dec_ms` counters to the
  final `audio_playback_load` event, then uploaded the standard full firmware
  to COM3. Three short loaded TTS smokes completed after upload. The first two
  default 0.9 s runs showed bridge publish elapsed about 20.7 s and firmware
  `rx_ms` about 20.8 s, with final completion about 0.36 s after bridge publish
  completion. A 0.6 s run showed bridge publish elapsed about 13.9 s,
  firmware `rx_ms` about 14.0 s, `gap_ms` about 690 ms, and final completion
  about 0.32 s after bridge publish completion. At that point, 128 byte ADPCM
  chunks, a 30 s final completion wait, and 0.6 s loaded-topic publish pacing
  were the conservative validated defaults.
- KOIZUMI-180 follow-up on 2026-06-01 fixed host serial TCP partial writes and
  firmware loaded-playback speaker queue handling, then revalidated the same
  target phrase `今日は電気をたべたよ` over COM3. With 128 byte ADPCM chunks
  and `STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC=0.05`, both
  the one-shot topic path and the carousel path completed. The target
  phrase used 106 chunks, 13,493 encoded bytes, 53,958 decoded bytes, and
  completed in about 10-11 s instead of the previous 68 s paced run. At that
  point, the loaded-topic publish interval default stayed at 0.05 s for this
  validated host serial path; slower values remained useful only for transport
  diagnostics.
- 2026-06-02 detailed-spoken-explanation follow-up rechecked the same COM3
  host-serial loaded-topic path for natural multi-sentence speech. With 128
  byte ADPCM chunks, `STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC=0.02`
  timed out at 21/127 loaded chunks, and `0.03` timed out at 76/122 loaded
  chunks. `0.04` completed a short waited `say` with 125 chunks, 15,875
  encoded bytes, and 63,486 decoded bytes. Use 0.04 s as the normal
  loaded-topic pacing for this validated path; 0.03 s and faster remain
  diagnostic-only until repeated hardware smokes prove reliability.
- A follow-up two-sentence `say` smoke on 2026-06-02 showed that splitting
  already-fit synthesized audio at a punctuation pause can be worse than one
  loaded transaction. The bridge accepted the one CLI command but internally
  loaded a later segment with a derived segment command id; the observed later
  segment reached `audio_playback_load complete=true` at 58 loaded chunks and
  29,260 decoded bytes, but the CLI had already returned recoverable
  `TIMEOUT`. Treat this as evidence that the normal path should keep
  short one-phrase synthesized TTS as one loaded transaction when it already
  fits the selected loaded payload limit. Longer multi-phrase speech may still
  use bridge-internal audio segmentation at natural silence boundaries; the
  important contract point is that Codex and users still send one public `say`
  command. This was a transport-completion finding only; audible naturalness
  still needs operator-listening validation.
- After rebuilding `stackchan_bridge` and restarting the host serial TCP
  bridge, the same smoke no longer produced a derived segment command id. The
  full utterance stayed one loaded transaction, proving the split-condition
  fix. The run still timed out: the single transaction reported 116 loaded
  chunks and 59,234 decoded bytes, with observed receive progress only reaching
  roughly 80 buffered chunks after about 111 s of firmware receive time. This
  separates the issues: avoidable internal segmentation is fixed, but the
  current host-serial loaded-topic transfer can still be too slow for even a
  short two-sentence spoken paragraph. Do not treat this as an audible-quality
  pass.
- After flashing firmware with a small loaded-topic future-chunk buffer, a
  fire-and-wait diagnostic run of the same short two-sentence `say` command
  still rejected the load with `MALFORMED_AUDIO_CHUNK(sequence_gap)`: firmware
  had accepted `seq0`, was still waiting for `expected_seq=1`, and then
  observed future chunks as far ahead as `received_seq=11` and later. This
  proves the remaining failure is transport ordering/backlog after one external
  `say` command, not Codex splitting the phrase into multiple commands. The
  firmware loaded-topic future window was widened to 24 small chunks for the
  128 byte ADPCM serial path before the next smoke. This remains a
  transport-completion finding only; audible naturalness still needs
  operator-listening validation after playback completes.
- With the 24-slot window and inclusive boundary fix flashed, another
  fire-and-wait diagnostic run still rejected early: firmware reached only
  `expected_seq=2` before seeing future chunks at `received_seq=27` and later.
  This shows the no-progress full-payload topic burst can create backlog far
  beyond a bounded device ordering cushion. The next corrective direction is
  bridge-internal natural audio segmentation and bounded segment loading under
  one public `say`, not unbounded firmware RAM growth.
- After adding bridge-internal natural audio segmentation, the same public
  `say` generated a first firmware-facing segment of 58 chunks and 29,260
  decoded bytes, proving the public command stayed one request while the bridge
  split the audio internally. That first segment still rejected under
  fire-and-wait topic diagnostics: firmware reached `expected_seq=18` and then
  saw `received_seq=43`, again one chunk beyond the 24-slot future window. The
  loaded-topic future window was widened to 32 small chunks for the next smoke;
  this is still a transport/backlog experiment, not an audible-quality pass.
- With the 32-slot future window flashed, the same public `say` still rejected
  under no-progress full-burst diagnostics. The first internal segment remained
  58 chunks / 29,260 decoded bytes; firmware buffered future chunks while
  waiting near `expected_seq=9`, then rejected `received_seq=42`, one chunk
  beyond the bounded future window. This confirms the fix is not more firmware
  RAM. The bridge loaded-topic path now routes progress-timeout-zero diagnostics
  through the existing bounded window carousel instead of publishing the whole
  segment as one burst. This is a transport-completion correction only;
  audible naturalness still needs an operator-listening pass.
- A follow-up smoke after that bridge change rebuilt `stackchan_bridge` and ran
  a short two-sentence `say` with progress timeout zero. The public command
  stayed one `say`, and the bridge used an internal segment with 51 chunks /
  25,644 decoded bytes through the bounded-window carousel. It did not fail
  with a current-command `sequence_gap`; instead, the load timed out at 17/51
  chunks. Treat this as progress from burst-ordering failure to a remaining
  serial transfer throughput/progress-loop issue. This is still not an
  audible-quality pass.
- A later diagnostic run with anchor repeats showed the reset `seq0` could be
  accepted, but `seq1` then failed to reach firmware and the load timed out at
  1/51 chunks. The bridge-side playback chunk publisher had only reliable
  depth 8 while the carousel could publish anchor repeats plus an 8-chunk
  lookahead window. The bridge publisher history was increased to 64 and the
  carousel now sends only `seq0` until the topic session starts, then resumes
  repeating the current expected sequence before the lookahead window. This
  protects the session-start anchor without starving later sampled progress
  events; it still needs a clean hardware smoke and an operator-listening pass.
- The next smoke rebuilt `stackchan_bridge` with bridge-side reliable depth 64
  and the sampled-progress-aware carousel. The same short two-sentence public
  `say` still timed out, but progressed to 19/51 chunks instead of 1/51. Events
  showed sampled progress from `seq0`, then `seq7`, then later buffered counts
  around 9, 11, 16, and 19 chunks, with future chunks observed beyond the
  missing expected sequence. This confirms the bridge is again feeding
  lookahead, but the current host-serial topic path still cannot reliably
  deliver the missing expected sequence quickly enough for natural spoken
  explanations. Do not count this as transport completion or audible quality.
- The next bridge change added a bounded missing-anchor service fallback:
  after the same expected sequence remains stuck for four carousel passes, the
  bridge may send only that chunk through the existing load service, then
  continue the topic carousel. This keeps the public command as one `say` and
  keeps topic loading as the primary payload path, while avoiding a full
  per-chunk service ACK fallback. Validate with hardware before treating it as
  transport-complete, and still require operator listening for naturalness.
- 2026-06-02 follow-up validation found that the fallback did not complete on
  the K151 serial path: the bridge no longer crashed when it converted internal
  segment metadata back to ROS `Time`, but the one-chunk load-service recovery
  timed out. A follow-up with 256 byte ADPCM topic chunks and service recovery
  disabled also timed out at the first segment. Keep the service recovery
  disabled by default and treat it as diagnostic-only until a focused hardware
  run proves it works without leaving the firmware loaded-playback session
  stuck. This still supports the design direction that long public `say`
  commands should be split internally after TTS, not split into multiple public
  commands.
- The bridge now treats failed TTS loaded preload as an internal transport
  failure and falls back to the normal PCM streaming relay for the same public
  `say` command. This is intended to reduce "wait, then fail" behavior while
  preserving the user-facing single-utterance contract. It still needs hardware
  smoke validation and operator listening before counting detailed natural
  speech as complete.
- A 2026-06-02 smoke with the normal loaded-topic progress timeout showed that
  the first internally split loaded segment could complete and play, but the
  second segment preload extended the public `say` past the CLI timeout. Later
  streaming fallback trials also failed to carry the next PCM chunk reliably on
  the same serial path. The bridge therefore keeps multi-segment loaded
  playback as the normal long-speech direction and uses a smaller default split
  target so first audio can start earlier; streaming remains a fallback when
  loaded preload fails before playback starts.
- A follow-up smoke confirmed that the streaming relay path was entered, but
  firmware rejected the first PCM chunk as `UNSUPPORTED_FEATURE` when the TTS
  audio had been synthesized at 8 kHz for loaded-preload reduction. The bridge
  now normalizes streaming fallback audio back to baseline 16 kHz PCM while
  keeping 8 kHz available for loaded ADPCM diagnostics.
- After the 16 kHz streaming normalization, firmware accepted the first PCM
  chunk but timed out waiting for the next pull response while the bridge still
  preferred topic NACK retries. The bridge now answers prebuffered TTS pull
  requests directly from its local buffer instead of waiting through NACK
  retries.
- A later long-speech smoke entered the streaming relay with all synthesized
  chunks buffered, but the bridge still attempted the command-audio
  loaded-preload wait before starting the firmware playback action. The bridge
  now skips that second preload wait for TTS streaming fallback, preserving one
  public `say` while splitting only the synthesized audio transport internally.
  The next smoke reached firmware playback action acceptance and the first 16
  kHz PCM chunk was accepted, but the mixed topic-window plus pull fallback
  still missed the next chunk deadline and ended in `pull_response_timeout`.
  A pull-led trial also missed the same service-response deadline and returned
  `AUDIO_UNDERRUN`, so per-chunk service delivery should not become the default.
  A follow-up trial that skipped the playback-topic subscription-count wait also
  still missed `seq1` and produced late `chunk_without_active_goal` events.
  Keep these as negative transport findings; the retained bridge fix is to
  avoid re-running loaded-preload wait once TTS has already fallen back to
  streaming.
- A diagnostic run with explicit multi-segment loaded playback confirmed that
  the first segment can load and play under one public `say`, and that the next
  segment begins with a derived segment command id. The run still timed out
  before all segments completed, so this is transport progress rather than an
  audible-quality pass. The default split target was reduced to 16 KiB decoded
  PCM to favor earlier first audio and shorter loaded transfers per segment.
- The next bridge-side corrective step added progressive loaded TTS for
  naturally punctuated short sentences. This keeps one public `say` action but
  lets the bridge synthesize, load, and play the first sentence-like fragment
  before waiting for the full paragraph TTS result. The fast-start path uses
  hard punctuation only, not comma or particle fallback splitting, because those
  fallback cuts sounded like chopped speech in earlier operator feedback. This
  still needs K151 smoke validation and an operator-listening pass before it can
  count as natural detailed speech.
- K151 smoke validation of that progressive path confirmed the bridge entered
  the intended one-public-`say` / internal-segment route: the firmware-facing
  command ids used derived `-s01` and `-s02` suffixes, `s01` reached loaded
  topic completion, the playback action was accepted, and speaker frames were
  queued. The smoke still returned a public `say` timeout before all internal
  segments completed. This proves the external command contract is now right,
  but the loaded-topic transfer is still too slow for natural detailed speech
  on the current host-serial path.
- A diagnostic run with 256 byte ADPCM loaded-topic chunks and a wider progress
  window did not fix the latency; progress stalled at the first segment's early
  window and the bridge then timed out. The bridge now treats an explicit
  progressive first-segment load failure as the same public `say` failure rather
  than falling through to a second full-utterance TTS/load attempt, because that
  fallback only made the user wait longer. A follow-up service-load diagnostic
  also exceeded the outer command timeout, so neither 256 byte topic chunks nor
  service-load delivery should be promoted to the default path from this
  evidence.
- A short one-sentence `say` smoke after the one-phrase split fix completed
  without derived `-s01` / `-s02` segment command ids. The public command id
  stayed on the loaded playback transaction, `tts_finished`,
  `loaded_playback_started`, and `speaker_frame_queued` were observed, so the
  bridge no longer splits a single natural sentence merely to shorten the
  transport. The run still needed about 36.8 s of firmware receive time for
  28 loaded topic chunks / 14,244 decoded bytes. This is useful contract
  evidence, but it is not a natural detailed-speech pass; the remaining issue
  is loaded-topic transfer latency on the current host-serial path.
- After flashing the firmware that samples loaded-topic progress events, the
  same short `元気だよ。` smoke still completed as one public `say` without
  derived segment ids. It used 28 loaded topic chunks / 14,244 decoded bytes and
  still needed about 37.9 s of firmware receive time, with sampled progress at
  chunks 1, 8, 16, 24, and 28. This proves duplicate progress-event suppression
  reduced event volume but did not fix loaded-topic receive latency.
- A follow-up two-sentence `say` smoke, still one public `say`, completed with
  progressive internal segments `-s01` and `-s02`. The first internal segment
  loaded 53 chunks / 26,980 decoded bytes in about 71.5 s and played; the
  second loaded 37 chunks / 18,512 decoded bytes in about 50.7 s and played,
  followed by `tts_finished` for the original public command id. This validates
  the command contract and internal sequencing, but the operator-facing delay is
  still far too long for natural detailed speech. The observed per-window
  receive gaps remained around 1.1 s, so the next firmware experiment suppresses
  unrelated low-rate runtime telemetry during incomplete loaded audio loads.
- After flashing that runtime-telemetry suppression change, the same short
  `元気だよ。` smoke completed with the one public command id and loaded 28
  chunks / 14,244 decoded bytes in about 1.12 s instead of about 37.9 s. The
  sampled receive gaps dropped from roughly 1.1 s to tens of milliseconds. A
  two-sentence public `say` then completed with progressive internal `-s01` and
  `-s02` segments: `s01` loaded 53 chunks / 26,980 decoded bytes in about
  2.48 s, and `s02` loaded 37 chunks / 18,512 decoded bytes in about 1.94 s,
  followed by `tts_finished` for the original public command id. This is the
  first K151 evidence that the single public `say` plus bridge-internal
  sentence segmentation can be fast enough for natural short explanations on
  the host-serial path. Audible quality and perceived pause naturalness still
  require an operator-listening pass.
- A follow-up bridge rebuild changed progressive text segmentation to group
  adjacent short sentence-like fragments before synthesis, and changed the
  normal loaded-TTS path to keep any already-fit utterance as one loaded
  transaction. The K151 smoke for
  `今日は電気をたべたよ。元気が出たよ。` then completed as one public command
  id with no derived `-s01` / `-s02` loaded-playback ids. Firmware received one
  loaded transaction of 98 chunks / 49,946 decoded bytes in about 4.32 s,
  followed by `tts_finished`, `loaded_playback_started`, and
  `speaker_frame_queued`. This removes the artificial reload pause for short
  connected two-sentence utterances while preserving the single public `say`
  contract. Longer detailed explanations may still be grouped internally when
  they exceed the configured progressive text segment size, and perceived
  naturalness still needs an operator-listening pass.
- A longer four-sentence explanation smoke then exposed a validation helper
  gap: `STACKCHAN_TTS_PROGRESSIVE_TEXT_SEGMENT_MAX_CHARS` was not passed into
  the Docker smoke container, and the first text group could exceed the 32 KiB
  encoded loaded payload buffer. In that state the bridge fell back to full
  utterance TTS and then split the synthesized audio into 10 loaded playback
  segments, including a final 243 chunk / 124,172 decoded-byte segment. That
  completed as one public `say`, but it is not the intended natural detailed
  speech path.
- The smoke helper now passes the progressive text controls through to the
  container, and the default progressive group bound is 32 characters. With
  `STACKCHAN_TTS_PROGRESSIVE_TEXT_SEGMENT_MAX_CHARS=32`, the same
  four-sentence explanation completed as one public `say` using four
  sentence-sized progressive loaded TTS groups instead of the full-audio
  10-segment fallback. The groups loaded as 120 chunks / 61,228 decoded bytes
  in about 5.57 s, 140 chunks / 71,656 decoded bytes in about 7.46 s,
  145 chunks / 73,898 decoded bytes in about 7.79 s, and 149 chunks /
  75,864 decoded bytes in about 7.98 s, followed by `tts_finished` for the
  original public command id. The smoke phase took about 70 s versus about
  93 s for the unintended 10-segment full-audio fallback. This is transport
  evidence that detailed speech now uses one public command with internal
  sentence groups; audible naturalness still needs an operator-listening pass.
- A diagnostic repeat with
  `STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC=0.03` also
  completed the four progressive groups, but it reported bridge liveness
  timeouts and the smoke phase grew to about 122 s. Keep 0.04 s as the standard
  loaded-topic pacing on this host-serial path unless repeated hardware smokes
  prove a faster value is reliable and improves end-to-end audible behavior.
- A follow-up bridge smoke added PC-side TTS prefetch for progressive groups:
  after each group is loaded and before it is played, the bridge starts
  synthesizing the next group in a background worker. The same four-sentence
  explanation still completed as one public `say` with four sentence-sized
  progressive groups, emitted `tts progressive loaded playback synth prefetch`
  for segments 2, 3, and 4, and avoided the full-audio 10-segment fallback.
  The smoke phase was about 69 s, similar to the previous 70 s because the
  dominant remaining wait is serialized loaded-topic transfer, not local TTS
  synthesis. This is a small naturalness improvement because inter-group gaps
  no longer need to include next-group synthesis time, but audible naturalness
  still requires operator listening.
- A direct comparison with `STACKCHAN_TTS_LOADED_PLAYBACK=0` showed that the
  streaming relay is still not a usable long-form speech replacement on this
  host-serial path. The same four-sentence explanation buffered 3,708 small
  streaming chunks and entered the relay, but firmware pull responses stalled
  with repeated `pull_response_timeout`; `stackchanctl say --wait` returned
  `TIMEOUT` and no `tts_finished` event was observed. Do not route normal
  detailed speech to the streaming relay until a separate relay fix proves
  continuous playback completion.
- A loaded-progressive diagnostic with
  `STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES=256` also failed on the
  first progressive group. Firmware progress stopped around sequence 7 and the
  bridge exhausted three progress retries, returning `TIMEOUT` without
  `tts_finished`. Keep 128 byte ADPCM loaded-topic chunks as the standard for
  the current host-serial path. The remaining operator-facing pause is the
  serialized loaded-topic transfer between progressive groups, not TTS
  synthesis or public command splitting.
- The bridge then changed progressive text grouping from fixed character-sized
  groups to synthesized-size-aware candidate grouping. With
  `STACKCHAN_TTS_PROGRESSIVE_TEXT_SEGMENT_MAX_CHARS=64`, the same four-sentence
  explanation first considered larger candidate groups, then fell back to
  single-sentence groups when the paired candidates did not fit the encoded
  loaded payload buffer. The public `say` still completed, `tts_finished` was
  observed, and the logs showed `source_fragments=1-1/4` through
  `source_fragments=4-4/4`. This preserves the option to merge shorter
  adjacent sentences when they really fit, without falling through to the
  unintended full-audio 10-segment fallback.
- A follow-up liveness fix updates bridge liveness from firmware events and
  suppresses `device_disconnected(liveness_timeout)` while a media action is
  active. The same four-sentence loaded-progressive smoke completed with no
  `device_disconnected` or `liveness_timeout` events in the filtered output.
  This removes a distracting bridge-status glitch during long speech playback;
  it does not remove the audible serialized transfer pauses between loaded
  groups.
- An operator-listening sample command then used one public `say` with
  `--face happy --motion cheerful --after-face happy` and three short
  explanation sentences:
  `今の設定では、一回の発話の中で文を自然にまとめるよ。大きすぎる文は中で分けて、次の音声も先に準備するよ。だから詳しい説明でも、できるだけつながって聞こえるようにしたよ。`
  The smoke completed with the face, motion, and after-face hints present in
  CLI JSON, `tts_finished` observed, no filtered `device_disconnected` /
  `liveness_timeout` events, and three progressive sentence-sized loaded
  groups. Those groups loaded 158 chunks / 80,618 decoded bytes in about
  7.91 s, 155 chunks / 79,078 decoded bytes in about 7.29 s, and 157 chunks /
  80,018 decoded bytes in about 8.61 s. This is the current listening-candidate
  configuration for "detailed but natural" speech; whether the inter-group
  transfer pauses are acceptable still requires the operator's listening
  verdict.
- A more speech-compressed listening sample then used one public `say` with
  `--face happy --motion cheerful --after-face happy` and:
  `一回で話すよ。長い説明は中で分けるよ。待ちを減らしてつなぐよ。`
  The dynamic progressive path grouped all three source sentences into one
  loaded playback transaction with the original public command id, not a
  derived `-s01` segment id. The run observed `loaded_playback_started`,
  `speaker_frame_queued`, and `tts_finished`; the face, motion, and after-face
  hints were present in CLI JSON. The single loaded transaction used
  184 chunks / 94,150 decoded bytes and loaded in about 9.10 s; the smoke phase
  took about 31 s. This is the current best listening candidate for a detailed
  but natural spoken summary: compact enough to avoid inter-group transfer
  pauses while still explaining the behavior.
  Count this candidate as complete only after an operator-listening verdict.
  The required transport evidence is `result_state=COMPLETED`,
  `STACKCHAN_BRIDGE_SAY_TTS_FINISHED_SEEN=1`, observed
  `loaded_playback_started` and `speaker_frame_queued`, the original public
  command id on the single loaded transaction with no derived `-s01` segment
  id, and no filtered `device_disconnected` or `liveness_timeout` event. The
  required listening evidence is that the speech is intelligible, volume is
  acceptable, no word or sentence is truncated, phrase-level timing does not
  sound chopped, and the initial load delay feels acceptable for a physical
  avatar answer that also carries face and motion expression. If the operator
  reports unnatural waiting, first shorten the spoken summary toward 20-25
  Japanese characters and leave the detailed explanation in text. If the
  operator reports unclear audio or poor volume, treat that as TTS/audio tuning
  rather than a command-splitting issue. If audible gaps appear inside the
  summary, verify the run stayed one loaded transaction and did not create
  derived segment command ids before changing the Codex skill wording.
- A repeat smoke of the same speech-compressed candidate on 2026-06-02 used
  the same one public `say` with face, motion, and after-face hints. The CLI
  returned `result_state=COMPLETED`, with
  `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `STACKCHAN_BRIDGE_SAY_VOICE_PROFILE_SEEN=1`,
  `STACKCHAN_BRIDGE_SAY_FACE_HINT_SEEN=1`,
  `STACKCHAN_BRIDGE_SAY_MOTION_HINT_SEEN=1`, and
  `STACKCHAN_BRIDGE_SAY_AFTER_FACE_SEEN=1`. Firmware events showed the single
  loaded transaction for the original public command id progressing to
  `complete=true` at 184 chunks / 94,150 decoded bytes, with receive time about
  8.63 s, followed by playback action events. The smoke checks phase took
  about 30 s. This is another transport pass for one-command compact detailed
  speech; it is still not an audible-naturalness pass until the operator
  records the listening verdict.
- A shorter candidate then tested the same meaning without increasing speech
  speed:
  `詳しい話は一回で。中で分け、待ちを減らすよ。`
  Offline synthesis at 8 kHz with the same VOICEVOX tuning produced 72,346 PCM
  bytes, about 4.52 s of audio, compared with 94,150 PCM bytes / about 5.88 s
  for the 31 character candidate. The K151 smoke completed as one public `say`
  with face, motion, and after-face hints; CLI JSON reported
  `result_state=COMPLETED`, and the smoke reported
  `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `STACKCHAN_BRIDGE_SAY_VOICE_PROFILE_SEEN=1`,
  `STACKCHAN_BRIDGE_SAY_FACE_HINT_SEEN=1`,
  `STACKCHAN_BRIDGE_SAY_MOTION_HINT_SEEN=1`, and
  `STACKCHAN_BRIDGE_SAY_AFTER_FACE_SEEN=1`. Firmware loaded-topic events used
  the original public command id, reached `complete=true` at 142 chunks /
  72,346 decoded bytes, and reported about 6.62 s receive time; the smoke
  checks phase took about 27 s. Treat 20-25 Japanese characters as the current
  better target for compact detailed speech when initial waiting is the main
  naturalness risk. This remains a transport pass until the operator records
  intelligibility, volume, truncation, and perceived-wait verdicts.
- A still shorter 20 character candidate preserved the same user-facing
  decision without increasing speech speed:
  `詳しく話すよ。中で分けて待ちを減らすよ。`
  Offline synthesis at 8 kHz with the same VOICEVOX tuning produced 56,842 PCM
  bytes, about 3.55 s of audio. The K151 smoke completed as one public `say`
  with face, motion, and after-face hints; CLI JSON reported
  `result_state=COMPLETED`, and the smoke reported the expected
  `STACKCHAN_BRIDGE_SAY_*` completion and hint markers. Firmware loaded-topic
  events used the original public command id, reached `complete=true` at
  112 chunks / 56,842 decoded bytes, and reported about 5.19 s receive time;
  the smoke checks phase took about 23 s. This is the best transport candidate
  so far for "detailed but natural" spoken summaries: it keeps the speech
  detailed enough to explain the behavior, while leaving full technical detail
  in text. It is still not an audible-naturalness pass until the operator
  records intelligibility, volume, truncation, and perceived-wait verdicts.
- The same candidate was then wired into the smoke helper as
  `--say-naturalness-check`, which sets that text and default
  `--face happy --motion cheerful --after-face happy` hints unless explicitly
  overridden. A K151 repeat run with the flag completed as one public `say`;
  CLI JSON reported `result_state=COMPLETED`, `text_length=20`, and the
  expected face, motion, and after-face hint fields. Firmware loaded-topic
  events again used the original public command id, reached `complete=true` at
  112 chunks / 56,842 decoded bytes, and reported about 5.29 s receive time;
  the smoke checks phase took about 24 s. Use this flag for repeated
  naturalness checks so the spoken text stays comparable across runs. The
  helper still prints the operator-listening gate as unrecorded; the run remains
  a transport pass, not an audible-naturalness pass, until a human listening
  verdict is recorded.
- After fixing the progressive `say` path to call the hard-punctuation-only
  progressive splitter, a no-`--skip-build` K151 repeat rebuilt
  `stackchan_bridge` and completed the same `--say-naturalness-check` as one
  public `say`. The run reported `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `text_length=20`, and the expected voice, face, motion, and after-face
  markers. Firmware loaded-topic events used the original public command id and
  reached `complete=true` at 112 chunks / 56,842 decoded bytes with about
  5.24 s receive time; the smoke checks phase took about 24 s after a 4 s ROS
  package rebuild. This proves the corrected source tree still passes the
  transport path. It is still not an audible-naturalness pass until an operator
  listening verdict is recorded.
- After adding the naturalness pass rerun hint, another K151
  `--say-naturalness-check` completed as one public `say` with
  `STACKCHAN_BRIDGE_SAY_COMPLETED=1`, `text_length=20`, and the expected voice,
  face, motion, and after-face markers. ROS sources were unchanged, so the
  helper reused the current symlink install rather than a stale install. Firmware
  loaded-topic events again used the original public command id and reached
  `complete=true` at 112 chunks / 56,842 decoded bytes with about 5.16 s receive
  time; the smoke checks phase took about 24 s. This confirms the post-hint
  source path still passes transport and emits the listening-record workflow, but
  it remains unrecorded audible quality until an operator verdict is captured.
- The operator then listened to the same `--say-naturalness-check` candidate on
  K151 and judged the audible result acceptable. The unrecorded listening run
  completed as one public `say` with `STACKCHAN_BRIDGE_SAY_COMPLETED=1`,
  `text_length=20`, expected voice/face/motion/after-face markers, a loaded
  topic completion at 112 chunks / 56,842 decoded bytes, about 5.41 s receive
  time, and a smoke checks phase around 24 s. The first attempt to record
  `--say-operator-listening-verdict pass` is not valid audible-pass evidence:
  the `say` command was rejected with `UNSUPPORTED_FEATURE` /
  `speaker begin failed`, `STACKCHAN_BRIDGE_SAY_COMPLETED=0`, and no
  `tts_finished` observation. After a 10 s settle delay, the same pass-record
  command completed with smoke exit 0. That successful retry reported
  `result_state=COMPLETED`, command id
  `e7189767-53c3-49c0-90a0-096596930c8e`,
  `STACKCHAN_BRIDGE_SAY_COMPLETED=1`, expected voice/face/motion/after-face
  markers, loaded-topic `complete=true` at 112 chunks / 56,842 decoded bytes
  with about 5.12 s receive time, `--say-operator-listening-verdict pass`, and
  issue `none`. Count only this successful retry, together with the operator's
  "OK. 許容範囲内" listening judgment, as the audible-naturalness pass for the
  compact detailed spoken summary.
- KOIZUMI-178 focused playback follow-up on 2026-05-29 found that the current
  bridge can convert a 500 ms `stackchanctl audio play --wait` tone into the
  loaded playback transaction before starting firmware playback. The run used
  32 loaded topic chunks / 16000 decoded bytes, completed with
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_OK_SEEN=1`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_TIMEOUT_SEEN=0`, and
  `STACKCHAN_SENSOR_SWEEP_AUDIO_PLAY_SETTLED_SEEN=1`. Bridge normal logs now
  report loaded audio `format_id` instead of codec names so the redaction scan
  does not match `pcm` inside a codec label; the same playback-only validation
  ended with `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0`. Follow-up
  camera and audio-capture-only checks after playback did not report
  `FIRMWARE_BUSY`; camera reported a capture failure and audio capture reported
  a QoS mismatch / no-PCM-chunks failure, which should be tracked separately
  from playback relay gate release.
- KOIZUMI-181 audio capture QoS follow-up on 2026-05-29 split
  stackchanctl audio chunk QoS by direction. Playback command chunks keep the
  reliable command-payload QoS, while capture subscribes to
  `/stackchan/<device_id>/device/audio/chunks` with best-effort, volatile,
  keep-last-8 QoS to match the firmware observation topic. A standard/full
  firmware `audio-capture-only` smoke over the host serial TCP bridge completed
  with `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_EXIT=0`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OK_SEEN=1`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OUTPUT_BYTES=684`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_FIRMWARE_BUSY_SEEN=0`, and
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0`. No incompatible QoS
  warning was observed in this run. A follow-up standard/full firmware
  all-media smoke with 500 ms waited playback then capture then camera also
  completed with playback, audio capture, and camera capture all reporting
  `OK_SEEN=1`, `FIRMWARE_BUSY_SEEN=0`, and
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0`; the audio capture WAV
  was 684 bytes and the camera JPEG was 6393 bytes.
- KOIZUMI-195 on 2026-06-01 keeps microphone capture observation-only while
  making the receive path terminal. The bridge now queues speech audio chunks
  onto a bounded worker so ROS callbacks do not wait on VAD, echo control, or
  local ASR. Firmware capture feedback is throttled and a capture-session
  watchdog emits structured `AUDIO_CAPTURE_FAILED` / `audio_capture_failed`
  instead of letting accepted goals hang until the bridge reports a generic
  timeout. After COM3 upload, a 0.02 s audio-capture-only smoke still completed
  with `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_EXIT=0`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OK_SEEN=1`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_OUTPUT_BYTES=684`,
  `STACKCHAN_SENSOR_SWEEP_AUDIO_CAPTURE_FIRMWARE_BUSY_SEEN=0`, and
  `STACKCHAN_SENSOR_SWEEP_LOG_SENSITIVE_PAYLOAD_SEEN=0`. A 1.0 s quiet capture
  no longer surfaced a generic bridge timeout; it returned recoverable
  `AUDIO_CAPTURE_FAILED` with `message=audio capture session timed out` and an
  `audio_capture_failed` event. A camera-only run after that failure completed
  with `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_EXIT=0`,
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_OK_SEEN=1`, and
  `STACKCHAN_SENSOR_SWEEP_CAMERA_CAPTURE_FIRMWARE_BUSY_SEEN=0`, proving the
  failure path releases media arbitration. A follow-up bridge smoke with
  `--face-check happy` cleared `last_error` and observed
  `STACKCHAN_BRIDGE_SOAK_ERROR_SEEN_1=0`, but still exited non-zero because the
  initial connected-observe wait missed the already connected public status;
  treat that as existing host serial TCP bridge startup flakiness, not as an
  audio-capture terminal-state failure. The remaining non-empty 1.0 s WAV
  success risk is tracked separately as KOIZUMI-196.

## Cleanup

- Save the command transcript and observed result codes in the PR or Linear
  issue.
- Reset temporary maintenance/debug firmware changes before merging production
  code.
