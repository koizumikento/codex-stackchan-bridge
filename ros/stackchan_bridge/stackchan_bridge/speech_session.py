"""Memory-only speech transcript storage for bridge-local coordination."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

TRANSCRIPT_TTL_SECONDS = 10 * 60


@dataclass(frozen=True)
class SpeechTranscript:
    """Speech text retained briefly for local bridge coordination only."""

    device_id: str
    utterance_id: str
    text: str
    created_at: float
    expires_at: float
    command_id: str = ""
    voice: str = ""
    source: str = ""


class SpeechTranscriptStore:
    """In-memory transcript store with a fixed default TTL."""

    def __init__(
        self,
        *,
        ttl_seconds: float = TRANSCRIPT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._records: dict[tuple[str, str], SpeechTranscript] = {}

    def put(
        self,
        device_id: str,
        utterance_id: str,
        text: str,
        *,
        command_id: str = "",
        voice: str = "",
        source: str = "",
    ) -> SpeechTranscript:
        """Store a transcript until TTL expiry."""

        now = self._clock()
        self.clear_expired(now=now)
        record = SpeechTranscript(
            device_id=device_id,
            utterance_id=utterance_id,
            text=text,
            voice=voice,
            source=source,
            created_at=now,
            expires_at=now + self.ttl_seconds,
            command_id=command_id,
        )
        self._records[(device_id, utterance_id)] = record
        return record

    def get(self, device_id: str, utterance_id: str) -> SpeechTranscript | None:
        """Return a non-expired transcript, or ``None`` after expiry."""

        now = self._clock()
        record = self._records.get((device_id, utterance_id))
        if record is None:
            return None
        if record.expires_at <= now:
            self._records.pop((device_id, utterance_id), None)
            return None
        return record

    def list_device(self, device_id: str) -> tuple[SpeechTranscript, ...]:
        """Return non-expired transcripts for one device in insertion order."""

        self.clear_expired()
        return tuple(
            record
            for key, record in self._records.items()
            if key[0] == device_id
        )

    def clear_expired(self, *, now: float | None = None) -> int:
        """Delete expired transcripts and return the number removed."""

        current = self._clock() if now is None else now
        expired_keys = [
            key for key, record in self._records.items() if record.expires_at <= current
        ]
        for key in expired_keys:
            self._records.pop(key, None)
        return len(expired_keys)

    def clear(self, device_id: str | None = None) -> None:
        """Clear all transcripts, or only transcripts for one device."""

        if device_id is None:
            self._records.clear()
            return
        for key in tuple(self._records):
            if key[0] == device_id:
                self._records.pop(key, None)
