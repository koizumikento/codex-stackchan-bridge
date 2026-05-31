from __future__ import annotations

import unittest

from stackchan_bridge.audio_session import (
    AUDIO_DIRECTION_CAPTURE,
    AUDIO_FORMAT_PCM_S16LE,
    AudioChunk,
    AudioFrame,
    AudioSessionError,
    BoundedDropQueue,
    VadConfig,
    VadStateMachine,
    energy_speech_detector,
    split_capture_chunk,
)


def frame(speech: bool, index: int = 0) -> AudioFrame:
    byte = b"\xff" if speech else b"\x80"
    return AudioFrame("default", "cmd-1", 1, index, byte * 320)


def pcm_frame(sample: int) -> AudioFrame:
    return AudioFrame("default", "cmd-1", 1, 0, int(sample).to_bytes(2, "little", signed=True) * 160)


class AudioSessionTests(unittest.TestCase):
    def test_splits_20ms_capture_chunk_into_10ms_frames(self) -> None:
        chunk = AudioChunk(
            device_id="default",
            command_id="cmd-1",
            direction=AUDIO_DIRECTION_CAPTURE,
            sequence=7,
            format=AUDIO_FORMAT_PCM_S16LE,
            sample_rate=16000,
            channels=1,
            pcm=b"\x80" * 640,
        )

        frames = split_capture_chunk(chunk)

        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].sequence, 7)
        self.assertEqual(len(frames[0].pcm), 320)

    def test_rejects_malformed_capture_chunk(self) -> None:
        chunk = AudioChunk("default", "cmd-1", AUDIO_DIRECTION_CAPTURE, 1, AUDIO_FORMAT_PCM_S16LE, 16000, 1, b"\x00")

        with self.assertRaises(AudioSessionError) as raised:
            split_capture_chunk(chunk)

        self.assertEqual(raised.exception.code, "MALFORMED_AUDIO_CHUNK")

    def test_energy_speech_detector_treats_pcm_s16le_zero_as_silence(self) -> None:
        self.assertFalse(energy_speech_detector(pcm_frame(0)))
        self.assertFalse(energy_speech_detector(pcm_frame(256)))
        self.assertTrue(energy_speech_detector(pcm_frame(1024)))
        self.assertTrue(energy_speech_detector(pcm_frame(-1024)))

    def test_vad_emits_detected_then_utterance(self) -> None:
        vad = VadStateMachine(
            config=VadConfig(start_frames=2, end_silence_ms=20, pre_roll_ms=10, post_roll_ms=10, min_utterance_ms=20)
        )

        self.assertFalse(vad.feed(frame(False), is_speech=False).speech_detected)
        self.assertFalse(vad.feed(frame(True, 1), is_speech=True).speech_detected)
        self.assertTrue(vad.feed(frame(True, 2), is_speech=True).speech_detected)
        self.assertIsNone(vad.feed(frame(False, 3), is_speech=False).utterance)
        utterance = vad.feed(frame(False, 4), is_speech=False).utterance

        self.assertIsNotNone(utterance)
        self.assertEqual(utterance.device_id, "default")
        self.assertGreaterEqual(utterance.duration_ms, 20)

    def test_vad_flushes_open_utterance_when_capture_window_ends(self) -> None:
        vad = VadStateMachine(
            config=VadConfig(start_frames=2, end_silence_ms=200, pre_roll_ms=10, post_roll_ms=10, min_utterance_ms=20)
        )

        vad.feed(frame(True, 1), is_speech=True)
        vad.feed(frame(True, 2), is_speech=True)
        utterance = vad.flush()

        self.assertIsNotNone(utterance)
        self.assertEqual(utterance.command_id, "cmd-1")
        self.assertGreaterEqual(utterance.duration_ms, 20)
        self.assertIsNone(vad.flush())

    def test_bounded_queue_drops_oldest(self) -> None:
        queue: BoundedDropQueue[int] = BoundedDropQueue(2)

        self.assertIsNone(queue.push(1))
        self.assertIsNone(queue.push(2))
        self.assertEqual(queue.push(3), 1)
        self.assertEqual(queue.pop(), 2)
        self.assertEqual(queue.pop(), 3)


if __name__ == "__main__":
    unittest.main()
