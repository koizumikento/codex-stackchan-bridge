"""Speech processing core and lazy ROS node entrypoint."""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

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


@dataclass(frozen=True)
class _AsrJob:
    utterance: object
    echo_state: EchoState


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
        asr_queue_capacity: int = 4,
    ) -> None:
        self.echo_controller = echo_controller or NullEchoController()
        self.asr_worker = asr_worker or LocalAsrWorker()
        self.transcript_store = transcript_store or SpeechTranscriptStore()
        self.speech_detector = speech_detector
        self.confidence_threshold = confidence_threshold
        self.vad_config = vad_config
        self.event_sink = event_sink
        self._vad_by_session: dict[tuple[str, str], VadStateMachine] = {}
        self._echo_state_by_session: dict[tuple[str, str], EchoState] = {}
        self._events: list[SpeechEvent] = []
        self._lock = threading.RLock()
        self._closed = False
        self._asr_jobs: queue.Queue[_AsrJob | None] = queue.Queue(maxsize=max(1, asr_queue_capacity))
        self._asr_thread = threading.Thread(target=self._run_asr_jobs, name="stackchan-asr-worker", daemon=True)
        self._asr_thread.start()

    @property
    def events(self) -> tuple[SpeechEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def handle_audio_chunk(self, chunk: AudioChunk) -> tuple[SpeechEvent, ...]:
        with self._lock:
            before = len(self._events)
        if chunk.direction == AUDIO_DIRECTION_PLAYBACK:
            for frame in _playback_frames(chunk):
                self.echo_controller.process_render(frame)
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
                            "requires_codex": False,
                            "safety_action": "none",
                            "echo_state": capture.state.value,
                            "suppressed_reason": capture.suppressed_reason,
                        },
                    )
                )
                continue
            session_key = (frame.device_id, frame.command_id)
            with self._lock:
                self._echo_state_by_session[session_key] = capture.state
                vad = self._vad_by_session.setdefault(session_key, VadStateMachine(config=self.vad_config))
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
                self._queue_utterance(update.utterance, echo_state=capture.state)
                with self._lock:
                    self._vad_by_session.pop(session_key, None)
                    self._echo_state_by_session.pop(session_key, None)
        return self._events_since(before)

    def flush_session(self, device_id: str, command_id: str) -> tuple[SpeechEvent, ...]:
        """Close a bounded capture/listen session without waiting for ASR."""

        with self._lock:
            before = len(self._events)
            vad = self._vad_by_session.pop((device_id, command_id), None)
            echo_state = self._echo_state_by_session.pop((device_id, command_id), EchoState.AEC_ACTIVE)
        if vad is None:
            return self._events_since(before)
        utterance = vad.flush()
        if utterance is not None:
            self._queue_utterance(utterance, echo_state=echo_state)
        return self._events_since(before)

    def flush_device(self, device_id: str) -> tuple[SpeechEvent, ...]:
        """Close all open speech sessions for a device."""

        with self._lock:
            before = len(self._events)
            keys = [key for key in self._vad_by_session if key[0] == device_id]
        for _, command_id in keys:
            self.flush_session(device_id, command_id)
        return self._events_since(before)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            try:
                self._asr_jobs.put(None, timeout=0.1)
                break
            except queue.Full:
                continue
        self._asr_thread.join(timeout=1.0)
        self.asr_worker.close()

    def _events_since(self, before: int) -> tuple[SpeechEvent, ...]:
        with self._lock:
            return tuple(self._events[before:])

    def _queue_utterance(self, utterance, *, echo_state: EchoState) -> None:
        with self._lock:
            closed = self._closed
        if closed:
            return
        try:
            self._asr_jobs.put_nowait(_AsrJob(utterance=utterance, echo_state=echo_state))
        except queue.Full:
            self._emit(
                SpeechEvent(
                    device_id=utterance.device_id,
                    event_name="transcript_failed",
                    command_id=utterance.command_id,
                    payload={"utterance_id": utterance.utterance_id, "error_code": "ASR_WORKER_FAILED"},
                )
            )

    def _run_asr_jobs(self) -> None:
        while True:
            job = self._asr_jobs.get()
            if job is None:
                return
            self._complete_utterance(job.utterance, echo_state=job.echo_state)

    def _complete_utterance(self, utterance, *, echo_state: EchoState) -> None:
        try:
            asr = self.asr_worker.transcribe(utterance)
        except AsrError as exc:
            self._emit(
                SpeechEvent(
                    device_id=utterance.device_id,
                    event_name="transcript_failed",
                    command_id=utterance.command_id,
                    payload={"utterance_id": utterance.utterance_id, "error_code": exc.code},
                )
            )
            return

        safety_action = detect_immediate_safety_action(asr.text)
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
            intent_hint=asr.intent_hint,
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
            safety_action=safety_action,
            suppressed_reason="none",
        )

    def _emit_semantic(
        self,
        utterance,
        asr: AsrResult,
        *,
        echo_state: EchoState,
        safety_action: str = "none",
        suppressed_reason: str = "none",
    ) -> None:
        requires_codex = safety_action == "none" and not asr.intent_hint
        self._emit(
            SpeechEvent(
                device_id=utterance.device_id,
                event_name="voice_semantic_event",
                command_id=utterance.command_id,
                payload={
                    "utterance_id": utterance.utterance_id,
                    "confidence": round(asr.confidence, 3),
                    "intent_hint": asr.intent_hint,
                    "requires_codex": requires_codex,
                    "safety_action": safety_action,
                    "echo_state": echo_state.value,
                    "suppressed_reason": suppressed_reason,
                },
            )
        )

    def _emit(self, event: SpeechEvent) -> None:
        with self._lock:
            if self._closed:
                return
            self._events.append(event)
        if self.event_sink is not None:
            self.event_sink(event)


def detect_immediate_safety_action(text: str) -> str:
    normalized = text.strip().lower()
    if not normalized:
        return "none"
    negative_contexts = (
        "止まらないで",
        "停止しないで",
        "ストップしないで",
        "止まってという",
        "「止まって」",
        "\"止まって\"",
        "ストップという",
        "コマンドを追加",
        "認識して",
        "どうなる",
    )
    if any(fragment in normalized for fragment in negative_contexts):
        return "none"
    if normalized in {"止まって", "ストップ", "停止", "やめて"}:
        return "stop"
    if normalized.endswith(("止まって", "ストップ", "停止して", "やめて")):
        return "stop"
    return "none"


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
