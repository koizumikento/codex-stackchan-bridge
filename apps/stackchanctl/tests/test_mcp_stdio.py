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
from stackchanctl.contract import CommandResult, DeviceStatus, ErrorDetail, Event, EventListResult, ResultState  # noqa: E402
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

    def play_audio(self, meta, path: str, *, wait: bool, timeout: float) -> BridgeCommandResponse:
        return BridgeCommandResponse(
            ok=False,
            result_state=ResultState.REJECTED,
            error=ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="bridge facade does not implement media transport yet",
                recoverable=False,
            ),
        )

    def capture_audio(self, meta, seconds: float, output: str, *, wait: bool, timeout: float) -> BridgeCommandResponse:
        return self.play_audio(meta, output, wait=wait, timeout=timeout)

    def capture_camera(self, meta, output: str, quality: int, *, wait: bool, timeout: float) -> BridgeCommandResponse:
        return self.play_audio(meta, output, wait=wait, timeout=timeout)


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


class SensitiveEventBackend:
    def execute(self, request):
        return EventListResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=request.meta.device_id,
            events=[
                Event(
                    event_id="evt-sensitive",
                    device_id=request.meta.device_id,
                    event_name="nfc_detected",
                    source="firmware",
                    stamp="2026-05-16T00:00:00Z",
                    command_id=request.meta.command_id,
                    payload={
                        "tag_id": "04AABB",
                        "nested": {"raw_ir_code": "0xDEADBEEF"},
                        "transcript": "turn the light on",
                        "full_transcript": "turn the lamp blue",
                        "asr_transcript": "open the window",
                        "utterance": "hello stackchan",
                        "utterance_text": "hello again",
                        "utterance_id": "mock-utt-001",
                        "level": 3,
                    },
                )
            ],
            cursor="evt-sensitive",
            meta=request.meta,
        )


class SensitiveCommandBackend:
    def execute(self, request):
        return CommandResult(
            ok=True,
            result_state=ResultState.ACCEPTED,
            meta=request.meta,
            command={
                "type": "audio.play",
                "pcm_data": "raw-pcm",
                "image_payload": "raw-image",
                "nested": {"raw_ir_code": "0xDEADBEEF"},
            },
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
                "motion_pose",
                "motion_home",
                "motion_status",
                "led",
                "observe",
                "events_list",
                "events_next",
                "events_clear",
                "speech_get_transcript",
                "power_status",
                "audio_play",
                "audio_capture",
                "camera_capture",
            },
        )
        for tool in responses[1]["result"]["tools"]:
            self.assertEqual(tool["inputSchema"]["properties"]["priority"]["enum"], ["LOW", "NORMAL", "HIGH"])
            self.assertNotIn("maintenance", tool["name"])
            self.assertNotIn("calibration", tool["name"])
        schemas = {tool["name"]: tool["inputSchema"] for tool in responses[1]["result"]["tools"]}
        self.assertIn("voice", schemas["say"]["properties"])
        self.assertEqual(
            schemas["motion_pose"]["properties"]["duration_ms"]["anyOf"],
            [
                {"type": "integer", "const": 0},
                {"type": "integer", "minimum": 100, "maximum": 2000},
            ],
        )
        self.assertEqual(
            schemas["motion_home"]["properties"]["duration_ms"]["anyOf"],
            [
                {"type": "integer", "const": 0},
                {"type": "integer", "minimum": 100, "maximum": 2000},
            ],
        )

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

    def test_mock_say_tool_accepts_voice_profile_without_returning_text(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-say",
                    "method": "tools/call",
                    "params": {
                        "name": "say",
                        "arguments": {"text": "hello", "voice": "default"},
                    },
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(
            structured["command"],
            {"type": "say", "text_length": 5, "voice_profile": "default"},
        )
        self.assertNotIn("hello", responses[0]["result"]["content"][0]["text"])

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
        self.assertEqual(structured["firmware_version"], "mock-firmware-0.1")
        capabilities = {item["name"]: item for item in structured["capabilities"]}
        self.assertEqual(capabilities["audio_playback"]["state"], "available")

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

    def test_events_tool_redacts_sensitive_payloads_in_structured_and_text_content(self) -> None:
        code, responses, stderr = run_mcp_with_backend_factory(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "events_list", "arguments": {}},
                }
            ],
            lambda name: SensitiveEventBackend(),
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        result = responses[0]["result"]
        structured = result["structuredContent"]
        payload = structured["events"][0]["payload"]
        self.assertEqual(payload["tag_id"], "<redacted>")
        self.assertEqual(payload["nested"]["raw_ir_code"], "<redacted>")
        self.assertEqual(payload["transcript"], "<redacted>")
        self.assertEqual(payload["full_transcript"], "<redacted>")
        self.assertEqual(payload["asr_transcript"], "<redacted>")
        self.assertEqual(payload["utterance"], "<redacted>")
        self.assertEqual(payload["utterance_text"], "<redacted>")
        self.assertEqual(payload["utterance_id"], "mock-utt-001")
        self.assertEqual(payload["level"], 3)
        self.assertEqual(json.loads(result["content"][0]["text"]), structured)
        self.assertNotIn("04AABB", result["content"][0]["text"])
        self.assertNotIn("0xDEADBEEF", result["content"][0]["text"])
        self.assertNotIn("turn the light on", result["content"][0]["text"])
        self.assertNotIn("turn the lamp blue", result["content"][0]["text"])
        self.assertNotIn("open the window", result["content"][0]["text"])
        self.assertNotIn("hello stackchan", result["content"][0]["text"])
        self.assertNotIn("hello again", result["content"][0]["text"])

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

    def test_media_and_sensor_tools_return_cli_result_shapes_without_payloads(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "audio-play",
                    "method": "tools/call",
                    "params": {"name": "audio_play", "arguments": {"path": "prompt.wav"}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": "audio-capture",
                    "method": "tools/call",
                    "params": {
                        "name": "audio_capture",
                        "arguments": {"seconds": 1.5, "output": "mic.wav"},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": "camera",
                    "method": "tools/call",
                    "params": {
                        "name": "camera_capture",
                        "arguments": {"output": "frame.jpg", "quality": 80},
                    },
                },
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = [response["result"]["structuredContent"] for response in responses]
        self.assertEqual(
            [payload["command"]["type"] for payload in structured],
            ["audio.play", "audio.capture", "camera.capture"],
        )
        content = "\n".join(response["result"]["content"][0]["text"] for response in responses)
        self.assertNotIn("pcm_data", content.lower())
        self.assertNotIn("audio_payload", content.lower())
        self.assertNotIn("base64", content.lower())
        self.assertNotIn("jpeg_bytes", content.lower())
        self.assertNotIn("image_payload", content.lower())
        self.assertNotIn("nfc_tag_id", content.lower())
        self.assertNotIn("raw_ir_code", content.lower())

    def test_media_tool_redacts_sensitive_backend_command_fields(self) -> None:
        code, responses, stderr = run_mcp_with_backend_factory(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-audio",
                    "method": "tools/call",
                    "params": {"name": "audio_play", "arguments": {"path": "prompt.wav"}},
                }
            ],
            lambda name: SensitiveCommandBackend(),
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertEqual(structured["command"]["pcm_data"], "<redacted>")
        self.assertEqual(structured["command"]["image_payload"], "<redacted>")
        self.assertEqual(structured["command"]["nested"]["raw_ir_code"], "<redacted>")
        self.assertEqual(json.loads(responses[0]["result"]["content"][0]["text"]), structured)
        self.assertNotIn("raw-pcm", responses[0]["result"]["content"][0]["text"])
        self.assertNotIn("raw-image", responses[0]["result"]["content"][0]["text"])
        self.assertNotIn("0xDEADBEEF", responses[0]["result"]["content"][0]["text"])

    def test_bridge_media_tool_rejection_is_tool_result_not_protocol_error(self) -> None:
        code, responses, stderr = run_mcp_with_backend_factory(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-audio",
                    "method": "tools/call",
                    "params": {"name": "audio_play", "arguments": {"path": "prompt.wav"}},
                }
            ],
            lambda name: BridgeBackend(FakeBridgeClient()),
            RuntimeConfig(backend="bridge", device="default", timeout=5.0, source="mcp_agent"),
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotIn("error", responses[0])
        structured = responses[0]["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["error"]["code"], "UNSUPPORTED_FEATURE")

    def test_media_tool_invalid_argument_type_is_protocol_error(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-camera",
                    "method": "tools/call",
                    "params": {"name": "camera_capture", "arguments": {"output": "frame.jpg", "quality": 80.5}},
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertIn("quality must be an integer", responses[0]["error"]["message"])

    def test_motion_pose_tool_returns_command_shape(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-pose",
                    "method": "tools/call",
                    "params": {
                        "name": "motion_pose",
                        "arguments": {"pan_deg": 30.0, "tilt_deg": 20.0, "speed": 500},
                    },
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["command"]["type"], "motion.pose")
        self.assertEqual(structured["command"]["frame"], "home")
        self.assertEqual(structured["command"]["pan_deg"], 30.0)

    def test_motion_home_tool_returns_dedicated_command_shape(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-home",
                    "method": "tools/call",
                    "params": {"name": "motion_home", "arguments": {"speed": 500}},
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["command"]["type"], "motion.home")

    def test_motion_status_tool_returns_pose_shape(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-status",
                    "method": "tools/call",
                    "params": {"name": "motion_status", "arguments": {}},
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        structured = responses[0]["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["pose"]["frame"], "home")

    def test_motion_pose_rejection_is_tool_result_not_protocol_error(self) -> None:
        code, responses, stderr = run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-pose",
                    "method": "tools/call",
                    "params": {
                        "name": "motion_pose",
                        "arguments": {"pan_deg": 129.0, "tilt_deg": 20.0},
                    },
                }
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotIn("error", responses[0])
        structured = responses[0]["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["error"]["code"], "SERVO_LIMIT_EXCEEDED")

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
