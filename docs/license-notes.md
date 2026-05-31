# License Notes

This project should keep the dependency and reference boundary explicit, especially around M5StackChan firmware and hardware support code.

## Policy

Use the permissive, library-shaped parts of the ecosystem as dependencies. Treat full application firmware repositories as references unless there is a concrete reason to import a small, clearly licensed part.

## Current dependency stance

### `m5stack/StackChan-BSP`

- Role: preferred hardware support dependency for official M5StackChan hardware.
- License: MIT, according to the GitHub repository license metadata and `LICENSE` file.
- Usage: OK to depend on from firmware code.
- Notes: The `1.1.0` release on 2026-05-12 switched the servo driver to `FTServo_Arduino`.

### `m5stack/StackChan`

- Role: reference implementation for factory firmware, remote controller firmware, mobile app, and server.
- License shape: repository-level license metadata is not detected by GitHub, but `firmware/LICENSE` and `remote/code/LICENSE` are currently MIT.
- Usage: OK to read and reference. Avoid vendoring or copying the repository wholesale.
- If code is copied: copy only the smallest necessary part, preserve copyright and MIT license notices, and document why dependency use was not enough.
- Project stance: do not fork this repository as the firmware baseline.

### `stack-chan/stackchan-arduino`

- Role: community reference for Stack-chan behavior and servo abstraction.
- License: MIT.
- Usage: OK as a reference. Do not mix it with `StackChan-BSP` in firmware unless there is a concrete integration reason.

### `stack-chan/stack-chan`

- Role: original community Stack-chan firmware and hardware project.
- License: Apache-2.0.
- Usage: OK as design reference. Avoid copying code into the firmware unless Apache-2.0 notice and compatibility are deliberately handled.

### VOICEVOX Engine

- Role: optional local TTS service for bridge-owned `/stackchan/<device_id>/cmd/say`.
- License shape: external runtime service with its own engine and voice terms.
- Usage: OK to call as an operator-provided local HTTP service. Do not vendor
  the engine, voice libraries, model assets, dictionaries, or character voices
  into this repository without a separate documented license and distribution
  decision.
- Credit: docs, examples, and voice profile config must preserve a
  `required_credit` string and `terms_url` for every distributable profile.
  Character-specific terms may require visible credit in demos or generated
  media, even when local use is free.
- Project stance: expose bridge-owned profile names such as `default`, not raw
  provider IDs, as the normal CLI/MCP selector. The bridge may map a profile to
  a VOICEVOX `speaker_id` locally.

### Local Whisper ASR services

- Role: optional local ASR service for bridge-owned speech recognition after
  VAD has produced a bounded utterance.
- License shape: external runtime service plus separately licensed model
  weights and caches. Server images, model weights, Hugging Face caches, and
  generated transcripts are not repository artifacts.
- Usage: OK to call as an operator-provided local HTTP service. Do not vendor
  ASR servers, model weights, downloaded caches, or generated transcript/audio
  data into this repository without a separate documented license and
  distribution decision.
- Project stance: keep provider endpoints and raw model identifiers inside
  bridge-local configuration. CLI, MCP, public events, and normal logs should
  expose only bounded metadata such as `utterance_id`, confidence, language,
  duration, command id, and structured result/error codes.

### Local audio codec candidates

- Role: optional local compression between the bridge and firmware for
  speech-sized playback payloads.
- IMA ADPCM: preferred first experiment because the decoder can be small,
  integer-only, and carried in-repo after a test-vector and license review.
  Do not copy codec code from FFmpeg, OpenCores GPL examples, or unclear
  snippets. If an upstream implementation is imported, document the exact file,
  copyright, license, and why a tiny in-repo implementation was not enough.
- Espressif `esp_audio_codec`: useful as a reference because it supports
  IMA-ADPCM, G.711, and Opus on ESP32-S3-class targets, but its registry entry
  is marked `Custom` license and the package is much broader than the current
  Arduino/PlatformIO firmware needs. Do not add it as a dependency without a
  separate license and footprint review.
- Opus and Speex: upstream codecs are permissively licensed, but they are not
  the first firmware target because their runtime integration, heap, stack, and
  bitstream framing cost is higher than a small ADPCM decoder. Treat them as
  future alternatives only after the ADPCM path is measured.
- G.711/G.726: acceptable comparison points for low-complexity speech
  compression. G.711 only halves 16-bit PCM payload size, while G.726 needs a
  deeper standard-codec implementation review.
- References checked on 2026-05-27: Microsoft ADPCM overview
  <https://learn.microsoft.com/en-us/windows/win32/xaudio2/adpcm-overview>,
  Opus license <https://opus-codec.org/license/>, Speex license summary
  <https://www.speex.org/fsos/>, and Espressif `esp_audio_codec`
  <https://components.espressif.com/components/espressif/esp_audio_codec/>.

## Practical rules

- Prefer `StackChan-BSP` for hardware access.
- Prefer our own behavior adapter for ROS/micro-ROS command handling.
- Do not vendor full factory firmware, mobile app, server, or remote-control code.
- Do not base this project on a fork of the M5Stack factory firmware.
- Do not depend on X/Twitter mirrors or unofficial reposts as source material.
- Do not commit generated speech audio, bundled TTS models, or provider
  runtime artifacts unless the license and redistribution terms are explicitly
  documented.
- Re-check license state before importing any upstream code, because the official repositories are still active.

## Why this matters

The project goal is to connect Codex to M5StackChan through ROS 2. It should not become a fork of the official firmware or a bundle of unclear upstream code. Keeping the boundary small makes the project easier to maintain, safer to publish, and easier to reason about.
