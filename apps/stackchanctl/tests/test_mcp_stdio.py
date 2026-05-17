from __future__ import annotations

import io
import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stackchanctl.backends.bridge import BridgeBackend, BridgeCommandResponse  # noqa: E402
from stackchanctl.config import RuntimeConfig  # noqa: E402
from stackchanctl.contract import DeviceStatus, ResultState  # noqa: E402
from stackchanctl import mcp_stdio  # noqa: E402


FIXED_NOW = datetime(2026, 5, 16, 0, 0, tzinfo=UTC)


class FakeBridgeClient:
    def get_status(self, meta, timeout: float) -> DeviceStatus:
        return DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
        )

    def set_face(self, meta, name: str, timeout: float) -> BridgeCommandResponse:
        return BridgeCommandResponse(ok=True, result_state=ResultState.ACCEPTED)


class ClosingBridgeClient(FakeBridgeClient):
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class CountingBackend:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    def execute(self, request):
        self.calls += 1
        return DeviceStatus(
            device_id=request.meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
        )

    def close(self) -> None:
        self.closed = True


class BadCloseBackend(CountingBackend):
    def close(self) -> None:
        self.closed = True
        raise RuntimeError("close failed")


class NonFiniteBackend:
    def execute(self, request):
        return DeviceStatus(
            device_id=request.meta.device_id,
            connected=True,
            device_state="idle",
            face=float("nan"),
        )


def encode_message(payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def decode_messages(raw: bytes) -> list[dict]:
    messages: list[dict] = []
    index = 0
    while index < len(raw):
        header_end = raw.index(b"\r\n\r\n", index)
        headers = raw[index:header_end].decode("ascii")
        length = None
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
        if length is None:
            raise AssertionError("missing Content-Length")
        body_start = header_end + 4
        body_end = body_start + length
        messages.append(json.loads(raw[body_start:body_end]))
        index = body_end
    return messages


def run_mcp(messages: list[dict], runtime: RuntimeConfig | None = None):
    stdin = io.BytesIO(b"".join(encode_message(message) for message in messages))
    stdout = io.BytesIO()
    stderr = io.StringIO()
    code = mcp_stdio.run_mcp_stdio(
        runtime or RuntimeConfig(backend="mock", device="default", timeout=5.0, source="mcp_agent"),
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        command_id_factory=lambda: "cmd-test-0001",
        clock=lambda: FIXED_NOW,
    )
    return code, decode_messages(stdout.getvalue()), stderr.getvalue()


def run_mcp_with_backend_factory(messages: list[dict], backend_factory, runtime: RuntimeConfig | None = None):
    stdin = io.BytesIO(b"".join(encode_message(message) for message in messages))
    stdout = io.BytesIO()
    stderr = io.StringIO()
    code = mcp_stdio.run_mcp_stdio(
        runtime or RuntimeConfig(backend="mock", device="default", timeout=5.0, source="mcp_agent"),
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        command_id_factory=lambda: "cmd-test-0001",
        clock=lambda: FIXED_NOW,
        backend_factory=backend_factory,
    )
    return code, decode_messages(stdout.getvalue()), stderr.getvalue()


def run_mcp_wire(raw: bytes):
    stdin = io.BytesIO(raw)
    stdout = io.BytesIO()
    stderr = io.StringIO()
    code = mcp_stdio.run_mcp_stdio(
        RuntimeConfig(backend="mock", device="default", timeout=5.0, source="mcp_agent"),
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        command_id_factory=lambda: "cmd-test-0001",
        clock=lambda: FIXED_NOW,
    )
    return code, decode_messages(stdout.getvalue()), stderr.getvalue()


class McpStdioTests(unittest.TestCase):
    def test_initialize_and_tools_list(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "stackchanctl")
        tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        self.assertEqual(
            tool_names,
            {
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
            },
        )
        for tool in responses[1]["result"]["tools"]:
            self.assertEqual(tool["inputSchema"]["properties"]["priority"]["enum"], ["LOW", "NORMAL", "HIGH"])

    def test_shutdown_exit_stops_server(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}},
                {"jsonrpc": "2.0", "method": "exit", "params": {}},
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual([response["id"] for response in responses], [1, 2])
        self.assertIsNone(responses[1]["result"])

    def test_request_shaped_notifications_do_not_respond(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {"jsonrpc": "2.0", "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "method": "shutdown", "params": {}},
                {"jsonrpc": "2.0", "method": "exit", "params": {}},
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(responses, [])
        self.assertEqual(stderr, "")

    def test_mock_face_tool_returns_cli_result_shape(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {
                        "name": "face",
                        "arguments": {"name": "happy", "device_id": "desk"},
                    },
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        result = responses[0]["result"]
        structured = result["structuredContent"]
        self.assertFalse(result["isError"])
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["result_state"], "ACCEPTED")
        self.assertEqual(structured["device_id"], "desk")
        self.assertEqual(structured["command_id"], "cmd-test-0001")
        self.assertEqual(structured["metadata"]["source"], "mcp_agent")
        self.assertEqual(structured["metadata"]["created_at"], "2026-05-16T00:00:00Z")
        self.assertEqual(structured["metadata"]["priority"], "NORMAL")
        self.assertEqual(structured["command"], {"type": "face", "name": "happy"})
        self.assertEqual(json.loads(result["content"][0]["text"]), structured)

    def test_observe_tool_returns_status_shape(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "observe", "arguments": {}},
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertEqual(structured["device_id"], "default")
        self.assertEqual(structured["device_state"], "idle")

    def test_events_next_tool_returns_event_shape(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "events_next", "arguments": {}},
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["device_id"], "default")
        self.assertEqual(len(structured["events"]), 1)
        self.assertEqual(structured["events"][0]["device_id"], "default")
        self.assertEqual(structured["command_id"], "cmd-test-0001")

    def test_events_next_tool_empty_after_cursor_exhaustion_is_ok(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "first",
                    "method": "tools/call",
                    "params": {"name": "events_next", "arguments": {}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": "second",
                    "method": "tools/call",
                    "params": {"name": "events_next", "arguments": {}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": "third",
                    "method": "tools/call",
                    "params": {"name": "events_next", "arguments": {}},
                },
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[2]["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["events"], [])
        self.assertIsNone(structured["cursor"])

    def test_events_clear_then_list_tool_empty_events_are_ok(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "clear",
                    "method": "tools/call",
                    "params": {"name": "events_clear", "arguments": {}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": "list",
                    "method": "tools/call",
                    "params": {"name": "events_list", "arguments": {}},
                },
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        cleared = responses[0]["result"]["structuredContent"]
        listed = responses[1]["result"]["structuredContent"]
        self.assertTrue(cleared["ok"])
        self.assertEqual(cleared["device_id"], "default")
        self.assertEqual(cleared["events"], [])
        self.assertIsNone(cleared["cursor"])
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["device_id"], "default")
        self.assertEqual(len(listed["events"]), 2)

    def test_speech_get_transcript_tool_returns_transcript_shape(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {
                        "name": "speech_get_transcript",
                        "arguments": {"utterance_id": "mock-utt-001"},
                    },
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["device_id"], "default")
        self.assertEqual(structured["utterance_id"], "mock-utt-001")
        self.assertEqual(structured["transcript"], "mock transcript")
        self.assertEqual(structured["confidence"], 1.0)

    def test_speech_get_transcript_requires_utterance_id(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "speech_get_transcript", "arguments": {}},
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertIn("utterance_id is required", responses[0]["error"]["message"])

    def test_speech_get_transcript_not_found_is_tool_result(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {
                        "name": "speech_get_transcript",
                        "arguments": {"utterance_id": "missing"},
                    },
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["result_state"], "REJECTED")
        self.assertEqual(structured["error"]["code"], "TRANSCRIPT_NOT_FOUND")

    def test_power_status_tool_returns_power_shape(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-power",
                    "method": "tools/call",
                    "params": {"name": "power_status", "arguments": {}},
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["power"]["power_source"], "usb")
        self.assertIsNone(structured["power"]["percentage"])

    def test_safety_priority_is_tool_result_not_protocol_error(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {
                        "name": "led",
                        "arguments": {"pattern": "progress", "priority": "SAFETY"},
                    },
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotIn("error", responses[0])
        structured = responses[0]["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["result_state"], "REJECTED")
        self.assertEqual(structured["error"]["code"], "INVALID_PRIORITY")

    def test_timeout_is_tool_result_not_protocol_error(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {
                        "name": "motion",
                        "arguments": {"name": "nod", "timeout": 0},
                    },
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotIn("error", responses[0])
        structured = responses[0]["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["result_state"], "TIMEOUT")
        self.assertEqual(structured["error"]["code"], "TIMEOUT")

    def test_invalid_argument_type_is_protocol_error(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {
                        "name": "motion",
                        "arguments": {"name": "nod", "wait": "false"},
                    },
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertEqual(responses[0]["error"]["message"], "wait must be a boolean")

    def test_invalid_arguments_container_is_protocol_error(self) -> None:
        for arguments in ([], None):
            with self.subTest(arguments=arguments):
                code, responses, stderr = run_mcp(
                    [
                        {
                            "jsonrpc": "2.0",
                            "id": "call-1",
                            "method": "tools/call",
                            "params": {"name": "observe", "arguments": arguments},
                        }
                    ]
                )

                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")
                self.assertEqual(responses[0]["error"]["code"], -32602)
                self.assertEqual(responses[0]["error"]["message"], "tool arguments must be an object")

    def test_unexpected_argument_is_protocol_error(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "observe", "arguments": {"wait": False}},
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertEqual(responses[0]["error"]["message"], "unexpected argument(s): wait")

    def test_non_finite_json_number_is_parse_error(self) -> None:
        body = (
            b'{"jsonrpc":"2.0","id":"call-1","method":"tools/call",'
            b'"params":{"name":"motion","arguments":{"name":"nod","timeout":NaN}}}'
        )
        raw = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        code, responses, stderr = run_mcp_wire(raw)

        self.assertEqual(code, 0)
        self.assertIn("stackchanctl mcp stdio parse error", stderr)
        self.assertEqual(responses[0]["error"]["code"], -32700)

    def test_oversized_json_number_id_is_parse_error(self) -> None:
        body = b'{"jsonrpc":"2.0","id":1e10000,"method":"tools/list","params":{}}'
        raw = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        code, responses, stderr = run_mcp_wire(raw)

        self.assertEqual(code, 0)
        self.assertIn("stackchanctl mcp stdio parse error", stderr)
        self.assertEqual(responses[0]["error"]["code"], -32700)

    def test_non_finite_default_timeout_is_protocol_error(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "motion", "arguments": {"name": "nod"}},
                }
            ],
            RuntimeConfig(backend="mock", device="default", timeout=float("inf"), source="mcp_agent"),
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertEqual(responses[0]["error"]["message"], "timeout must be finite")

    def test_top_level_non_object_is_invalid_request(self) -> None:
        body = b"[]"
        raw = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        code, responses, stderr = run_mcp_wire(raw)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(responses[0]["error"]["code"], -32600)

    def test_tools_call_notification_is_not_executed(self) -> None:
        backend = CountingBackend()
        code, responses, stderr = run_mcp_with_backend_factory(
            [
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "observe", "arguments": {}},
                }
            ],
            lambda name: backend,
        )

        self.assertEqual(code, 0)
        self.assertEqual(responses, [])
        self.assertEqual(stderr, "")
        self.assertEqual(backend.calls, 0)

    def test_non_finite_backend_result_is_framed_internal_error(self) -> None:
        code, responses, stderr = run_mcp_with_backend_factory(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "observe", "arguments": {}},
                }
            ],
            lambda name: NonFiniteBackend(),
        )

        self.assertEqual(code, 0)
        self.assertIn("stackchanctl mcp stdio error", stderr)
        self.assertEqual(responses[0]["id"], "call-1")
        self.assertEqual(responses[0]["error"]["code"], -32603)

    def test_malformed_frame_keeps_stdout_protocol_framed_and_diagnostics_on_stderr(self) -> None:
        code, responses, stderr = run_mcp_wire(b"X-Debug: bad\r\n\r\n")

        self.assertEqual(code, 0)
        self.assertIn("stackchanctl mcp stdio parse error", stderr)
        self.assertEqual(responses[0]["jsonrpc"], "2.0")
        self.assertIsNone(responses[0]["id"])
        self.assertEqual(responses[0]["error"]["code"], -32700)

    def test_bridge_backend_fake_client_keeps_result_shape(self) -> None:
        code, responses, stderr = run_mcp_with_backend_factory(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "face", "arguments": {"name": "happy"}},
                }
            ],
            lambda name: BridgeBackend(FakeBridgeClient()),
            RuntimeConfig(backend="bridge", device="default", timeout=5.0, source="mcp_agent"),
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["result_state"], "ACCEPTED")
        self.assertEqual(structured["metadata"]["source"], "mcp_agent")
        self.assertEqual(structured["command"], {"type": "face", "name": "happy"})

    def test_backend_is_reused_and_closed(self) -> None:
        backend = CountingBackend()
        code, responses, stderr = run_mcp_with_backend_factory(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "observe", "arguments": {}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": "call-2",
                    "method": "tools/call",
                    "params": {"name": "observe", "arguments": {}},
                },
            ],
            lambda name: backend,
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(len(responses), 2)
        self.assertEqual(backend.calls, 2)
        self.assertTrue(backend.closed)

    def test_backend_close_failure_is_reported_without_crashing(self) -> None:
        backend = BadCloseBackend()
        code, responses, stderr = run_mcp_with_backend_factory(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "observe", "arguments": {}},
                },
            ],
            lambda name: backend,
        )

        self.assertEqual(code, 0)
        self.assertEqual(len(responses), 1)
        self.assertIn("stackchanctl mcp stdio close error", stderr)
        self.assertTrue(backend.closed)

    def test_bridge_backend_close_reaches_wrapped_client(self) -> None:
        client = ClosingBridgeClient()
        code, responses, stderr = run_mcp_with_backend_factory(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "face", "arguments": {"name": "happy"}},
                },
                {"jsonrpc": "2.0", "method": "exit", "params": {}},
            ],
            lambda name: BridgeBackend(client),
            RuntimeConfig(backend="bridge", device="default", timeout=5.0, source="mcp_agent"),
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(len(responses), 1)
        self.assertTrue(client.closed)


if __name__ == "__main__":
    unittest.main()
