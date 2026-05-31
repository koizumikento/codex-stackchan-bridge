# Quality Gates

This document defines the quality gates for this repository. These gates are intended to keep the Codex skill, CLI, ROS 2 interfaces, and firmware moving together without relying on hardware for every change.

## Principles

- Every command path must be testable without physical hardware.
- The mock backend and bridge backend must share the same command contract.
- Single-device and multi-device behavior must share the same `device_id` contract.
- Cross-layer contracts must be documented before implementation spreads across packages.
- Safety behavior must be validated at the firmware boundary, not only in the CLI.
- JSON output and structured errors are part of the public contract.
- MCP stdio adapters must keep JSON-RPC on `stdout` and logs on `stderr`.
- Media completion and audible quality are different gates. `tts_finished`,
  action completion, and firmware drain events prove transport/software
  completion; they do not prove that speech was intelligible to an operator.

## Required Gates By Area

### Documentation

Required when changing architecture, interfaces, safety behavior, dependencies, or command semantics:

- Update the relevant document under `docs/`.
- Keep package READMEs focused on package-local setup and link back to `docs/`.
- Update `AGENTS.md` when a decision should guide future agents.

### stackchanctl

Required for CLI changes:

- Unit tests for command parsing and validation.
- Mock backend tests for deterministic JSON.
- Error-shape tests for ROS `error_code` and CLI `error.code` mapping, plus `message` and `recoverable`.
- Metadata tests for `device_id`, `command_id`, `source`, `created_at`, and `priority`.
- Device selection tests for default device and `--device <device_id>`.
- Success semantics tests for `ACCEPTED`, `COMPLETED`, `REJECTED`, and `TIMEOUT` states.
- Human output remains compact; `--json` remains machine-readable.
- Event command tests cover `events list`, `events next`, `events clear`, empty
  event results, cursor-only clear behavior, and deterministic mock events.
- Transcript command tests cover explicit lookup by `utterance_id` and
  structured expiry/not-found failures.
- Power command tests cover strict JSON output, unsupported numeric values as
  `null`, stale telemetry, unsupported hardware, and bridge/mock shape parity.
- Audio command tests cover accepted playback/capture, timeout, underrun,
  overrun, unsupported firmware, malformed chunk, disconnect mid-stream, and
  absence of PCM, speech text, and transcript text in CLI JSON or diagnostics.
- Say/TTS tests cover provider-disabled, unknown voice profile, local provider
  synthesis failure, audio playback failure, timeout, mock metadata parity, and
  absence of speech text, provider request bodies, raw provider speaker IDs,
  PCM, and transcript text in CLI JSON, MCP results, events, and diagnostics.
- Camera command tests cover QVGA JPEG metadata, `quality=1..95`, max 96 KiB,
  chunk reassembly, timeout, oversized payload handling, unsupported firmware,
  first-frame freshness after camera bring-up, firmware-owned orientation
  correction, and absence of image bytes/base64 in CLI JSON or diagnostics.
- Maintenance-separation tests prove normal CLI/MCP/Codex command groups cannot
  reach calibration writes, raw hardware controls, NVS import/export, or
  maintenance unlocks.
- Raw sensor command tests cover stale telemetry, saturated sensors, missing
  calibration, NaN-to-null conversion, and per-device separation.
- Face/LED tests cover unknown expression/pattern, timeout, idempotency,
  no unbounded queue growth, `HIGH` preempt behavior, and external `SAFETY`
  rejection.
- Mood command tests cover deterministic mock presets, unknown mood rejection,
  bridge use of existing face/LED/motion facade calls, metadata preservation,
  disconnected/unknown device errors, external `SAFETY` rejection, and absence
  of speech text, PCM, image bytes, raw NFC tag IDs, raw IR codes, and secrets.
- Demo command tests cover default non-media behavior, opt-in say/media flags,
  structured step summaries, unsupported/degraded step handling, media-busy
  diagnostics without payload exposure, bridge/mock parity, and the distinction
  between transport completion and operator-listening audible quality.
- Doctor command tests cover read-only behavior, mock healthy/degraded reports,
  bridge status/capability aggregation, `device_state` versus `result_state`,
  disconnected/unknown/conflict/stale classifications, no maintenance or
  actuation calls, and redaction of speech, audio, image, NFC, IR, provider
  request, and secret payloads.

Required for MCP stdio changes:

- Stdio smoke tests for initialize, `tools/list`, and `tools/call`.
- Tests that `stdout` contains only MCP JSON-RPC frames and diagnostics stay on `stderr`.
- Mock backend tests for deterministic tool results.
- Metadata tests for `device_id`, `command_id`, `source=mcp_agent`, `created_at`, and `priority`.
- Tests that `SAFETY` priority is rejected with the shared structured error shape.
- Tests that rejected commands and timeouts are returned as tool results with `ok=false`, not protocol errors.
- Bridge fake-client tests that preserve the same command/result shape as the mock backend.
- Event observation tools preserve the same `events`/`cursor` shape as CLI JSON
  and return empty event lists as tool results, not MCP errors.
- MCP tools must not return PCM payloads, speech text, transcript text, image
  bytes/base64, raw NFC tag IDs, raw IR codes, or protocol dumps unless a
  separate explicit local diagnostic contract exists.
- MCP must not expose unbounded raw telemetry streams unless a separate
  streaming MCP contract exists; prefer bounded request/response tools and
  existing event/status tools.

### ROS 2 Interfaces

Required for message, service, or action changes:

- Interface definitions build successfully when a ROS 2 Jazzy environment is
  available; otherwise run the repository contract checker and mark the
  `colcon` build unavailable in the change notes.
- New command-bearing interfaces include required metadata.
- Namespaces follow `/stackchan/<device_id>`.
- Firmware-owned resources use full `/stackchan/<device_id>/device/...` names,
  bridge facade commands use `/stackchan/<device_id>/cmd/...`, and public
  bridge-owned status/telemetry/events use `/stackchan/<device_id>/...`
  without `/device`. Bare `/device/...` shorthand is not acceptable in
  interface docs, issue plans, or implementation notes for actual resources.
- Multiple physical devices are separated by `device_id`; fields such as
  `sensor_index` identify multiple sensors within one device only.
- Response/error shapes follow the documented error model.
- Interface changes are reflected in `docs/ros-interface.md`.
- QoS and heartbeat decisions are documented when implementation touches status, events, IMU, audio chunks, or camera paths.
- Event contracts document `/stackchan/<device_id>/device/events`,
  `/stackchan/<device_id>/events`, event query services, ownership, fields,
  bounded payload rules, and event taxonomy.
- Event contracts document redacted/reference handling for NFC/IR identifiers
  and keep IR transmit command behavior out of receive/event-only contracts
  unless a separate `/cmd/ir/...` design exists.
- Sensor and power telemetry contracts document bounded messages, public and
  device-side topic names, low-rate baselines, QoS, stale/error semantics, and
  that raw telemetry is not added to `/status`.
- Audio/camera contracts document resource names, action result/feedback,
  payload/chunk bounds, privacy/redaction rules, and how oversize/malformed
  payloads map to structured errors.

### stackchan_bridge

Required for bridge event changes:

- Event buffer tests cover ordering, capacity, per-device separation, consumer
  cursors, and cursor clear without deleting the ring buffer.
- Event aggregation tests cover firmware event normalization, bridge-origin
  events, duplicate/debounce behavior, and unknown/disconnected/conflict events.
- Redaction tests cover speech transcripts, image/audio payloads, and NFC tag
  IDs in normal logs.
- Redaction tests cover raw IR codes and protocol dumps, firmware/bridge
  diagnostic paths, and public event payloads.
- Transcript store tests cover memory-only behavior, lookup by `utterance_id`,
  and default 10 minute TTL expiry.
- Speech processing tests cover 20 ms chunk to 10 ms frame splitting, VAD
  state transitions, AEC unavailable fallback, playback hangover suppression,
  ASR worker timeout/failure, callback non-blocking behavior, transcript
  redaction, low-confidence suppression, queue overflow/drop behavior, and proof
  that speech/audio events do not emit action-oriented fields or dispatch
  physical commands.
- Power telemetry tests cover latest snapshot storage, stale detection, public
  topic naming, and `device_id` preservation while relaying telemetry.
- Audio routing tests cover command_id/direction separation, no per-chunk ACK
  assumption, overrun/underrun mapping, same-direction `FIRMWARE_BUSY`, media
  action timeout settle gating with previous `command_id` diagnostics, and
  bounded queue behavior.
- TTS routing tests cover local provider selection, VOICEVOX adapter error
  mapping, 16 kHz mono PCM normalization, voice profile config, balanced
  default tuning, event redaction, and forwarding synthesized audio through the
  documented loaded playback path. The default serial TTS payload path must not
  depend on per-chunk service ACK responses; use bounded topic payloads plus a
  transaction-progress/load-complete observation and the playback action result.
  Loaded topic diagnostics may expose redacted sequence counters such as
  expected and received sequence numbers, but must not expose speech text,
  provider request bodies, or PCM/ADPCM payload bytes.
  If loaded topic progress retry is enabled, tests or source inspections must
  preserve the bounded retry limits and the firmware duplicate-chunk
  idempotency rule so retried chunks cannot be decoded twice.
- Smoke helper tests preserve early readiness observations such as
  `firmware_ready` across paginated event queries, especially for long media
  smokes where later event pages may no longer contain startup events. Repeated
  hardware smokes may also count a connected public status sample as a harness
  readiness observation when the firmware was already running before the bridge
  started.
- Camera routing tests cover metadata-only action results, chunk-topic payload
  reassembly, oversize discard, timeout/failure propagation, and no image bytes
  in public observations.
- `perform` remains reserved unless implemented; if implemented, bridge tests
  cover cancel, preempt, timeout, partial failure, per-step result aggregation,
  and prohibition on maintenance/calibration steps.

### Firmware

Required for firmware changes:

- Firmware build-only check passes for the supported board target when a
  PlatformIO/micro-ROS-capable environment is available; otherwise run the
  hardware-free firmware contract checks and mark the PlatformIO build
  unavailable in the change notes.
- Firmware C++ contract harnesses must use safe nominal sample data and fail
  with readable stderr diagnostics rather than CPU trap instructions, so CI
  reports the violated contract instead of only a signal such as `SIGILL`.
- Safety limits remain firmware-owned.
- Calibration storage remains firmware NVS unless a documented decision changes it.
- Disconnect, audio underrun, mic overrun, camera failure, NFC failure, and servo/safety failure behavior remains documented.
- Calibration NVS behavior covers schema version, checksum/corruption
  detection, atomic write or rollback, reset-to-default, and missing/corrupted
  calibration rejection.
- Any change touching hardware control preserves resource arbitration order:

```text
safety > motion stop/neutral > audio capture/playback > command handling > camera > LED/idle
```
- Event estimator changes include contract tests for bounded names and payloads,
  optional `command_id` only for sensor-origin events, device id preservation,
  and separation of raw IMU telemetry from high-level IMU events.
- Touch, proximity, light, remote/IR, and power event additions include
  hardware-free contract tests for event names, bounded payloads, non-blocking
  queue behavior, and safe defaults when hardware is unavailable.
- Audio, camera, raw sensor, face, and LED adapters include bounded queues or
  callback budgets proving they cannot block safety, fault handling, or
  motion-neutral work.
- Firmware normal diagnostics must not print raw `payload_json`, PCM payloads,
  image bytes, raw NFC tag IDs, raw IR codes, or protocol dumps outside an
  explicit local maintenance/debug mode.

### Codex Skill

Required for skill changes:

- Skill calls `stackchanctl`, not raw `ros2` commands.
- Skill behavior works against the mock backend.
- User-facing command timing and failure behavior is documented if it changes.
- Event-policy behavior treats events as observations rather than direct
  commands, fetches transcripts only through explicit transcript lookup after
  `transcript_ready`, and avoids noisy responses to repeated low-value events.
- Skill validation proves speech/audio observations do not automatically call
  `say`, `face`, `motion`, `led`, `audio`, or maintenance commands.
- Skill validation proves routine cues never call maintenance commands, raw
  hardware controls, calibration writes, raw telemetry streams, or undocumented
  face/LED names.

### Rust Companion Workers

Required before adding or expanding Rust workers:

- The hot path or deployment need is measured or clearly documented.
- The worker preserves the same command metadata and error model as the Python CLI.
- The Python CLI can call or supervise the worker through a narrow boundary.
- Setup and failure modes are documented.

## CI Targets

The expected CI shape is:

- GitHub Actions on Ubuntu 24.04.
- Python lint and unit tests for `apps/stackchanctl`.
- Mock backend contract tests.
- Multi-device/default-device contract tests.
- ROS 2 interface contract checks for `ros/stackchan_msgs`; replace or supplement these with `colcon` interface build checks when a ROS 2 Jazzy CI image is available.
- ROS 2 bridge package tests for hardware-free facade logic.
- Containerized ROS 2 smoke for `stackchan_msgs`, `stackchan_bridge`, and the
  no-device `stackchanctl --backend bridge` path.
- Firmware contract checks for `firmware/m5stackchan-microros`; run PlatformIO build-only checks in a PlatformIO/micro-ROS-capable environment.
- Containerized PlatformIO build-only checks for firmware when the pinned
  micro-ROS PlatformIO dependency resolves.

## Hardware-Free Readiness Summary

The practical pre-hardware gate is complete when these checks pass locally or
in CI:

- `uv run --directory apps/stackchanctl python -m unittest discover -s tests`
  for CLI, mock backend, MCP stdio, and Codex skill policy regression.
- `uv run --directory apps/stackchanctl --with ruff ruff check .`.
- `uv run --directory ros/stackchan_bridge --no-project python -m unittest discover -s tests`
  for hardware-free bridge facade, event, speech, telemetry, and redaction
  behavior.
- `uv run --directory ros/stackchan_bridge --no-project --with ruff ruff check .`.
- `uv run --no-project python scripts/check_ros_interfaces.py` for
  `stackchan_msgs` contract shape when a full ROS 2 build is unavailable.
- `uv run python -m unittest discover -s firmware/m5stackchan-microros/tests`
  for firmware contract checks that do not need a board. In CI this includes
  native C++ contract harnesses compiled with the runner toolchain; their
  assertion failures should identify the contract that failed.
- `uv run --no-project python scripts/ros2_container.py smoke` when Docker is
  available, to build `stackchan_msgs` and `stackchan_bridge` in ROS 2 Jazzy and
  verify the no-device bridge path.
- `uv run --no-project python scripts/firmware_container.py build` when Docker
  is available and the pinned PlatformIO/micro-ROS dependencies resolve. If the
  container daemon, PlatformIO toolchain, or pinned dependency is unavailable,
  run the firmware contract tests above and explicitly mark the build check
  unavailable.

Passing these gates does not claim physical behavior works. K151-specific
servo direction, display rendering, LED behavior, audio I/O, camera data, NFC
and IR observations, USB serial passthrough, micro-ROS Agent connectivity, and
disconnect/reconnect behavior remain manual validation items under
`docs/hardware-validation.md`.

Deferred until implementation stabilizes:

- Markdown formatting checks.
- external link checks
- hardware-in-the-loop checks
- release packaging checks

## Manual Validation

Hardware validation is still required for behavior that depends on the physical device, but it should not be the only way to validate a change.

Manual hardware checks should cover:

- The detailed K151 checklist in [hardware-validation.md](hardware-validation.md)
  has been followed or explicitly marked unavailable.
- Face command rendering.
- Motion command safety and neutral behavior.
- Explicit head pose rejects out-of-range values instead of clamping, keeps
  named-motion trajectory limits separate, and covers calibration invalid,
  servo read failure, stale telemetry, and `motion home`.
- LED command behavior.
- Audio playback and capture.
- Camera snapshot.
- NFC/IR/remote event reporting with redacted/reference identifiers in normal
  output.
- IMU raw stream and high-level events.
- Disconnect and reconnect behavior.
- Device event publishing for button, IMU, NFC, audio overrun/underrun, and
  public bridge event visibility through `stackchanctl events`.

## Merge Readiness

A change is ready when:

- The relevant automated gates pass or are explicitly marked unavailable.
- Mock backend behavior still works for affected commands.
- Cross-layer contract changes are documented.
- Safety-related changes include firmware-side validation notes.
- Known limitations are written down instead of left implicit.
