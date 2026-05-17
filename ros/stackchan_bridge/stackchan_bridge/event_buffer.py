"""Per-device event ring buffer with observe cursors."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
from threading import RLock
from typing import Any

EVENT_ID_MAX_LENGTH = 36
DEVICE_ID_MAX_LENGTH = 32
EVENT_NAME_MAX_LENGTH = 32
SOURCE_MAX_LENGTH = 32
COMMAND_ID_MAX_LENGTH = 36
PAYLOAD_JSON_MAX_LENGTH = 256


@dataclass(frozen=True)
class EventRecord:
    """Hardware-free model of a high-level bridge event."""

    sequence: int
    event_id: str
    device_id: str
    event_name: str
    stamp: float
    command_id: str = ""
    source: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)


class EventBuffer:
    """Retains bounded per-device events and tracks consumer cursors."""

    def __init__(
        self,
        *,
        maxlen: int = 32,
        max_cursors: int = 64,
        cursor_ttl_seconds: float = 3600.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if maxlen < 1:
            raise ValueError("maxlen must be at least 1")
        if max_cursors < 1:
            raise ValueError("max_cursors must be at least 1")
        if cursor_ttl_seconds < 0:
            raise ValueError("cursor_ttl_seconds must be non-negative")
        self.maxlen = maxlen
        self.max_cursors = max_cursors
        self.cursor_ttl_seconds = cursor_ttl_seconds
        self._clock = clock
        self._events: dict[str, deque[EventRecord]] = defaultdict(
            lambda: deque(maxlen=maxlen)
        )
        self._cursors: dict[tuple[str, str], int] = {}
        self._cursor_touched: dict[tuple[str, str], float] = {}
        self._next_sequence = 1
        self._lock = RLock()

    def append(
        self,
        device_id: str,
        event_name: str,
        *,
        command_id: str = "",
        source: str = "",
        event_id: str = "",
        payload: Mapping[str, Any] | None = None,
        stamp: float | None = None,
    ) -> EventRecord:
        """Append an event to the device ring buffer."""

        with self._lock:
            sequence = self._next_sequence
            bounded_payload = _bounded_payload(payload or {})
            record = EventRecord(
                sequence=sequence,
                event_id=_bounded_text(event_id or f"evt-{sequence:08d}", EVENT_ID_MAX_LENGTH),
                device_id=_bounded_text(device_id, DEVICE_ID_MAX_LENGTH),
                event_name=_bounded_text(event_name, EVENT_NAME_MAX_LENGTH),
                stamp=self._clock() if stamp is None else stamp,
                command_id=_bounded_text(command_id, COMMAND_ID_MAX_LENGTH),
                source=_bounded_text(source, SOURCE_MAX_LENGTH),
                payload=bounded_payload,
            )
            self._next_sequence = sequence + 1
            self._events[device_id].append(record)
            return record

    def records(self, device_id: str, *, limit: int | None = None) -> tuple[EventRecord, ...]:
        """Return retained events for one device without changing cursors."""

        with self._lock:
            return _limit(tuple(self._events.get(device_id, ())), limit)

    def read(
        self,
        device_id: str,
        consumer_id: str,
        *,
        limit: int | None = None,
    ) -> tuple[EventRecord, ...]:
        """Read events after the consumer cursor and advance that cursor."""

        if not consumer_id:
            raise ValueError("consumer_id is required")
        with self._lock:
            now = self._clock()
            self._prune_cursors(now)
            cursor_key = (consumer_id, device_id)
            after_sequence = self._cursors.get(cursor_key, 0)
            available = tuple(
                record
                for record in self._events.get(device_id, ())
                if record.sequence > after_sequence
            )
            selected = _head_limit(available, limit)
            if selected:
                if cursor_key not in self._cursors:
                    self._reserve_cursor_slot()
                self._cursors[cursor_key] = selected[-1].sequence
                self._cursor_touched[cursor_key] = now
            return selected

    def clear_cursor(self, consumer_id: str, device_id: str | None = None) -> None:
        """Forget cursor positions without deleting retained ring-buffer events."""

        if not consumer_id:
            raise ValueError("consumer_id is required")
        with self._lock:
            if device_id is not None:
                self._cursors.pop((consumer_id, device_id), None)
                self._cursor_touched.pop((consumer_id, device_id), None)
                return
            for cursor_key in tuple(self._cursors):
                if cursor_key[0] == consumer_id:
                    self._cursors.pop(cursor_key, None)
                    self._cursor_touched.pop(cursor_key, None)

    def cursor_sequence(self, consumer_id: str, device_id: str) -> int | None:
        """Return the last delivered sequence for diagnostics and tests."""

        with self._lock:
            return self._cursors.get((consumer_id, device_id))

    def _prune_cursors(self, now: float) -> None:
        if self.cursor_ttl_seconds == 0:
            self._cursors.clear()
            self._cursor_touched.clear()
            return

        expired = tuple(
            cursor_key
            for cursor_key, touched in self._cursor_touched.items()
            if now - touched >= self.cursor_ttl_seconds
        )
        for cursor_key in expired:
            self._cursors.pop(cursor_key, None)
            self._cursor_touched.pop(cursor_key, None)

    def _reserve_cursor_slot(self) -> None:
        while len(self._cursors) >= self.max_cursors and self._cursor_touched:
            oldest = min(self._cursor_touched, key=self._cursor_touched.__getitem__)
            self._cursors.pop(oldest, None)
            self._cursor_touched.pop(oldest, None)


def _limit(records: tuple[EventRecord, ...], limit: int | None) -> tuple[EventRecord, ...]:
    if limit is None:
        return records
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if limit == 0:
        return ()
    return records[-limit:]


def _head_limit(
    records: tuple[EventRecord, ...], limit: int | None
) -> tuple[EventRecord, ...]:
    if limit is None:
        return records
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if limit == 0:
        return ()
    return records[:limit]


def _bounded_text(value: str, max_length: int) -> str:
    return str(value or "")[:max_length]


def _bounded_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    copied = dict(payload)
    compact = json.dumps(copied, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(compact.encode("utf-8")) <= PAYLOAD_JSON_MAX_LENGTH:
        return copied
    return {
        "truncated": True,
        "reason": "payload_json_exceeds_256_bytes",
    }
