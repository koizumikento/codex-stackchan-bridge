from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Callable, Mapping, TextIO

from stackchanctl.backends import create_backend
from stackchanctl.config import resolve_runtime_config
from stackchanctl.contract import (
    CommandMeta,
    CommandRequest,
    CommandResult,
    CommandType,
    DeviceStatus,
    EventListResult,
    Priority,
    TranscriptResult,
    utc_timestamp,
)
from stackchanctl.mcp_stdio import run_mcp_stdio

CommandIdFactory = Callable[[], str]
Clock = Callable[[], datetime]


VALUE_GLOBALS = {"--backend", "--device", "--timeout", "--priority", "--source"}
FLAG_GLOBALS = {"--json", "--wait"}


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv if argv is not None else sys.argv[1:])


def run_cli(
    argv: list[str],
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    env: Mapping[str, str] | None = None,
    command_id_factory: CommandIdFactory | None = None,
    clock: Clock | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    if env is None:
        env = os.environ
    command_id_factory = command_id_factory or (lambda: str(uuid.uuid4()))
    clock = clock or (lambda: datetime.now(UTC))

    parser = build_parser()
    try:
        args = parser.parse_args(_normalize_global_options(argv))
    except SystemExit as exc:
        return int(exc.code)

    is_mcp = args.command == "mcp"
    runtime = resolve_runtime_config(
        cli_backend=args.backend,
        cli_device=args.device,
        cli_json=args.json,
        cli_source=args.source,
        cli_timeout=args.timeout,
        env=env,
        default_source="mcp_agent" if is_mcp else "human_cli",
    )
    if is_mcp:
        if args.transport != "stdio":
            stderr.write("REJECTED unsupported MCP transport\n")
            return 1
        return run_mcp_stdio(runtime, stderr=stderr)

    if (
        args.command == "events"
        and args.events_command == "tail"
        and args.follow
        and runtime.output == "json"
    ):
        stderr.write("events tail --follow is only supported for human output\n")
        return 2

    priority = Priority(args.priority or Priority.NORMAL.value)
    request = build_request(
        args=args,
        device_id=runtime.device,
        priority=priority,
        timeout=runtime.timeout,
        command_id=command_id_factory(),
        now=clock(),
        source=runtime.source,
    )

    backend = create_backend(runtime.backend)
    try:
        if args.command == "events" and args.events_command == "tail" and args.follow:
            return _run_follow_loop(
                backend,
                request,
                stdout=stdout,
                stderr=stderr,
                poll_interval=args.poll_interval,
            )
        result = backend.execute(request)
        render(result, json_output=runtime.output == "json", stdout=stdout, stderr=stderr)
        if _is_failed_result(result):
            return 1
        return 0
    finally:
        close = getattr(backend, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:  # pragma: no cover - defensive cleanup guard
                stderr.write(f"stackchanctl backend close error: {exc}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stackchanctl")
    parser.add_argument("--backend", choices=("bridge", "mock"))
    parser.add_argument("--device")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=finite_float)
    parser.add_argument("--priority", choices=[priority.value for priority in Priority])
    parser.add_argument("--source")
    parser.add_argument("--wait", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    say = subparsers.add_parser("say")
    say.add_argument("text", nargs="+")

    face = subparsers.add_parser("face")
    face.add_argument("name")

    motion = subparsers.add_parser("motion")
    motion.add_argument("name")

    led = subparsers.add_parser("led")
    led.add_argument("pattern")

    mcp = subparsers.add_parser("mcp")
    mcp_subparsers = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_serve = mcp_subparsers.add_parser("serve")
    mcp_serve.add_argument("--transport", choices=("stdio",), default="stdio")

    audio = subparsers.add_parser("audio")
    audio_subparsers = audio.add_subparsers(dest="audio_command", required=True)
    audio_play = audio_subparsers.add_parser("play")
    audio_play.add_argument("path")
    audio_capture = audio_subparsers.add_parser("capture")
    audio_capture.add_argument("--seconds", type=finite_float, default=3.0)
    audio_capture.add_argument("--output", required=True)

    camera = subparsers.add_parser("camera")
    camera_subparsers = camera.add_subparsers(dest="camera_command", required=True)
    camera_capture = camera_subparsers.add_parser("capture")
    camera_capture.add_argument("--output", required=True)
    camera_capture.add_argument("--quality", type=int, default=80)

    nfc = subparsers.add_parser("nfc")
    nfc_subparsers = nfc.add_subparsers(dest="nfc_command", required=True)
    nfc_subparsers.add_parser("wait")

    imu = subparsers.add_parser("imu")
    imu_subparsers = imu.add_subparsers(dest="imu_command", required=True)
    imu_stream = imu_subparsers.add_parser("stream")
    imu_stream.add_argument("--hz", type=finite_float, default=10.0)

    events = subparsers.add_parser("events")
    events_subparsers = events.add_subparsers(dest="events_command", required=True)
    events_list = events_subparsers.add_parser("list")
    events_list.add_argument("--limit", type=events_limit, default=32)
    events_list.add_argument("--since-event")
    events_next = events_subparsers.add_parser("next")
    events_next.add_argument("--after")
    events_tail = events_subparsers.add_parser("tail")
    events_tail.add_argument("--limit", type=events_limit, default=10)
    events_tail.add_argument("--follow", action="store_true")
    events_tail.add_argument("--poll-interval", type=finite_float, default=1.0)
    events_subparsers.add_parser("clear")

    speech = subparsers.add_parser("speech")
    speech_subparsers = speech.add_subparsers(dest="speech_command", required=True)
    speech_transcript = speech_subparsers.add_parser("transcript")
    speech_transcript.add_argument("utterance_id")

    subparsers.add_parser("observe")

    return parser


def build_request(
    *,
    args: argparse.Namespace,
    device_id: str,
    priority: Priority,
    timeout: float,
    command_id: str,
    now: datetime,
    source: str,
) -> CommandRequest:
    if args.command == "audio":
        command_type = CommandType(f"audio-{args.audio_command}")
    elif args.command == "camera":
        command_type = CommandType(f"camera-{args.camera_command}")
    elif args.command == "nfc":
        command_type = CommandType(f"nfc-{args.nfc_command}")
    elif args.command == "imu":
        command_type = CommandType(f"imu-{args.imu_command}")
    elif args.command == "events":
        if args.events_command == "tail":
            command_type = CommandType.EVENTS_LIST
        else:
            command_type = CommandType(f"events-{args.events_command}")
    elif args.command == "speech":
        command_type = CommandType(f"speech-{args.speech_command}")
    else:
        command_type = CommandType(args.command)
    meta = CommandMeta(
        device_id=device_id,
        command_id=command_id,
        source=source,
        created_at=utc_timestamp(now),
        priority=priority,
    )

    command_args: dict[str, object]
    if command_type is CommandType.SAY:
        command_args = {"text": " ".join(args.text).strip()}
    elif command_type in {CommandType.FACE, CommandType.MOTION}:
        command_args = {"name": args.name.strip()}
    elif command_type is CommandType.LED:
        command_args = {"pattern": args.pattern.strip()}
    elif command_type is CommandType.AUDIO_PLAY:
        command_args = {"path": args.path.strip()}
    elif command_type is CommandType.AUDIO_CAPTURE:
        command_args = {"seconds": args.seconds, "output": args.output.strip()}
    elif command_type is CommandType.CAMERA_CAPTURE:
        command_args = {"output": args.output.strip(), "quality": args.quality}
    elif command_type is CommandType.NFC_WAIT:
        command_args = {}
    elif command_type is CommandType.IMU_STREAM:
        command_args = {"hz": args.hz}
    elif command_type is CommandType.EVENTS_LIST:
        if args.command == "events" and args.events_command == "tail":
            command_args = {"limit": args.limit, "follow": args.follow}
        else:
            since_event_id = None if args.since_event is None else args.since_event.strip()
            command_args = {"limit": args.limit, "since_event_id": since_event_id or None}
    elif command_type is CommandType.EVENTS_NEXT:
        after_event_id = None if args.after is None else args.after.strip()
        command_args = {
            "limit": 1,
            "after_event_id": after_event_id or None,
            "consumer_id": source,
        }
    elif command_type is CommandType.EVENTS_CLEAR:
        command_args = {"consumer_id": source}
    elif command_type is CommandType.SPEECH_TRANSCRIPT:
        command_args = {"utterance_id": args.utterance_id.strip()}
    else:
        command_args = {}

    return CommandRequest(
        command_type=command_type,
        meta=meta,
        args=command_args,
        wait=args.wait,
        timeout=timeout,
    )


def render(
    result: CommandResult | DeviceStatus | EventListResult | TranscriptResult,
    *,
    json_output: bool,
    stdout: TextIO,
    stderr: TextIO,
) -> None:
    if json_output:
        stream = stderr if _is_failed_result(result) else stdout
        json.dump(result.to_dict(), stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        return

    if isinstance(result, DeviceStatus):
        line = (
            f"{result.device_id} {result.device_state} "
            f"connected={str(result.connected).lower()} face={result.face}"
        )
        if result.last_error is not None:
            line += f" error={result.last_error.code}"
        stdout.write(line + "\n")
        return

    if isinstance(result, EventListResult):
        if not result.ok:
            _render_error_result(result.device_id, result.error, stderr)
            return
        if not result.events:
            stdout.write(f"no events device={result.device_id}\n")
            return
        for event in result.events:
            payload = json.dumps(event.payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            command_id = event.command_id or "-"
            event_id = event.event_id or "-"
            stdout.write(
                f"{event.stamp} {event.event_name} event_id={event_id} device={event.device_id} "
                f"command_id={command_id} payload={payload}\n"
            )
        return

    if isinstance(result, TranscriptResult):
        if not result.ok:
            _render_error_result(result.device_id, result.error, stderr)
            return
        utterance_id = result.utterance_id or "-"
        text = result.transcript or ""
        stdout.write(
            f"transcript device={result.device_id} utterance_id={utterance_id} "
            f"confidence={result.confidence} text={text}\n"
        )
        return

    command = result.command.get("type", "command")
    if result.ok:
        stdout.write(
            f"{result.result_state.value} {command} "
            f"device={result.meta.device_id} command_id={result.meta.command_id}\n"
        )
        return

    error = result.error
    message = "unknown error" if error is None else f"{error.code}: {error.message}"
    stderr.write(
        f"{result.result_state.value} {message} "
        f"device={result.meta.device_id} command_id={result.meta.command_id}\n"
    )


def _is_failed_result(result: CommandResult | DeviceStatus | EventListResult | TranscriptResult) -> bool:
    return isinstance(result, (CommandResult, EventListResult, TranscriptResult)) and not result.ok


def _render_error_result(device_id: str, error, stderr: TextIO) -> None:
    message = "unknown error" if error is None else f"{error.code}: {error.message}"
    stderr.write(f"REJECTED {message} device={device_id}\n")


def _run_follow_loop(
    backend,
    request: CommandRequest,
    *,
    stdout: TextIO,
    stderr: TextIO,
    poll_interval: float,
) -> int:
    if poll_interval <= 0:
        stderr.write("events tail --follow requires a positive poll interval\n")
        return 2
    try:
        while True:
            result = backend.execute(request)
            render(result, json_output=False, stdout=stdout, stderr=stderr)
            if _is_failed_result(result):
                return 1
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        return 0


def _normalize_global_options(argv: list[str]) -> list[str]:
    globals_part: list[str] = []
    command_part: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            command_part.extend(argv[index:])
            break
        if token in VALUE_GLOBALS:
            globals_part.append(token)
            if index + 1 < len(argv):
                globals_part.append(argv[index + 1])
                index += 2
                continue
        elif token in FLAG_GLOBALS:
            globals_part.append(token)
            index += 1
            continue

        command_part.append(token)
        index += 1

    return globals_part + command_part


def finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from exc
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError(f"{value!r} must be finite")
    return parsed


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"{value!r} must be positive")
    return parsed


def events_limit(value: str) -> int:
    parsed = positive_int(value)
    if parsed > 32:
        raise argparse.ArgumentTypeError(f"{value!r} must be 32 or less")
    return parsed
