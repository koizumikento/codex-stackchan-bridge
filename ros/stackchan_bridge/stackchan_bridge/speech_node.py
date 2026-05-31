"""Speech processing core and lazy ROS node entrypoint."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from time import monotonic

from stackchan_bridge.asr import AsrError, AsrResult, LocalAsrWorker
from stackchan_bridge.audio_session import (
    AUDIO_DIRECTION_PLAYBACK,
    AUDIO_FORMAT_PCM_S16LE,
    AudioChunk,
    AudioFrame,
    AudioSessionError,
    SpeechDetector,
    VadConfig,
    VadStateMachine,
    energy_speech_detector,
    split_capture_chunk,
)
from stackchan_bridge.echo_control import EchoController, EchoState, NullEchoController
from stackchan_bridge.speech_session import SpeechTranscriptStore


@dataclass(frozen=True)
class SpeechEvent:
    device_id: str
    event_name: str
    source: str = "speech_session"
    command_id: str = ""
    payload: dict[str, object] | None = None


EventSink = Callable[[SpeechEvent], None]
Clock = Callable[[], float]
INVALID_CAPTURE_SESSION_TTL_SEC = 300.0


class SpeechSessionProcessor:
    """Process audio chunks into redacted speech events and transcript lookups."""

    def __init__(
        self,
        *,
        echo_controller: EchoController | None = None,
        asr_worker: LocalAsrWorker | None = None,
        transcript_store: SpeechTranscriptStore | None = None,
        speech_detector: SpeechDetector = energy_speech_detector,
        confidence_threshold: float = 0.75,
        vad_config: VadConfig | None = None,
        event_sink: EventSink | None = None,
        clock: Clock = monotonic,
    ) -> None:
        self.echo_controller = echo_controller or NullEchoController()
        self.asr_worker = asr_worker or LocalAsrWorker()
        self.transcript_store = transcript_store or SpeechTranscriptStore()
        self.speech_detector = speech_detector
        self.confidence_threshold = confidence_threshold
        self.vad_config = vad_config
        self.event_sink = event_sink
        self._clock = clock
        self._vad_by_device: dict[str, VadStateMachine] = {}
        self._invalid_capture_sessions: dict[tuple[str, str], float] = {}
        self._pending_asr_sessions: dict[tuple[str, str], int] = {}
        self._events: list[SpeechEvent] = []
        self._events_lock = RLock()

    @property
    def events(self) -> tuple[SpeechEvent, ...]:
        with self._events_lock:
            return tuple(self._events)

    def handle_audio_chunk(self, chunk: AudioChunk) -> tuple[SpeechEvent, ...]:
        before = self._event_count()
        if chunk.direction == AUDIO_DIRECTION_PLAYBACK:
            for frame in _playback_frames(chunk):
                self.echo_controller.process_render(frame)
            return self._events_since(before)
        if self._capture_session_invalidated(chunk.device_id, chunk.command_id):
            return self._events_since(before)
        try:
            frames = split_capture_chunk(chunk)
        except AudioSessionError as exc:
            self._emit(
                SpeechEvent(
                    device_id=chunk.device_id,
                    event_name="transcript_failed",
                    command_id=chunk.command_id,
                    payload={"error_code": exc.code},
                )
            )
            return self._events_since(before)

        for frame in frames:
            if self._capture_session_invalidated(frame.device_id, frame.command_id):
                return self._events_since(before)
            capture = self.echo_controller.process_capture(frame)
            if capture.frame is None:
                self._emit(
                    SpeechEvent(
                        device_id=frame.device_id,
                        event_name="voice_semantic_event",
                        command_id=frame.command_id,
                        payload={
                            "utterance_id": "",
                            "confidence": 0.0,
                            "echo_state": capture.state.value,
                            "suppressed_reason": capture.suppressed_reason,
                        },
                    )
                )
                continue
            vad = self._vad_by_device.setdefault(frame.device_id, VadStateMachine(config=self.vad_config))
            update = vad.feed(capture.frame, is_speech=self.speech_detector(capture.frame))
            if update.speech_detected:
                self._emit(
                    SpeechEvent(
                        device_id=frame.device_id,
                        event_name="speech_detected",
                        command_id=frame.command_id,
                        payload={"echo_state": capture.state.value},
                    )
                )
            if update.utterance is not None:
                if self._capture_session_invalidated(
                    update.utterance.device_id,
                    update.utterance.command_id,
                ):
                    return self._events_since(before)
                self._complete_utterance(update.utterance, echo_state=capture.state)
        return self._events_since(before)

    def invalidate_capture_session(
        self,
        *,
        device_id: str,
        command_id: str,
        sequence: int,
        reason: str,
    ) -> tuple[SpeechEvent, ...]:
        before = self._event_count()
        with self._events_lock:
            now = self._clock()
            self._purge_invalid_capture_sessions_locked(now)
            self._invalid_capture_sessions[(device_id, command_id)] = now
            self._vad_by_device.pop(device_id, None)
        self._emit(
            SpeechEvent(
                device_id=device_id,
                event_name="transcript_failed",
                command_id=command_id,
                payload={
                    "error_code": "AUDIO_CHUNK_DROPPED",
                    "sequence": sequence,
                    "reason": reason,
                },
            )
        )
        return self._events_since(before)

    def _complete_utterance(self, utterance, *, echo_state: EchoState) -> None:
        self._increment_pending_asr(utterance.device_id, utterance.command_id)
        try:
            self.asr_worker.submit(
                utterance,
                lambda completed, result, error: self._finish_asr_result(
                    completed,
                    result=result,
                    error=error,
                    echo_state=echo_state,
                ),
            )
        except AsrError as exc:
            self._decrement_pending_asr(utterance.device_id, utterance.command_id)
            self._emit(
                SpeechEvent(
                    device_id=utterance.device_id,
                    event_name="transcript_failed",
                    command_id=utterance.command_id,
                    payload={"utterance_id": utterance.utterance_id, "error_code": exc.code},
                )
            )
            return
        except Exception:
            self._decrement_pending_asr(utterance.device_id, utterance.command_id)
            raise

    def _finish_asr_result(
        self,
        utterance,
        *,
        result: AsrResult | None,
        error: AsrError | None,
        echo_state: EchoState,
    ) -> None:
        try:
            self._handle_asr_result(
                utterance,
                result=result,
                error=error,
                echo_state=echo_state,
            )
        finally:
            self._decrement_pending_asr(utterance.device_id, utterance.command_id)

    def _handle_asr_result(
        self,
        utterance,
        *,
        result: AsrResult | None,
        error: AsrError | None,
        echo_state: EchoState,
    ) -> None:
        if self._capture_session_invalidated(utterance.device_id, utterance.command_id):
            return
        if error is not None or result is None:
            exc = error or AsrError("ASR_WORKER_FAILED", "local ASR worker failed")
            self._emit(
                SpeechEvent(
                    device_id=utterance.device_id,
                    event_name="transcript_failed",
                    command_id=utterance.command_id,
                    payload={"utterance_id": utterance.utterance_id, "error_code": exc.code},
                )
            )
            return

        asr = result
        if asr.confidence < self.confidence_threshold:
            self._emit_semantic(utterance, asr, echo_state=echo_state, suppressed_reason="low_confidence")
            return

        self.transcript_store.put(
            utterance.device_id,
            utterance.utterance_id,
            asr.text,
            command_id=utterance.command_id,
            source="speech_session",
            confidence=asr.confidence,
            language=asr.language,
        )
        self._emit(
            SpeechEvent(
                device_id=utterance.device_id,
                event_name="transcript_ready",
                command_id=utterance.command_id,
                payload={"utterance_id": utterance.utterance_id},
            )
        )
        self._emit_semantic(
            utterance,
            asr,
            echo_state=echo_state,
            suppressed_reason="none",
        )

    def _emit_semantic(
        self,
        utterance,
        asr: AsrResult,
        *,
        echo_state: EchoState,
        suppressed_reason: str = "none",
    ) -> None:
        self._emit(
            SpeechEvent(
                device_id=utterance.device_id,
                event_name="voice_semantic_event",
                command_id=utterance.command_id,
                payload={
                    "utterance_id": utterance.utterance_id,
                    "confidence": round(asr.confidence, 3),
                    "echo_state": echo_state.value,
                    "suppressed_reason": suppressed_reason,
                },
            )
        )

    def _emit(self, event: SpeechEvent) -> None:
        with self._events_lock:
            self._events.append(event)
        if self.event_sink is not None:
            self.event_sink(event)

    def _capture_session_invalidated(self, device_id: str, command_id: str) -> bool:
        with self._events_lock:
            self._purge_invalid_capture_sessions_locked(self._clock())
            return (device_id, command_id) in self._invalid_capture_sessions

    def _increment_pending_asr(self, device_id: str, command_id: str) -> None:
        key = (device_id, command_id)
        with self._events_lock:
            self._pending_asr_sessions[key] = self._pending_asr_sessions.get(key, 0) + 1

    def _decrement_pending_asr(self, device_id: str, command_id: str) -> None:
        key = (device_id, command_id)
        with self._events_lock:
            pending = self._pending_asr_sessions.get(key, 0) - 1
            if pending > 0:
                self._pending_asr_sessions[key] = pending
            else:
                self._pending_asr_sessions.pop(key, None)
            self._purge_invalid_capture_sessions_locked(self._clock())

    def _purge_invalid_capture_sessions_locked(self, now: float) -> None:
        expired = [
            key
            for key, invalidated_at in self._invalid_capture_sessions.items()
            if now - invalidated_at >= INVALID_CAPTURE_SESSION_TTL_SEC
            and self._pending_asr_sessions.get(key, 0) <= 0
        ]
        for key in expired:
            self._invalid_capture_sessions.pop(key, None)

    def wait_asr_idle(self, timeout_sec: float = 1.0) -> bool:
        return self.asr_worker.wait_idle(timeout_sec=timeout_sec)

    def close(self) -> None:
        self.asr_worker.close(wait=False)

    def _event_count(self) -> int:
        with self._events_lock:
            return len(self._events)

    def _events_since(self, index: int) -> tuple[SpeechEvent, ...]:
        with self._events_lock:
            return tuple(self._events[index:])


def _playback_frames(chunk: AudioChunk) -> tuple[AudioFrame, ...]:
    if chunk.direction != AUDIO_DIRECTION_PLAYBACK or chunk.format != AUDIO_FORMAT_PCM_S16LE:
        return ()
    return tuple(
        AudioFrame(
            device_id=chunk.device_id,
            command_id=chunk.command_id,
            sequence=chunk.sequence,
            index=index,
            pcm=chunk.pcm[offset : offset + 320],
        )
        for index, offset in enumerate(range(0, len(chunk.pcm), 320))
        if len(chunk.pcm[offset : offset + 320]) == 320
    )


def speech_event_payload_json(event: SpeechEvent) -> str:
    """Serialize bounded event metadata without ever adding transcript text."""

    payload_json = json.dumps(event.payload or {}, ensure_ascii=False, separators=(",", ":"))
    if len(payload_json.encode("utf-8")) <= 256:
        return payload_json
    return '{"truncated":true,"reason":"payload_json_exceeds_256_bytes"}'


def main(args: list[str] | None = None) -> None:
    del args
    raise RuntimeError(
        "speech processing is owned by stackchan_bridge_node so transcripts and "
        "events share the bridge facade stores"
    )
