from __future__ import annotations

import json
import socket
import unittest
import urllib.error

from stackchan_bridge.asr import (
    AsrError,
    AsrResult,
    LocalAsrWorker,
    WhisperHttpAsrEngine,
    _parse_transcription_response,
)
from stackchan_bridge.audio_session import Utterance


def utterance() -> Utterance:
    return Utterance(
        device_id="default",
        utterance_id="utt-001",
        command_id="cmd-1",
        pcm=b"\x00\x00" * 320,
        frame_count=2,
        duration_ms=20,
    )


class WhisperHttpAsrEngineTests(unittest.TestCase):
    def test_transcribe_posts_openai_compatible_wav_request(self) -> None:
        calls = []

        def http_post(url: str, data: bytes, headers: dict[str, str], timeout_sec: float) -> bytes:
            calls.append((url, data, headers, timeout_sec))
            return json.dumps(
                {
                    "text": "redacted transcript",
                    "language": "en",
                    "segments": [{"no_speech_prob": 0.2}],
                }
            ).encode("utf-8")

        engine = WhisperHttpAsrEngine(
            endpoint="http://asr.local:8000/",
            model="local-model",
            language="en",
            timeout_sec=3.5,
            http_post=http_post,
        )

        result = engine.transcribe(utterance())

        self.assertEqual(result, AsrResult("redacted transcript", 0.8, language="en"))
        url, body, headers, timeout_sec = calls[0]
        self.assertEqual(url, "http://asr.local:8000/v1/audio/transcriptions")
        self.assertEqual(timeout_sec, 3.5)
        self.assertIn("multipart/form-data; boundary=", headers["Content-Type"])
        self.assertIn(b'Content-Disposition: form-data; name="response_format"', body)
        self.assertIn(b"verbose_json", body)
        self.assertIn(b'Content-Disposition: form-data; name="model"', body)
        self.assertIn(b"local-model", body)
        self.assertIn(b'Content-Disposition: form-data; name="language"', body)
        self.assertIn(b'Content-Type: audio/wav', body)
        self.assertIn(b"RIFF", body)

    def test_missing_endpoint_is_structured(self) -> None:
        engine = WhisperHttpAsrEngine(endpoint="")

        with self.assertRaises(AsrError) as caught:
            engine.transcribe(utterance())

        self.assertEqual(caught.exception.code, "ASR_UNAVAILABLE")
        self.assertFalse(caught.exception.recoverable)

    def test_http_error_maps_to_worker_failed(self) -> None:
        def http_post(url: str, data: bytes, headers: dict[str, str], timeout_sec: float) -> bytes:
            del url, data, headers, timeout_sec
            raise urllib.error.HTTPError("http://asr.local", 500, "error", {}, None)

        engine = WhisperHttpAsrEngine(endpoint="http://asr.local", http_post=http_post)

        with self.assertRaises(AsrError) as caught:
            engine.transcribe(utterance())

        self.assertEqual(caught.exception.code, "ASR_WORKER_FAILED")

    def test_url_error_maps_to_unavailable(self) -> None:
        def http_post(url: str, data: bytes, headers: dict[str, str], timeout_sec: float) -> bytes:
            del url, data, headers, timeout_sec
            raise urllib.error.URLError("connection refused")

        engine = WhisperHttpAsrEngine(endpoint="http://asr.local", http_post=http_post)

        with self.assertRaises(AsrError) as caught:
            engine.transcribe(utterance())

        self.assertEqual(caught.exception.code, "ASR_UNAVAILABLE")

    def test_url_error_timeout_maps_to_timeout(self) -> None:
        def http_post(url: str, data: bytes, headers: dict[str, str], timeout_sec: float) -> bytes:
            del url, data, headers, timeout_sec
            raise urllib.error.URLError(TimeoutError("slow"))

        engine = WhisperHttpAsrEngine(endpoint="http://asr.local", http_post=http_post)

        with self.assertRaises(AsrError) as caught:
            engine.transcribe(utterance())

        self.assertEqual(caught.exception.code, "ASR_TIMEOUT")

    def test_socket_timeout_maps_to_timeout(self) -> None:
        def http_post(url: str, data: bytes, headers: dict[str, str], timeout_sec: float) -> bytes:
            del url, data, headers, timeout_sec
            raise TimeoutError("slow")

        engine = WhisperHttpAsrEngine(endpoint="http://asr.local", http_post=http_post)

        with self.assertRaises(AsrError) as caught:
            engine.transcribe(utterance())

        self.assertEqual(caught.exception.code, "ASR_TIMEOUT")

    def test_socket_timeout_subclass_maps_to_timeout(self) -> None:
        def http_post(url: str, data: bytes, headers: dict[str, str], timeout_sec: float) -> bytes:
            del url, data, headers, timeout_sec
            raise socket.timeout("slow")

        engine = WhisperHttpAsrEngine(endpoint="http://asr.local", http_post=http_post)

        with self.assertRaises(AsrError) as caught:
            engine.transcribe(utterance())

        self.assertEqual(caught.exception.code, "ASR_TIMEOUT")

    def test_invalid_json_is_structured(self) -> None:
        with self.assertRaises(AsrError) as caught:
            _parse_transcription_response(b"{")

        self.assertEqual(caught.exception.code, "ASR_INVALID_OUTPUT")

    def test_missing_text_is_structured(self) -> None:
        with self.assertRaises(AsrError) as caught:
            _parse_transcription_response(b'{"language":"en"}')

        self.assertEqual(caught.exception.code, "ASR_INVALID_OUTPUT")

    def test_empty_transcript_is_rejected_by_worker_boundary(self) -> None:
        def http_post(url: str, data: bytes, headers: dict[str, str], timeout_sec: float) -> bytes:
            del url, data, headers, timeout_sec
            return b'{"text":"","segments":[]}'

        worker = LocalAsrWorker(
            WhisperHttpAsrEngine(endpoint="http://asr.local", http_post=http_post),
            timeout_ms=1000,
        )

        with self.assertRaises(AsrError) as caught:
            worker.transcribe(utterance())

        self.assertEqual(caught.exception.code, "ASR_EMPTY_RESULT")
        worker.close()

    def test_invalid_confidence_is_rejected_by_worker_boundary(self) -> None:
        class InvalidConfidenceEngine:
            def transcribe(self, value: Utterance) -> AsrResult:
                del value
                return AsrResult("redacted transcript", 1.5)

        worker = LocalAsrWorker(InvalidConfidenceEngine(), timeout_ms=1000)

        with self.assertRaises(AsrError) as caught:
            worker.transcribe(utterance())

        self.assertEqual(caught.exception.code, "ASR_INVALID_OUTPUT")
        worker.close()

    def test_response_shapes_and_confidence_are_bounded(self) -> None:
        self.assertEqual(_parse_transcription_response(b'"hello"'), AsrResult("hello", 1.0))
        result = _parse_transcription_response(
            b'{"text":"hello","segments":[{"no_speech_prob":2.0}]}'
        )

        self.assertEqual(result.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
