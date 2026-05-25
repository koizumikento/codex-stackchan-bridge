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
