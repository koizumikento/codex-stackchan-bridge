from __future__ import annotations

import io
import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stackchanctl.backends.bridge import (  # noqa: E402
    BridgeBackend,
    BridgeBackendTimeout,
    BridgeCommandResponse,
    RclpyBridgeClient,
    _copy_created_at,
    _normalize_action_response,
)
from stackchanctl.backends import bridge as bridge_module  # noqa: E402
from stackchanctl.cli import run_cli  # noqa: E402
from stackchanctl.contract import (  # noqa: E402
    DeviceStatus,
    ErrorDetail,
    EventListResult,
    PowerStatusResult,
    ResultState,
    TranscriptResult,
)


FIXED_NOW = datetime(2026, 5, 16, 0, 0, tzinfo=UTC)


class FakeBridgeClient:
    def __init__(self, *, timeout: bool = False) -> None:
        self.timeout = timeout
        self.get_status_args = None
        self.list_events_args = None
        self.next_event_args = None
        self.clear_events_args = None
        self.power_status_args = None

    def get_status(self, meta, timeout: float) -> DeviceStatus:
        if self.timeout:
            raise BridgeBackendTimeout()
        self.get_status_args = (meta.device_id, meta.command_id, meta.source, timeout)
        return DeviceStatus(
            device_id=meta.device_id,
            connected=True,
            device_state="idle",
            face="neutral",
        )

    def set_face(self, meta, name: str, timeout: float) -> BridgeCommandResponse:
        return self._accepted()

    def set_led(self, meta, pattern: str, timeout: float) -> BridgeCommandResponse:
        return self._accepted()

    def run_motion(
        self, meta, name: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        if self.timeout:
            raise BridgeBackendTimeout()
        return BridgeCommandResponse(
            ok=True,
            result_state=ResultState.COMPLETED if wait else ResultState.ACCEPTED,
        )

    def say(
        self, meta, text: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        return BridgeCommandResponse(
            ok=True,
            result_state=ResultState.COMPLETED if wait else ResultState.ACCEPTED,
        )

    def play_audio(
        self, meta, path: str, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        return self._unsupported_media()

    def capture_audio(
        self,
        meta,
        seconds: float,
        output: str,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        return self._unsupported_media()

    def capture_camera(
        self, meta, output: str, quality: int, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        return self._unsupported_media()

    def list_events(
        self, meta, limit: int, since_event_id: str | None, timeout: float
    ) -> EventListResult:
        self.list_events_args = (meta.device_id, limit, since_event_id, timeout)
        return self._unsupported_events(meta.device_id)

    def next_event(
        self,
        meta,
        consumer_id: str,
        after_event_id: str | None,
        timeout: float,
    ) -> EventListResult:
        self.next_event_args = (meta.device_id, consumer_id, after_event_id, timeout)
        return self._unsupported_events(meta.device_id)

    def clear_events(self, meta, consumer_id: str, timeout: float) -> EventListResult:
        self.clear_events_args = (meta.device_id, consumer_id, timeout)
        return self._unsupported_events(meta.device_id)

    def get_transcript(
        self, meta, utterance_id: str | None, timeout: float
    ) -> TranscriptResult:
        return TranscriptResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=meta.device_id,
            utterance_id=utterance_id,
            transcript=None,
            confidence=None,
            expires_at=None,
            error=ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="bridge facade does not implement transcripts yet",
                recoverable=False,
            ),
        )

    def get_power_status(self, meta, timeout: float) -> PowerStatusResult:
        self.power_status_args = (meta.device_id, meta.command_id, timeout)
        return PowerStatusResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=meta.device_id,
            voltage_v=4.9,
            current_ma=180.0,
            power_mw=882.0,
            percentage=None,
            power_source="usb",
            charging=True,
            powered=True,
            low_battery=False,
            brownout_risk=False,
            stale=False,
            stamp="2026-05-16T00:00:00Z",
            meta=meta,
        )

    @staticmethod
    def _accepted() -> BridgeCommandResponse:
        return BridgeCommandResponse(ok=True, result_state=ResultState.ACCEPTED)

    @staticmethod
    def _unsupported_media() -> BridgeCommandResponse:
        return BridgeCommandResponse(
            ok=False,
            result_state=ResultState.REJECTED,
            error=ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="bridge facade does not implement media transport yet",
                recoverable=False,
            ),
        )

    @staticmethod
    def _unsupported_events(device_id: str) -> EventListResult:
        return EventListResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=device_id,
            events=[],
            meta=None,
            error=ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="bridge facade does not implement event buffer yet",
                recoverable=False,
            ),
        )


def run_stackchanctl(argv: list[str], client: FakeBridgeClient):
    stdout = io.StringIO()
    stderr = io.StringIO()
    original = bridge_module.RclpyBridgeClient
    bridge_module.RclpyBridgeClient = lambda: client
    try:
        code = run_cli(
            argv,
            stdout=stdout,
            stderr=stderr,
            env={"XDG_CONFIG_HOME": str(ROOT / ".test-config")},
            command_id_factory=lambda: "cmd-test-0001",
            clock=lambda: FIXED_NOW,
        )
    finally:
        bridge_module.RclpyBridgeClient = original
    return code, stdout.getvalue(), stderr.getvalue()


class BridgeBackendTests(unittest.TestCase):
    def test_bridge_observe_json_uses_client_status(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "observe", "--json"],
            client,
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["device_id"], "default")
        self.assertEqual(payload["device_state"], "idle")
        self.assertEqual(payload["command_id"], "cmd-test-0001")
        self.assertEqual(payload["metadata"]["source"], "human_cli")
        self.assertEqual(
            client.get_status_args,
            ("default", "cmd-test-0001", "human_cli", 5.0),
        )

    def test_bridge_face_json_matches_mock_shape(self) -> None:
        bridge_backend = BridgeBackend(FakeBridgeClient())
        self.assertIsNotNone(bridge_backend)

        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "face", "happy", "--json"],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["result_state"], "ACCEPTED")
        self.assertEqual(payload["command"], {"type": "face", "name": "happy"})
        self.assertEqual(payload["metadata"]["device_id"], "default")

    def test_bridge_motion_wait_can_complete(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "motion", "nod", "--wait", "--json"],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["result_state"], "COMPLETED")

    def test_bridge_say_wait_can_complete(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "say", "hello", "--wait", "--json"],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["result_state"], "COMPLETED")
        self.assertEqual(payload["command"], {"type": "say", "text_length": 5})

    def test_created_at_is_copied_to_ros_time(self) -> None:
        class Stamp:
            sec = 0
            nanosec = 0

        stamp = Stamp()
        _copy_created_at(stamp, "2026-05-16T00:00:01Z")

        self.assertEqual(stamp.sec, 1778889601)
        self.assertEqual(stamp.nanosec, 0)

    def test_bridge_timeout_maps_to_recoverable_structured_error(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "motion", "nod", "--json"],
            FakeBridgeClient(timeout=True),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["result_state"], "TIMEOUT")
        self.assertEqual(payload["error"]["code"], "TIMEOUT")
        self.assertTrue(payload["error"]["recoverable"])

    def test_bridge_audio_play_is_unsupported_until_transport_exists(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "audio", "play", "prompt.wav", "--json"],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["result_state"], "REJECTED")
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(payload["command"], {"type": "audio.play", "path": "prompt.wav"})

    def test_bridge_audio_capture_is_unsupported_until_transport_exists(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "audio",
                "capture",
                "--seconds",
                "1.5",
                "--output",
                "mic.wav",
                "--wait",
                "--json",
            ],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["result_state"], "REJECTED")
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(payload["command"]["type"], "audio.capture")
        self.assertEqual(payload["command"]["output"], "mic.wav")

    def test_bridge_camera_capture_is_unsupported_until_transport_exists(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "camera",
                "capture",
                "--output",
                "frame.jpg",
                "--quality",
                "80",
                "--wait",
                "--json",
            ],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["result_state"], "REJECTED")
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(payload["command"]["type"], "camera.capture")
        self.assertEqual(payload["command"]["quality"], 80)

    def test_bridge_events_list_passes_since_event_to_client(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "events",
                "list",
                "--since-event",
                "evt-1",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["device_id"], "default")
        self.assertEqual(payload["events"], [])
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(client.list_events_args, ("default", 32, "evt-1", 5.0))

    def test_bridge_events_next_and_clear_pass_consumer_cursor_args(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "--source",
                "codex_skill",
                "events",
                "next",
                "--after",
                "evt-1",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(client.next_event_args, ("default", "codex_skill", "evt-1", 5.0))

        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "--source",
                "codex_skill",
                "events",
                "clear",
                "--json",
            ],
            client,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "UNSUPPORTED_FEATURE")
        self.assertEqual(client.clear_events_args, ("default", "codex_skill", 5.0))

    def test_bridge_speech_transcript_is_unsupported_until_service_exists(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            [
                "--backend",
                "bridge",
                "speech",
                "transcript",
                "u-1",
                "--json",
            ],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["device_id"], "default")
        self.assertEqual(payload["utterance_id"], "u-1")
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_FEATURE")

    def test_bridge_power_status_uses_client_shape(self) -> None:
        client = FakeBridgeClient()
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "power", "status", "--json"],
            client,
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["power"]["power_source"], "usb")
        self.assertEqual(payload["power"]["voltage_v"], 4.9)
        self.assertEqual(client.power_status_args, ("default", "cmd-test-0001", 5.0))

    def test_non_wait_action_normalizes_success_after_facade_validation(self) -> None:
        response = _normalize_action_response(
            BridgeCommandResponse(ok=True, result_state=ResultState.COMPLETED),
            wait=False,
        )

        self.assertEqual(response.result_state, ResultState.ACCEPTED)

    def test_rclpy_action_waits_for_facade_result_when_not_waiting(self) -> None:
        action = FakeActionClient()
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy()
        client._node = object()
        client._action_client_type = lambda node, action_type, action_name: action

        response = client._send_action_goal(
            object,
            "/stackchan/default/cmd/say",
            object(),
            wait=False,
            timeout=1.0,
        )

        self.assertTrue(response.ok)
        self.assertEqual(response.result_state, ResultState.ACCEPTED)
        self.assertTrue(action.goal_handle.result_requested)

    def test_run_motion_waits_for_facade_result_when_not_waiting(self) -> None:
        action = FakeActionClient()
        client = RclpyBridgeClient.__new__(RclpyBridgeClient)
        client._rclpy = FakeRclpy()
        client._node = object()
        client._action_client_type = lambda node, action_type, action_name: action
        client._run_motion_type = FakeRunMotion

        response = client.run_motion(
            SimpleNamespace(
                device_id="default",
                command_id="cmd-test-0001",
                source="test",
                created_at="2026-05-16T00:00:00Z",
                priority=SimpleNamespace(value="NORMAL"),
            ),
            "nod",
            wait=False,
            timeout=1.0,
        )

        self.assertTrue(response.ok)
        self.assertEqual(response.result_state, ResultState.ACCEPTED)
        self.assertTrue(action.goal_handle.result_requested)

    def test_non_wait_action_preserves_facade_rejection(self) -> None:
        response = _normalize_action_response(
            BridgeCommandResponse(
                ok=False,
                result_state=ResultState.REJECTED,
                error=ErrorDetail(
                    code="INVALID_PRIORITY",
                    message="rejected",
                    recoverable=False,
                ),
            ),
            wait=False,
        )

        self.assertFalse(response.ok)
        self.assertEqual(response.error.code, "INVALID_PRIORITY")

    def test_bridge_rejection_keeps_cli_error_shape(self) -> None:
        class RejectingClient(FakeBridgeClient):
            def set_face(self, meta, name: str, timeout: float) -> BridgeCommandResponse:
                return BridgeCommandResponse(
                    ok=False,
                    result_state=ResultState.REJECTED,
                    error=ErrorDetail(
                        code="TRANSPORT_DISCONNECTED",
                        message="device is disconnected",
                        recoverable=True,
                    ),
                )

        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "face", "happy", "--json"],
            RejectingClient(),
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "TRANSPORT_DISCONNECTED")
        self.assertTrue(payload["error"]["recoverable"])


class FakeRclpy:
    def spin_until_future_complete(self, node, future, timeout_sec: float) -> None:
        del node, timeout_sec
        future.completed = True


class FakeFuture:
    def __init__(self, result) -> None:
        self._result = result
        self.completed = False

    def done(self) -> bool:
        return self.completed

    def result(self):
        return self._result


class FakeGoalHandle:
    accepted = True

    def __init__(self) -> None:
        self.result_requested = False

    def get_result_async(self):
        self.result_requested = True
        return FakeFuture(
            SimpleNamespace(
                result=SimpleNamespace(
                    result=SimpleNamespace(
                        ok=True,
                        state=2,
                        error_code="",
                        message="",
                        recoverable=False,
                    )
                )
            )
        )


class FakeActionClient:
    def __init__(self) -> None:
        self.goal_handle = FakeGoalHandle()

    def wait_for_server(self, timeout_sec: float) -> bool:
        del timeout_sec
        return True

    def send_goal_async(self, goal):
        del goal
        return FakeFuture(self.goal_handle)


class FakeRunMotion:
    class Goal:
        def __init__(self) -> None:
            self.meta = SimpleNamespace(created_at=SimpleNamespace())
            self.name = ""
            self.intensity = 0.0
            self.duration_ms = 0


if __name__ == "__main__":
    unittest.main()
