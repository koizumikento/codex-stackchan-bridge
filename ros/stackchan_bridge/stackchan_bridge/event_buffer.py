"""Per-device event ring buffer with observe cursors."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from threading import RLock
from typing import Any


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
        clock: Callable[[], float] = time.time,
    ) -> None:
        if maxlen < 1:
            raise ValueError("maxlen must be at least 1")
        self.maxlen = maxlen
        self._clock = clock
        self._events: dict[str, deque[EventRecord]] = defaultdict(
            lambda: deque(maxlen=maxlen)
        )
        self._cursors: dict[tuple[str, str], int] = {}
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
            record = EventRecord(
                sequence=sequence,
                event_id=event_id or f"evt-{sequence:08d}",
                device_id=device_id,
                event_name=event_name,
                stamp=self._clock() if stamp is None else stamp,
                command_id=command_id,
                source=source,
                payload=dict(payload or {}),
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
            cursor_key = (consumer_id, device_id)
            after_sequence = self._cursors.get(cursor_key, 0)
            available = tuple(
                record
                for record in self._events.get(device_id, ())
                if record.sequence > after_sequence
            )
            selected = _head_limit(available, limit)
            if selected:
                self._cursors[cursor_key] = selected[-1].sequence
            return selected

    def clear_cursor(self, consumer_id: str, device_id: str | None = None) -> None:
        """Forget cursor positions without deleting retained ring-buffer events."""

        if not consumer_id:
            raise ValueError("consumer_id is required")
        with self._lock:
            if device_id is not None:
                self._cursors.pop((consumer_id, device_id), None)
                return
            for cursor_key in tuple(self._cursors):
                if cursor_key[0] == consumer_id:
                    self._cursors.pop(cursor_key, None)

    def cursor_sequence(self, consumer_id: str, device_id: str) -> int | None:
        """Return the last delivered sequence for diagnostics and tests."""

        with self._lock:
            return self._cursors.get((consumer_id, device_id))


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
