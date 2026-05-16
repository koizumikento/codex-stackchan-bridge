from __future__ import annotations

import io
import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stackchanctl.backends.bridge import (  # noqa: E402
    BridgeBackend,
    BridgeBackendTimeout,
    BridgeCommandResponse,
    _copy_created_at,
)
from stackchanctl.backends import bridge as bridge_module  # noqa: E402
from stackchanctl.cli import run_cli  # noqa: E402
from stackchanctl.contract import DeviceStatus, ErrorDetail, ResultState  # noqa: E402


FIXED_NOW = datetime(2026, 5, 16, 0, 0, tzinfo=UTC)


class FakeBridgeClient:
    def __init__(self, *, timeout: bool = False) -> None:
        self.timeout = timeout

    def get_status(self, device_id: str, timeout: float) -> DeviceStatus:
        if self.timeout:
            raise BridgeBackendTimeout()
        return DeviceStatus(
            device_id=device_id,
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
        return BridgeCommandResponse(
            ok=True,
            result_state=ResultState.COMPLETED if wait else ResultState.ACCEPTED,
        )

    def capture_audio(
        self,
        meta,
        seconds: float,
        output: str,
        *,
        wait: bool,
        timeout: float,
    ) -> BridgeCommandResponse:
        return BridgeCommandResponse(
            ok=True,
            result_state=ResultState.COMPLETED if wait else ResultState.ACCEPTED,
        )

    def capture_camera(
        self, meta, output: str, quality: int, *, wait: bool, timeout: float
    ) -> BridgeCommandResponse:
        return BridgeCommandResponse(
            ok=True,
            result_state=ResultState.COMPLETED if wait else ResultState.ACCEPTED,
        )

    @staticmethod
    def _accepted() -> BridgeCommandResponse:
        return BridgeCommandResponse(ok=True, result_state=ResultState.ACCEPTED)


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
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "observe", "--json"],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["device_id"], "default")
        self.assertEqual(payload["device_state"], "idle")

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

    def test_bridge_audio_play_keeps_json_shape(self) -> None:
        code, stdout, stderr = run_stackchanctl(
            ["--backend", "bridge", "audio", "play", "prompt.wav", "--json"],
            FakeBridgeClient(),
        )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["result_state"], "ACCEPTED")
        self.assertEqual(payload["command"], {"type": "audio.play", "path": "prompt.wav"})

    def test_bridge_audio_capture_wait_can_complete(self) -> None:
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

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["result_state"], "COMPLETED")
        self.assertEqual(payload["command"]["type"], "audio.capture")
        self.assertEqual(payload["command"]["output"], "mic.wav")

    def test_bridge_camera_capture_wait_can_complete(self) -> None:
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

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["result_state"], "COMPLETED")
        self.assertEqual(payload["command"]["type"], "camera.capture")
        self.assertEqual(payload["command"]["quality"], 80)

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


if __name__ == "__main__":
    unittest.main()
