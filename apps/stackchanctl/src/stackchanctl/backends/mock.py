from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from stackchanctl.contract import (
    CommandRequest,
    CommandResult,
    CommandType,
    DeviceStatus,
    ErrorDetail,
    Event,
    EventListResult,
    Priority,
    ResultState,
    TranscriptResult,
)


DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
ALLOWED_FACES = {"neutral", "happy", "thinking", "surprised", "sleepy", "error"}
ALLOWED_MOTIONS = {"nod", "shake", "look-left", "look-right", "look-user", "idle"}
ALLOWED_LEDS = {"off", "progress", "success", "warning", "error", "listening"}
BASELINE_AUDIO_FORMAT = "pcm_s16le"
BASELINE_AUDIO_SAMPLE_RATE = 16000
BASELINE_AUDIO_CHANNELS = 1
MAX_EVENTS = 32


class MockBackend:
    """Deterministic backend used by tests, skills, and hardware-free demos."""

    def __init__(self) -> None:
        self._events_by_device: dict[str, list[Event]] = {}
        self._event_cursors: dict[tuple[str, str], int] = {}
        self._transcripts_by_device: dict[str, dict[str, TranscriptResult]] = {}

    def execute(
        self, request: CommandRequest
    ) -> CommandResult | DeviceStatus | EventListResult | TranscriptResult:
        validation_error = validate_common_request(request)
        if validation_error is not None:
            return _rejected(request, validation_error)

        if request.command_type is CommandType.OBSERVE:
            return _observe(request)

        if request.timeout <= 0:
            return _timeout_result(request)

        if request.command_type is CommandType.EVENTS_LIST:
            return self._list_events(request)

        if request.command_type is CommandType.EVENTS_NEXT:
            return self._next_event(request)

        if request.command_type is CommandType.EVENTS_CLEAR:
            return self._clear_events(request)

        if request.command_type is CommandType.SPEECH_TRANSCRIPT:
            return self._get_transcript(request)

        result_state = ResultState.COMPLETED if request.wait else ResultState.ACCEPTED
        return CommandResult(
            ok=True,
            result_state=result_state,
            meta=request.meta,
            command=_command_payload(request),
        )

    def _list_events(self, request: CommandRequest) -> EventListResult:
        limit = int(request.args["limit"])
        since_event_id = request.args.get("since_event_id")
        events = self._events_for(request.meta.device_id)
        if since_event_id:
            events = _events_after(events, str(since_event_id))
        selected = events[-limit:]
        return EventListResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=request.meta.device_id,
            events=selected,
            cursor=_cursor_for(selected),
            meta=request.meta,
        )

    def _next_event(self, request: CommandRequest) -> EventListResult:
        events = self._events_for(request.meta.device_id)
        after_event_id = request.args.get("after_event_id")
        consumer_id = str(request.args.get("consumer_id") or request.meta.source)
        if after_event_id:
            candidates = _events_after(events, str(after_event_id))
        else:
            cursor = self._event_cursors.get((consumer_id, request.meta.device_id), 0)
            candidates = events[cursor:]
        if not candidates:
            return EventListResult(
                ok=True,
                result_state=ResultState.COMPLETED,
                device_id=request.meta.device_id,
                events=[],
                cursor=None,
                meta=request.meta,
            )
        event = candidates[0]
        self._event_cursors[(consumer_id, request.meta.device_id)] = events.index(event) + 1
        return EventListResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=request.meta.device_id,
            events=[event],
            cursor=event.event_id,
            meta=request.meta,
        )

    def _clear_events(self, request: CommandRequest) -> EventListResult:
        consumer_id = str(request.args.get("consumer_id") or request.meta.source)
        self._event_cursors.pop((consumer_id, request.meta.device_id), None)
        return EventListResult(
            ok=True,
            result_state=ResultState.COMPLETED,
            device_id=request.meta.device_id,
            events=[],
            cursor=None,
            meta=request.meta,
        )

    def _get_transcript(self, request: CommandRequest) -> TranscriptResult:
        utterance_id = request.args.get("utterance_id")
        transcripts = self._transcripts_for(request.meta.device_id)
        if utterance_id is None:
            return transcripts["mock-utt-001"]
        transcript = transcripts.get(str(utterance_id))
        if transcript is None:
            return TranscriptResult(
                ok=False,
                result_state=ResultState.REJECTED,
                device_id=request.meta.device_id,
                utterance_id=str(utterance_id),
                transcript=None,
                confidence=None,
                expires_at=None,
                meta=request.meta,
                error=ErrorDetail(
                    code="TRANSCRIPT_NOT_FOUND",
                    message=f"transcript {utterance_id!r} was not found",
                    recoverable=False,
                ),
            )
        return replace(transcript, meta=request.meta)

    def _events_for(self, device_id: str) -> list[Event]:
        if device_id not in self._events_by_device:
            self._events_by_device[device_id] = [
                Event(
                    event_id="mock-event-0001",
                    device_id=device_id,
                    event_name="picked_up",
                    source="firmware",
                    stamp="2026-05-16T00:00:01Z",
                    command_id=None,
                    payload={},
                ),
                Event(
                    event_id="mock-event-0002",
                    device_id=device_id,
                    event_name="transcript_ready",
                    source="speech_session",
                    stamp="2026-05-16T00:00:02Z",
                    command_id=None,
                    payload={"utterance_id": "mock-utt-001"},
                ),
            ]
        return self._events_by_device[device_id]

    def _transcripts_for(self, device_id: str) -> dict[str, TranscriptResult]:
        if device_id not in self._transcripts_by_device:
            self._transcripts_by_device[device_id] = {
                "mock-utt-001": TranscriptResult(
                    ok=True,
                    result_state=ResultState.COMPLETED,
                    device_id=device_id,
                    utterance_id="mock-utt-001",
                    transcript="mock transcript",
                    confidence=1.0,
                    expires_at="2026-05-16T00:10:02Z",
                    meta=None,
                )
            }
        return self._transcripts_by_device[device_id]


def validate_common_request(request: CommandRequest) -> ErrorDetail | None:
    device_id = request.meta.device_id
    if not DEVICE_ID_PATTERN.fullmatch(device_id):
        return ErrorDetail(
            code="INVALID_DEVICE_ID",
            message=f"invalid device_id {device_id!r}; use ASCII letters, numbers, '_' or '-'",
            recoverable=False,
        )

    if device_id in {"missing", "unknown"}:
        return ErrorDetail(
            code="DEVICE_NOT_FOUND",
            message=f"device {device_id!r} is not registered",
            recoverable=False,
        )

    if request.meta.priority is Priority.SAFETY:
        return ErrorDetail(
            code="INVALID_PRIORITY",
            message="CLI priority SAFETY is reserved for bridge and firmware internals",
            recoverable=False,
        )

    if request.command_type is CommandType.FACE and request.args["name"] not in ALLOWED_FACES:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message=f"unknown face {request.args['name']!r}",
            recoverable=False,
        )

    if request.command_type is CommandType.MOTION and request.args["name"] not in ALLOWED_MOTIONS:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message=f"unknown motion {request.args['name']!r}",
            recoverable=False,
        )

    if request.command_type is CommandType.LED and request.args["pattern"] not in ALLOWED_LEDS:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message=f"unknown LED pattern {request.args['pattern']!r}",
            recoverable=False,
        )

    if request.command_type is CommandType.SAY and not request.args["text"]:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message="say requires non-empty text",
            recoverable=False,
        )

    if request.command_type is CommandType.AUDIO_PLAY and not request.args["path"]:
        return ErrorDetail(
            code="UNKNOWN_COMMAND",
            message="audio play requires a path",
            recoverable=False,
        )

    if request.command_type is CommandType.AUDIO_CAPTURE:
        seconds = float(request.args["seconds"])
        if seconds <= 0:
            return ErrorDetail(
                code="UNKNOWN_COMMAND",
                message="audio capture requires a positive duration",
                recoverable=False,
            )
        if not request.args["output"]:
            return ErrorDetail(
                code="UNKNOWN_COMMAND",
                message="audio capture requires an output path",
                recoverable=False,
            )

    if request.command_type is CommandType.CAMERA_CAPTURE:
        quality = int(request.args["quality"])
        if quality < 1 or quality > 95:
            return ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera quality must be between 1 and 95",
                recoverable=True,
            )
        if not request.args["output"]:
            return ErrorDetail(
                code="CAMERA_CAPTURE_FAILED",
                message="camera capture requires an output path",
                recoverable=True,
            )

    if request.command_type is CommandType.IMU_STREAM:
        hz = float(request.args["hz"])
        if hz < 10 or hz > 30:
            return ErrorDetail(
                code="UNSUPPORTED_FEATURE",
                message="IMU stream rate must be between 10 and 30 Hz",
                recoverable=False,
            )

    if request.command_type in {CommandType.EVENTS_LIST, CommandType.EVENTS_NEXT}:
        limit = int(request.args["limit"])
        if limit < 1 or limit > MAX_EVENTS:
            return ErrorDetail(
                code="UNKNOWN_COMMAND",
                message="events limit must be between 1 and 32",
                recoverable=False,
            )

    return None


def _observe(request: CommandRequest) -> DeviceStatus:
    if request.meta.device_id == "disconnected":
        return DeviceStatus(
            device_id=request.meta.device_id,
            connected=False,
            device_state="disconnected",
            face="neutral",
            last_error=ErrorDetail(
                code="TRANSPORT_DISCONNECTED",
                message="mock device is disconnected",
                recoverable=True,
            ),
            meta=request.meta,
        )

    return DeviceStatus(
        device_id=request.meta.device_id,
        connected=True,
        device_state="idle",
        face="neutral",
        meta=request.meta,
    )


def _rejected(request: CommandRequest, error: ErrorDetail) -> CommandResult | EventListResult | TranscriptResult:
    if request.command_type in {
        CommandType.EVENTS_LIST,
        CommandType.EVENTS_NEXT,
        CommandType.EVENTS_CLEAR,
    }:
        return EventListResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            events=[],
            meta=request.meta,
            error=error,
        )
    if request.command_type is CommandType.SPEECH_TRANSCRIPT:
        return TranscriptResult(
            ok=False,
            result_state=ResultState.REJECTED,
            device_id=request.meta.device_id,
            utterance_id=request.args.get("utterance_id"),
            transcript=None,
            confidence=None,
            expires_at=None,
            meta=request.meta,
            error=error,
        )
    return CommandResult(
        ok=False,
        result_state=ResultState.REJECTED,
        meta=request.meta,
        command=_command_payload(request),
        error=error,
    )


def _timeout_result(request: CommandRequest) -> CommandResult | EventListResult | TranscriptResult:
    error = ErrorDetail(
        code="TIMEOUT",
        message="command timed out before acceptance",
        recoverable=True,
    )
    if request.command_type in {
        CommandType.EVENTS_LIST,
        CommandType.EVENTS_NEXT,
        CommandType.EVENTS_CLEAR,
    }:
        return EventListResult(
            ok=False,
            result_state=ResultState.TIMEOUT,
            device_id=request.meta.device_id,
            events=[],
            meta=request.meta,
            error=error,
        )
    if request.command_type is CommandType.SPEECH_TRANSCRIPT:
        return TranscriptResult(
            ok=False,
            result_state=ResultState.TIMEOUT,
            device_id=request.meta.device_id,
            utterance_id=request.args.get("utterance_id"),
            transcript=None,
            confidence=None,
            expires_at=None,
            meta=request.meta,
            error=error,
        )
    return CommandResult(
        ok=False,
        result_state=ResultState.TIMEOUT,
        meta=request.meta,
        command=_command_payload(request),
        error=error,
    )


def _command_payload(request: CommandRequest) -> dict[str, Any]:
    if request.command_type is CommandType.SAY:
        return {"type": "say", "text_length": len(request.args["text"])}
    if request.command_type is CommandType.FACE:
        return {"type": "face", "name": request.args["name"]}
    if request.command_type is CommandType.MOTION:
        return {"type": "motion", "name": request.args["name"]}
    if request.command_type is CommandType.LED:
        return {"type": "led", "pattern": request.args["pattern"]}
    if request.command_type is CommandType.AUDIO_PLAY:
        return {
            "type": "audio.play",
            "path": request.args["path"],
            "format": BASELINE_AUDIO_FORMAT,
            "sample_rate": BASELINE_AUDIO_SAMPLE_RATE,
            "channels": BASELINE_AUDIO_CHANNELS,
            "chunk_ms": 20,
            "max_chunk_ms": 40,
        }
    if request.command_type is CommandType.AUDIO_CAPTURE:
        return {
            "type": "audio.capture",
            "seconds": request.args["seconds"],
            "output": request.args["output"],
            "format": BASELINE_AUDIO_FORMAT,
            "sample_rate": BASELINE_AUDIO_SAMPLE_RATE,
            "channels": BASELINE_AUDIO_CHANNELS,
            "chunk_ms": 20,
            "max_chunk_ms": 40,
        }
    if request.command_type is CommandType.CAMERA_CAPTURE:
        return {
            "type": "camera.capture",
            "output": request.args["output"],
            "format": "jpeg",
            "width": 320,
            "height": 240,
            "quality": request.args["quality"],
            "max_payload_bytes": 98304,
        }
    if request.command_type is CommandType.NFC_WAIT:
        return {
            "type": "nfc.wait",
            "events": ["nfc_detected", "nfc_removed"],
            "tag_id_logging": "redacted",
        }
    if request.command_type is CommandType.IMU_STREAM:
        return {
            "type": "imu.stream",
            "hz": request.args["hz"],
            "topic": "imu/raw",
            "status_field": False,
        }
    if request.command_type is CommandType.EVENTS_LIST:
        return {"type": "events.list", "limit": request.args["limit"]}
    if request.command_type is CommandType.EVENTS_NEXT:
        return {"type": "events.next", "limit": request.args["limit"]}
    if request.command_type is CommandType.EVENTS_CLEAR:
        return {"type": "events.clear"}
    if request.command_type is CommandType.SPEECH_TRANSCRIPT:
        return {
            "type": "speech.transcript",
            "utterance_id": request.args.get("utterance_id"),
        }
    return {"type": request.command_type.value}


def _events_after(events: list[Event], event_id: str) -> list[Event]:
    for index, event in enumerate(events):
        if event.event_id == event_id:
            return events[index + 1 :]
    return events


def _cursor_for(events: list[Event]) -> str | None:
    if not events:
        return None
    return events[-1].event_id
