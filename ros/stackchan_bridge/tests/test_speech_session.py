from __future__ import annotations

import unittest

from stackchan_bridge.speech_session import (
    TRANSCRIPT_TTL_SECONDS,
    SpeechTranscriptStore,
)


class MutableClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class SpeechTranscriptStoreTests(unittest.TestCase):
    def test_default_ttl_is_ten_minutes(self) -> None:
        self.assertEqual(TRANSCRIPT_TTL_SECONDS, 600)

    def test_transcript_expires_after_ttl(self) -> None:
        clock = MutableClock(100.0)
        store = SpeechTranscriptStore(ttl_seconds=10.0, clock=clock)

        record = store.put("default", "cmd-1", "hello", voice="local")

        self.assertEqual(record.expires_at, 110.0)
        self.assertEqual(store.get("default", "cmd-1"), record)

        clock.now = 110.0

        self.assertIsNone(store.get("default", "cmd-1"))
        self.assertEqual(store.list_device("default"), ())

    def test_transcripts_are_separated_per_device(self) -> None:
        clock = MutableClock(100.0)
        store = SpeechTranscriptStore(clock=clock)

        default = store.put("default", "cmd-1", "hello")
        desk = store.put("desk", "cmd-1", "hello from desk")

        self.assertEqual(store.get("default", "cmd-1"), default)
        self.assertEqual(store.get("desk", "cmd-1"), desk)
        self.assertEqual(store.list_device("default"), (default,))

    def test_transcript_metadata_keeps_confidence_and_language(self) -> None:
        store = SpeechTranscriptStore(clock=MutableClock(100.0))

        record = store.put(
            "default",
            "utt-1",
            "hello",
            confidence=0.82,
            language="ja",
        )

        self.assertEqual(record.confidence, 0.82)
        self.assertEqual(record.language, "ja")


if __name__ == "__main__":
    unittest.main()
