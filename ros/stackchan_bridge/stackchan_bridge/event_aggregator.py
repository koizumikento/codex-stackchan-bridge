"""Event normalization and debounce helpers for observe support."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

from stackchan_bridge.event_buffer import EventBuffer, EventRecord
from stackchan_bridge.redaction import redact_payload

_NON_EVENT_CHARACTERS = re.compile(r"[^a-z0-9_]+")
_UNDERSCORES = re.compile(r"_+")

EVENT_NAME_ALIASES = {
    "camera_failed": "camera_capture_failed",
    "nfc": "nfc_detected",
    "nfc_tag": "nfc_detected",
    "pickup": "picked_up",
}


class EventAggregator:
    """Normalizes raw bridge/device events and suppresses short duplicates."""

    def __init__(
        self,
        buffer: EventBuffer | None = None,
        *,
        debounce_seconds: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if debounce_seconds < 0:
            raise ValueError("debounce_seconds must be non-negative")
        self.buffer = buffer or EventBuffer()
        self.debounce_seconds = debounce_seconds
        self._clock = clock
        self._last_emit: dict[tuple[str, str, str, str], float] = {}

    def add(
        self,
        device_id: str,
        event_name: str,
        *,
        command_id: str = "",
        source: str = "",
        event_id: str = "",
        payload: Mapping[str, Any] | str | None = None,
        stamp: float | None = None,
    ) -> EventRecord | None:
        """Normalize, debounce, and append an event.

        Returns ``None`` when a duplicate falls inside the debounce window.
        """

        normalized_name = normalize_event_name(event_name)
        normalized_payload = normalize_payload(payload)
        now = self._clock()
        fingerprint = _fingerprint(normalized_payload)
        debounce_key = (device_id, normalized_name, command_id, fingerprint)
        last_emit = self._last_emit.get(debounce_key)
        if last_emit is not None and now - last_emit < self.debounce_seconds:
            return None

        self._last_emit[debounce_key] = now
        return self.buffer.append(
            device_id,
            normalized_name,
            command_id=command_id,
            source=source,
            event_id=event_id,
            payload=normalized_payload,
            stamp=stamp,
        )


def normalize_event_name(event_name: str) -> str:
    """Convert device/worker event names into the documented event style."""

    normalized = event_name.strip().lower().replace("-", "_").replace(" ", "_")
    normalized = _NON_EVENT_CHARACTERS.sub("_", normalized)
    normalized = _UNDERSCORES.sub("_", normalized).strip("_")
    normalized = normalized or "unknown"
    return EVENT_NAME_ALIASES.get(normalized, normalized)


def normalize_payload(payload: Mapping[str, Any] | str | None) -> dict[str, Any]:
    """Return redacted, JSON-compatible event metadata."""

    if payload is None:
        return {}
    if isinstance(payload, str):
        try:
            loaded = json.loads(payload)
        except json.JSONDecodeError:
            return {"value": payload}
        if isinstance(loaded, Mapping):
            return dict(redact_payload(loaded))
        return {"value": redact_payload(loaded)}
    return dict(redact_payload(payload))


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)
