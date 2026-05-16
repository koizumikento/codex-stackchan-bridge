---
name: stackchan-contract-change
description: Contract-change workflow for codex-stackchan-bridge. Use when changing ROS 2 messages, services, actions, topic names, QoS, stackchanctl command behavior, CommandMeta, Result, device_id handling, audio/camera/NFC/IMU contracts, or the bridge facade between CLI, ROS, and firmware.
---

# StackChan Contract Change

Use this skill whenever a change affects more than one layer's understanding of a command, event, status, or payload.

## Read First

1. Read root `AGENTS.md`.
2. Read `docs/ros-interface.md` and `docs/stackchanctl.md`.
3. For message definitions, read `ros/stackchan_msgs/AGENTS.md`.
4. For bridge behavior, read `ros/stackchan_bridge/AGENTS.md`.
5. For firmware-facing behavior, read `firmware/m5stackchan-microros/AGENTS.md`.

## Contract Rules

- Command-bearing interfaces include `device_id`, `command_id`, `source`, `created_at`, and `priority`.
- `device_id` is part of every public command path; `default` is the baseline single-device id.
- Public bridge facade names use `/stackchan/<device_id>/cmd/...`.
- Firmware-side resources use `/stackchan/<device_id>/device/...`.
- `Result.error_code` maps to CLI JSON `error.code`.
- CLI JSON uses `result_state` for command result state and `device_state` for observed device state.
- Command topics are not allowed; use services for quick request/response and actions for long-running work.
- Topics are for state, telemetry, events, and bounded chunks.
- Audio baseline is PCM 16 kHz mono 16-bit, 20 ms chunks by default, 40 ms max when transport overhead matters.
- Camera baseline is QVGA JPEG snapshot only, max 96 KiB.
- NFC reports tag events and IDs; PC/Codex decides meaning.
- IMU exposes raw telemetry plus high-level events.

## Change Checklist

1. Update the interface source of truth first.
2. Update CLI, bridge, firmware, mock backend, and docs to match the same terms.
3. Keep machine-readable JSON stable and explicit.
4. For MCP stdio adapters, preserve stdout JSON-RPC framing and keep logs on stderr.
5. Add or update tests around metadata, structured errors, and mock behavior when implementation exists.
6. Ask `interface-contract-steward` to review if subagents are in use.

If a command cannot be represented in the mock backend, tighten the command contract before implementing it.
