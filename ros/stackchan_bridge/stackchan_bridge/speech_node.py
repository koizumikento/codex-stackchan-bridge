"""Speech processing core and lazy ROS node entrypoint."""

from __future__ import annotations

import json
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
    ) -> None:
        self.echo_controller = echo_controller or NullEchoController()
        self.asr_worker = asr_worker or LocalAsrWorker()
        self.transcript_store = transcript_store or SpeechTranscriptStore()
        self.speech_detector = speech_detector
        self.confidence_threshold = confidence_threshold
        self.vad_config = vad_config
        self.event_sink = event_sink
        self._vad_by_device: dict[str, VadStateMachine] = {}
        self._events: list[SpeechEvent] = []

    @property
    def events(self) -> tuple[SpeechEvent, ...]:
        return tuple(self._events)

    def handle_audio_chunk(self, chunk: AudioChunk) -> tuple[SpeechEvent, ...]:
        before = len(self._events)
        if chunk.direction == AUDIO_DIRECTION_PLAYBACK:
            for frame in _playback_frames(chunk):
                self.echo_controller.process_render(frame)
            return tuple(self._events[before:])
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
            return tuple(self._events[before:])

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
                self._complete_utterance(update.utterance, echo_state=capture.state)
        return tuple(self._events[before:])

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

    return json.dumps(event.payload or {}, ensure_ascii=False, separators=(",", ":"))[:256]


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
        from rclpy.node import Node
        from stackchan_msgs.msg import AudioChunk as RosAudioChunk
        from stackchan_msgs.msg import StackChanEvent
    except ImportError as exc:  # pragma: no cover - exercised only without ROS.
        raise RuntimeError("stackchan_speech_node requires ROS 2 Python packages.") from exc

    def normalize_device_ids(value: object) -> list[str]:
        raw = [value] if isinstance(value, str) else list(value or [])
        device_ids: list[str] = []
        for item in raw:
            device_id = str(item).strip()
            if device_id and device_id not in device_ids:
                device_ids.append(device_id)
        return device_ids or ["default"]

    class StackChanSpeechNode(Node):
        def __init__(self) -> None:
            super().__init__("stackchan_speech")
            self.declare_parameter("device_ids", ["default"])
            self.device_ids = normalize_device_ids(self.get_parameter("device_ids").value)
            self._publishers = {
                device_id: self.create_publisher(
                    StackChanEvent,
                    f"/stackchan/{device_id}/events",
                    32,
                )
                for device_id in self.device_ids
            }
            self.processor = SpeechSessionProcessor(event_sink=self._publish_event)
            self._subscriptions = [
                self.create_subscription(
                    RosAudioChunk,
                    f"/stackchan/{device_id}/device/audio/chunks",
                    self._handle_audio_chunk,
                    8,
                )
                for device_id in self.device_ids
            ]

        def _handle_audio_chunk(self, message: object) -> None:
            chunk = AudioChunk(
                device_id=getattr(message, "device_id", "") or "default",
                command_id=getattr(message, "command_id", ""),
                direction=int(getattr(message, "direction", 0)),
                sequence=int(getattr(message, "sequence", 0)),
                format=int(getattr(message, "format", 0)),
                sample_rate=int(getattr(message, "sample_rate", 0)),
                channels=int(getattr(message, "channels", 0)),
                pcm=bytes(getattr(message, "pcm", b"")),
            )
            self.processor.handle_audio_chunk(chunk)

        def _publish_event(self, event: SpeechEvent) -> None:
            publisher = self._publishers.get(event.device_id)
            if publisher is None:
                return
            message = StackChanEvent()
            message.event_id = ""
            message.device_id = event.device_id
            message.event_name = event.event_name
            message.source = event.source
            now = self.get_clock().now().to_msg()
            message.stamp.sec = now.sec
            message.stamp.nanosec = now.nanosec
            message.command_id = event.command_id
            message.payload_json = speech_event_payload_json(event)
            publisher.publish(message)

    rclpy.init(args=args)
    node = StackChanSpeechNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
