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
from stackchan_bridge.speech_node import SpeechSessionProcessor, detect_immediate_safety_action


def chunk(direction: int, pcm: bytes | None = None) -> AudioChunk:
    return AudioChunk(
        device_id="default",
        command_id="cmd-1",
        direction=direction,
        sequence=1,
        format=AUDIO_FORMAT_PCM_S16LE,
        sample_rate=16000,
        channels=1,
        pcm=pcm if pcm is not None else b"\xff" * 640,
    )


class CrashingEchoWorker(NullEchoController):
    def process_capture(self, frame: AudioFrame, *, delay_ms: int | None = None):
        del frame, delay_ms
        raise TimeoutError("stuck")


class SlowEngine:
    def transcribe(self, utterance):
        del utterance
        time.sleep(0.2)
        return AsrResult("late", 1.0)


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

        for _ in range(4):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))
        processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\x80" * 640))
        processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\x80" * 640))

        ready = [event for event in processor.events if event.event_name == "transcript_ready"]
        semantic = [event for event in processor.events if event.event_name == "voice_semantic_event"]

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

        for _ in range(4):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))
        for _ in range(2):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\x80" * 640))

        self.assertFalse([event for event in processor.events if event.event_name == "transcript_ready"])
        semantic = [event for event in processor.events if event.event_name == "voice_semantic_event"]
        self.assertEqual(semantic[-1].payload["suppressed_reason"], "low_confidence")

    def test_asr_worker_timeout_is_structured(self) -> None:
        worker = LocalAsrWorker(SlowEngine(), timeout_ms=1)
        processor = SpeechSessionProcessor(
            asr_worker=worker,
            speech_detector=lambda frame: frame.pcm[0] != 0x80,
            vad_config=self.short_vad(),
        )

        for _ in range(4):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE))
        for _ in range(2):
            processor.handle_audio_chunk(chunk(AUDIO_DIRECTION_CAPTURE, b"\x80" * 640))

        failures = [event for event in processor.events if event.event_name == "transcript_failed"]
        self.assertEqual(failures[-1].payload["error_code"], "ASR_TIMEOUT")
        worker.close()

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


if __name__ == "__main__":
    unittest.main()
