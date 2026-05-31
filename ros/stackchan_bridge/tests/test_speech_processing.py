from __future__ import annotations

import time
import unittest

from stackchan_bridge.asr import AsrResult, LocalAsrWorker, StaticAsrEngine
from stackchan_bridge.audio_session import (
    AUDIO_DIRECTION_CAPTURE,
    AUDIO_DIRECTION_PLAYBACK,
    AUDIO_FORMAT_PCM_S16LE,
    AudioChunk,
    AudioFrame,
    VadConfig,
)
from stackchan_bridge.echo_control import EchoGateFallback, NullEchoController, WorkerEchoController
from stackchan_bridge.speech_node import (
    SpeechEvent,
    SpeechSessionProcessor,
    detect_immediate_safety_action,
    speech_event_payload_json,
)


def chunk(direction: int, pcm: bytes | None = None, *, command_id: str = "cmd-1") -> AudioChunk:
    return AudioChunk(
        device_id="default",
        command_id=command_id,
        direction=direction,
        sequence=1,
        format=AUDIO_FORMAT_PCM_S16LE,
        sample_rate=16000,
        channels=1,
        pcm=pcm if pcm is not None else b"\xff" * 640,
    )


def wait_for_events(processor: SpeechSessionProcessor, event_name: str, *, count: int = 1):
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        events = [event for event in processor.events if event.event_name == event_name]
        if len(events) >= count:
            return events
        time.sleep(0.01)
    return [event for event in processor.events if event.event_name == event_name]


class CrashingEchoWorker(NullEchoController):
    def process_capture(self, frame: AudioFrame, *, delay_ms: int | None = None):
        del frame, delay_ms
        raise TimeoutError("stuck")


class SlowEngine:
    def transcribe(self, utterance):
        del utterance
        time.sleep(0.2)
        return AsrResult("late", 1.0)


class FailingEngine:
    def transcribe(self, utterance):
        del utterance
        raise RuntimeError("backend crashed")


class SpeechProcessingTests(unittest.TestCase):
    def short_vad(self) -> VadConfig:
        return VadConfig(start_frames=2, end_silence_ms=20, pre_roll_ms=10, post_roll_ms=10, min_utterance_ms=20)

    def test_playback_reference_gates_capture_when_aec_unavailable(self) -> None:
        processor = SpeechSessionProcessor(
            echo_controller=EchoGateFallback(hangover_frames=2),
            asr_worker=LocalAsrWorker(StaticAsrEngine(AsrResult("hello", 0.9)), timeout_ms=1000),
            speech_detector=lambda frame: True,
            vad_config=self.short_vad(),
        )
        self.addCleanup(processor.close)

        processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_PLAYBACK))
        events = processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))

        self.assertTrue(any(event.event_name == "voice_semantic_event" for event in events))
        self.assertEqual(events[0].payload["suppressed_reason"], "playback_hangover")
        self.assertFalse(any(event.event_name == "transcript_ready" for event in events))

    def test_transcript_ready_event_redacts_text_and_store_keeps_text(self) -> None:
        processor = SpeechSessionProcessor(
            asr_worker=LocalAsrWorker(StaticAsrEngine(AsrResult("止まって", 0.91)), timeout_ms=1000),
            speech_detector=lambda frame: frame.pcm[0] != 0x80,
            vad_config=self.short_vad(),
        )
        self.addCleanup(processor.close)

        for _ in range(4):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))
        processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\x80" * 640))
        processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\x80" * 640))

        ready = wait_for_events(processor, "transcript_ready")
        semantic = wait_for_events(processor, "voice_semantic_event")

        self.assertTrue(ready)
        self.assertNotIn("止まって", str(ready[0].payload))
        record = processor.transcript_store.get("default", ready[0].payload["utterance_id"])
        self.assertIsNotNone(record)
        self.assertEqual(record.text, "止まって")
        self.assertEqual(semantic[-1].payload["safety_action"], "stop")

    def test_low_confidence_does_not_store_transcript(self) -> None:
        processor = SpeechSessionProcessor(
            asr_worker=LocalAsrWorker(StaticAsrEngine(AsrResult("look left", 0.4)), timeout_ms=1000),
            speech_detector=lambda frame: frame.pcm[0] != 0x80,
            confidence_threshold=0.75,
            vad_config=self.short_vad(),
        )
        self.addCleanup(processor.close)

        for _ in range(4):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))
        for _ in range(2):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\x80" * 640))

        semantic = wait_for_events(processor, "voice_semantic_event")
        self.assertFalse([event for event in processor.events if event.event_name == "transcript_ready"])
        self.assertEqual(semantic[-1].payload["suppressed_reason"], "low_confidence")

    def test_asr_worker_timeout_is_structured(self) -> None:
        worker = LocalAsrWorker(SlowEngine(), timeout_ms=1)
        processor = SpeechSessionProcessor(
            asr_worker=worker,
            speech_detector=lambda frame: frame.pcm[0] != 0x80,
            vad_config=self.short_vad(),
        )
        self.addCleanup(processor.close)

        for _ in range(4):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))
        for _ in range(2):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\x80" * 640))

        failures = wait_for_events(processor, "transcript_failed")
        self.assertEqual(failures[-1].payload["error_code"], "ASR_TIMEOUT")

    def test_asr_worker_failure_is_structured(self) -> None:
        worker = LocalAsrWorker(FailingEngine(), timeout_ms=1000)
        processor = SpeechSessionProcessor(
            asr_worker=worker,
            speech_detector=lambda frame: frame.pcm[0] != 0x80,
            vad_config=self.short_vad(),
        )
        self.addCleanup(processor.close)

        for _ in range(4):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))
        for _ in range(2):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\x80" * 640))

        failures = wait_for_events(processor, "transcript_failed")
        self.assertEqual(failures[-1].payload["error_code"], "ASR_WORKER_FAILED")

    def test_flush_session_finishes_speech_without_waiting_for_more_silence(self) -> None:
        processor = SpeechSessionProcessor(
            asr_worker=LocalAsrWorker(StaticAsrEngine(AsrResult("hello", 0.9)), timeout_ms=1000),
            speech_detector=lambda frame: True,
            vad_config=VadConfig(start_frames=2, end_silence_ms=700, pre_roll_ms=10, post_roll_ms=10, min_utterance_ms=20),
        )
        self.addCleanup(processor.close)

        processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))
        processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))
        self.assertFalse([event for event in processor.events if event.event_name == "transcript_ready"])

        processor.flush_session("default", "cmd-1")
        ready = wait_for_events(processor, "transcript_ready")

        self.assertTrue(ready)

    def test_vad_sessions_are_separated_by_command_id(self) -> None:
        processor = SpeechSessionProcessor(
            asr_worker=LocalAsrWorker(StaticAsrEngine(AsrResult("hello", 0.9)), timeout_ms=1000),
            speech_detector=lambda frame: True,
            vad_config=self.short_vad(),
        )
        self.addCleanup(processor.close)

        processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\xff" * 320, command_id="cmd-1"))
        processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\xff" * 320, command_id="cmd-2"))
        self.assertFalse([event for event in processor.events if event.event_name == "speech_detected"])

        processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\xff" * 320, command_id="cmd-1"))
        detected = [event for event in processor.events if event.event_name == "speech_detected"]

        self.assertEqual(len(detected), 1)
        self.assertEqual(detected[0].command_id, "cmd-1")

    def test_asr_runs_outside_audio_callback(self) -> None:
        processor = SpeechSessionProcessor(
            asr_worker=LocalAsrWorker(SlowEngine(), timeout_ms=1000),
            speech_detector=lambda frame: frame.pcm[0] != 0x80,
            vad_config=self.short_vad(),
        )
        self.addCleanup(processor.close)

        started = time.monotonic()
        for _ in range(4):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))
        for _ in range(2):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\x80" * 640))

        self.assertLess(time.monotonic() - started, 0.1)

    def test_echo_worker_timeout_falls_back_to_gate(self) -> None:
        controller = WorkerEchoController(CrashingEchoWorker())
        result = controller.process_capture(AudioFrame("default", "cmd-1", 1, 0, b"\x80" * 320))

        self.assertFalse(controller.available)
        self.assertEqual(controller.last_error, "worker_timeout")
        self.assertIn(result.suppressed_reason, {"aec_unavailable", "playback_hangover"})

    def test_safety_detector_ignores_quotes_and_negative_contexts(self) -> None:
        self.assertEqual(detect_immediate_safety_action("止まって"), "stop")
        self.assertEqual(detect_immediate_safety_action("「止まって」と言ったらどうなる？"), "none")
        self.assertEqual(detect_immediate_safety_action("止まらないで"), "none")
        self.assertEqual(detect_immediate_safety_action("ストップというコマンドを追加して"), "none")

    def test_speech_event_payload_bounding_keeps_valid_json(self) -> None:
        payload = speech_event_payload_json(
            SpeechEvent("default", "voice_semantic_event", payload={"value": "x" * 400})
        )

        self.assertLessEqual(len(payload.encode("utf-8")), 256)
        self.assertTrue(payload.startswith("{"))
        self.assertIn("truncated", payload)


if __name__ == "__main__":
    unittest.main()
