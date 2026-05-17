from __future__ import annotations

import json
import math
import sys
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, BinaryIO, Protocol, TextIO

from stackchanctl.backends import create_backend
from stackchanctl.config import RuntimeConfig
from stackchanctl.contract import (
    CommandMeta,
    CommandRequest,
    CommandType,
    Priority,
    utc_timestamp,
)

CommandIdFactory = Callable[[], str]
Clock = Callable[[], datetime]
BackendFactory = Callable[[], "Backend"]


class Backend(Protocol):
    def execute(self, request: CommandRequest) -> Any: ...

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "stackchanctl", "version": "0.1.0"}
SUPPORTED_TOOLS = (
    "say",
    "face",
    "motion",
    "led",
    "observe",
    "events_list",
    "events_next",
    "events_clear",
    "speech_get_transcript",
    "power_status",
)
_EXIT = object()


def run_mcp_stdio(
    runtime: RuntimeConfig,
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
    command_id_factory: CommandIdFactory | None = None,
    clock: Clock | None = None,
    backend_factory: Callable[[str], Backend] | None = None,
) -> int:
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    stderr = stderr or sys.stderr
    command_id_factory = command_id_factory or (lambda: str(uuid.uuid4()))
    clock = clock or (lambda: datetime.now(UTC))
    backend_factory = backend_factory or create_backend
    backend: Backend | None = None

    def get_backend() -> Backend:
        nonlocal backend
        if backend is None:
            backend = backend_factory(runtime.backend)
        return backend

    try:
        while True:
            try:
                raw = _read_message(stdin)
                if raw is None:
                    return 0
                request = json.loads(
                    raw.decode("utf-8"),
                    parse_constant=_reject_json_constant,
                    parse_float=_parse_json_float,
                )
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
                stderr.write(f"stackchanctl mcp stdio parse error: {exc}\n")
                response = _error_response(None, -32700, "parse error")
            else:
                if not isinstance(request, Mapping):
                    response = _error_response(None, -32600, "invalid request")
                else:
                    try:
                        response = _handle_request(
                            request,
                            runtime,
                            command_id_factory=command_id_factory,
                            clock=clock,
                            backend_factory=get_backend,
                        )
                    except Exception as exc:  # pragma: no cover - defensive protocol guard
                        stderr.write(f"stackchanctl mcp stdio error: {exc}\n")
                        response = _error_response(request.get("id"), -32603, "internal error")

            if response is _EXIT:
                return 0
            if response is not None:
                _write_message(stdout, response)
    finally:
        if backend is not None:
            close = getattr(backend, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:  # pragma: no cover - defensive cleanup guard
                    stderr.write(f"stackchanctl mcp stdio close error: {exc}\n")


def _handle_request(
    request: Mapping[str, Any],
    runtime: RuntimeConfig,
    *,
    command_id_factory: CommandIdFactory,
    clock: Clock,
    backend_factory: BackendFactory,
) -> dict[str, Any] | object | None:
    request_id = request.get("id")
    method = request.get("method")

    if "id" not in request and method != "exit":
        return None

    if method == "initialize":
        return _success_response(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _success_response(request_id, {"tools": [_tool_schema(name) for name in SUPPORTED_TOOLS]})
    if method == "tools/call":
        if request_id is None:
            return None
        return _handle_tool_call(
            request_id,
            request.get("params", {}),
            runtime,
            command_id_factory,
            clock,
            backend_factory,
        )
    if method == "shutdown":
        return _success_response(request_id, None)
    if method == "exit":
        return _EXIT

    if request_id is None:
        return None
    return _error_response(request_id, -32601, f"method not found: {method}")


def _handle_tool_call(
    request_id: Any,
    params: Any,
    runtime: RuntimeConfig,
    command_id_factory: CommandIdFactory,
    clock: Clock,
    backend_factory: BackendFactory,
) -> dict[str, Any]:
    if not isinstance(params, Mapping):
        return _error_response(request_id, -32602, "tools/call params must be an object")

    name = params.get("name")
    arguments = params["arguments"] if "arguments" in params else {}
    if not isinstance(name, str) or name not in SUPPORTED_TOOLS:
        return _error_response(request_id, -32602, f"unknown tool: {name}")
    if arguments is None or not isinstance(arguments, Mapping):
        return _error_response(request_id, -32602, "tool arguments must be an object")
    extra_keys = set(arguments) - _allowed_argument_keys(name)
    if extra_keys:
        keys = ", ".join(sorted(str(key) for key in extra_keys))
        return _error_response(request_id, -32602, f"unexpected argument(s): {keys}")

    try:
        request = _build_tool_request(
            name=name,
            arguments=arguments,
            runtime=runtime,
            command_id=command_id_factory(),
            now=clock(),
        )
    except ValueError as exc:
        return _error_response(request_id, -32602, str(exc))

    result = backend_factory().execute(request)
    structured = result.to_dict()
    content_text = json.dumps(structured, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return _success_response(
        request_id,
        {
            "content": [{"type": "text", "text": content_text}],
            "structuredContent": structured,
            "isError": False,
        },
    )


def _build_tool_request(
    *,
    name: str,
    arguments: Mapping[str, Any],
    runtime: RuntimeConfig,
    command_id: str,
    now: datetime,
) -> CommandRequest:
    priority = _optional_priority(arguments, "priority", Priority.NORMAL)
    device_id = _optional_string(arguments, "device_id", runtime.device)
    meta = CommandMeta(
        device_id=device_id,
        command_id=command_id,
        source=runtime.source,
        created_at=utc_timestamp(now),
        priority=priority,
    )
    timeout = _optional_number(arguments, "timeout", runtime.timeout)
    wait = _optional_bool(arguments, "wait", False)

    if name == "say":
        text = _required_string(arguments, "text").strip()
        command_type = CommandType.SAY
        command_args: dict[str, Any] = {"text": text}
    elif name == "face":
        command_type = CommandType.FACE
        command_args = {"name": _required_string(arguments, "name").strip()}
    elif name == "motion":
        command_type = CommandType.MOTION
        command_args = {"name": _required_string(arguments, "name").strip()}
    elif name == "led":
        command_type = CommandType.LED
        command_args = {"pattern": _required_string(arguments, "pattern").strip()}
    elif name == "observe":
        command_type = CommandType.OBSERVE
        command_args = {}
    elif name == "events_list":
        command_type = CommandType.EVENTS_LIST
        command_args = {
            "limit": _optional_int(arguments, "limit", 32),
            "since_event_id": _optional_string(arguments, "since_event_id", "").strip() or None,
        }
    elif name == "events_next":
        command_type = CommandType.EVENTS_NEXT
        command_args = {
            "limit": 1,
            "after_event_id": _optional_string(arguments, "after_event_id", "").strip() or None,
        }
    elif name == "events_clear":
        command_type = CommandType.EVENTS_CLEAR
        command_args = {}
    elif name == "speech_get_transcript":
        command_type = CommandType.SPEECH_TRANSCRIPT
        utterance_id = _required_string(arguments, "utterance_id").strip()
        if not utterance_id:
            raise ValueError("utterance_id is required")
        command_args = {"utterance_id": utterance_id}
    elif name == "power_status":
        command_type = CommandType.POWER_STATUS
        command_args = {}
    else:  # pragma: no cover - guarded by caller
        raise ValueError(f"unknown tool: {name}")

    return CommandRequest(
        command_type=command_type,
        meta=meta,
        args=command_args,
        wait=wait,
        timeout=timeout,
    )


def _required_string(arguments: Mapping[str, Any], key: str) -> str:
    if key not in arguments:
        raise ValueError(f"{key} is required")
    value = arguments[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_string(arguments: Mapping[str, Any], key: str, default: str) -> str:
    if key not in arguments:
        return default
    value = arguments[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_bool(arguments: Mapping[str, Any], key: str, default: bool) -> bool:
    if key not in arguments:
        return default
    value = arguments[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _optional_number(arguments: Mapping[str, Any], key: str, default: float) -> float:
    if key not in arguments:
        return _finite_number(default, key)
    value = arguments[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be a number")
    return _finite_number(value, key)


def _optional_int(arguments: Mapping[str, Any], key: str, default: int) -> int:
    if key not in arguments:
        value = default
    else:
        raw = arguments[key]
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError(f"{key} must be an integer")
        value = raw
    if value < 1:
        raise ValueError(f"{key} must be positive")
    if key == "limit" and value > 32:
        raise ValueError("limit must be 32 or less")
    return value


def _finite_number(value: int | float, key: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{key} must be finite")
    return value


def _optional_priority(arguments: Mapping[str, Any], key: str, default: Priority) -> Priority:
    if key not in arguments:
        return default
    value = arguments[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return Priority(value)


def _allowed_argument_keys(name: str) -> set[str]:
    keys = {"device_id", "priority", "timeout"}
    if name == "say":
        keys.update({"text", "wait"})
    elif name in {"face", "motion"}:
        keys.add("name")
        if name == "motion":
            keys.add("wait")
    elif name == "led":
        keys.add("pattern")
    elif name == "events_list":
        keys.update({"limit", "since_event_id"})
    elif name == "events_next":
        keys.add("after_event_id")
    elif name == "speech_get_transcript":
        keys.add("utterance_id")
    return keys


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _parse_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"invalid JSON number: {value}")
    return parsed


def _tool_schema(name: str) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "device_id": {"type": "string"},
        "priority": {"type": "string", "enum": ["LOW", "NORMAL", "HIGH"]},
        "timeout": {"type": "number"},
    }
    required: list[str] = []

    if name == "say":
        properties["text"] = {"type": "string"}
        required.append("text")
    elif name in {"face", "motion"}:
        properties["name"] = {"type": "string"}
        required.append("name")
    elif name == "led":
        properties["pattern"] = {"type": "string"}
        required.append("pattern")
    elif name == "events_list":
        properties["limit"] = {"type": "integer", "minimum": 1}
        properties["since_event_id"] = {"type": "string"}
    elif name == "events_next":
        properties["after_event_id"] = {"type": "string"}
    elif name == "speech_get_transcript":
        properties["utterance_id"] = {"type": "string"}
        required.append("utterance_id")

    if name in {"say", "motion"}:
        properties["wait"] = {"type": "boolean"}

    return {
        "name": name,
        "description": _tool_description(name),
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def _tool_description(name: str) -> str:
    if name.startswith("events_"):
        return f"Read stackchanctl {name.replace('_', ' ')} through the configured backend."
    if name == "speech_get_transcript":
        return "Read a speech transcript through the configured backend."
    if name == "power_status":
        return "Read StackChan power telemetry through the configured backend."
    return f"Send stackchanctl {name} through the configured backend."


def _success_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _read_message(stream: BinaryIO) -> bytes | None:
    headers = bytearray()
    while b"\r\n\r\n" not in headers and b"\n\n" not in headers:
        char = stream.read(1)
        if char == b"":
            return None
        headers.extend(char)

    header_text = bytes(headers).decode("ascii", errors="replace")
    content_length = None
    for line in header_text.replace("\r\n", "\n").split("\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
            break
    if content_length is None:
        raise ValueError("missing Content-Length header")

    return stream.read(content_length)


def _write_message(stream: BinaryIO, payload: Mapping[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()
