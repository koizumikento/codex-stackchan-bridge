"""Bridge-local audio framing, VAD, and bounded queues."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

AUDIO_DIRECTION_PLAYBACK = 1
AUDIO_DIRECTION_CAPTURE = 2
AUDIO_FORMAT_PCM_S16LE = 1
BASELINE_SAMPLE_RATE = 16000
BASELINE_CHANNELS = 1
ROS_CHUNK_MS = 20
INTERNAL_FRAME_MS = 10
INTERNAL_FRAME_BYTES = 320
ROS_CHUNK_BYTES = 640


class AudioSessionError(ValueError):
    """Raised when a device audio chunk violates the bridge speech contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AudioFrame:
    device_id: str
    command_id: str
    sequence: int
    index: int
    pcm: bytes
    sample_rate: int = BASELINE_SAMPLE_RATE
    channels: int = BASELINE_CHANNELS
    frame_ms: int = INTERNAL_FRAME_MS


@dataclass(frozen=True)
class AudioChunk:
    device_id: str
    command_id: str
    direction: int
    sequence: int
    format: int
    sample_rate: int
    channels: int
    pcm: bytes


def split_capture_chunk(chunk: AudioChunk) -> tuple[AudioFrame, ...]:
    """Validate a ROS AudioChunk and split it into 10 ms bridge frames."""

    if chunk.direction != AUDIO_DIRECTION_CAPTURE:
        return ()
    if chunk.format != AUDIO_FORMAT_PCM_S16LE:
        raise AudioSessionError("AUDIO_FORMAT_UNSUPPORTED", "speech node only accepts PCM_S16LE capture chunks")
    if chunk.sample_rate != BASELINE_SAMPLE_RATE or chunk.channels != BASELINE_CHANNELS:
        raise AudioSessionError("AUDIO_FORMAT_UNSUPPORTED", "speech node only accepts 16 kHz mono capture chunks")
    if not chunk.pcm or len(chunk.pcm) % INTERNAL_FRAME_BYTES != 0:
        raise AudioSessionError("MALFORMED_AUDIO_CHUNK", "capture chunk must divide into 10 ms frames")
    if len(chunk.pcm) > ROS_CHUNK_BYTES * 2:
        raise AudioSessionError("MALFORMED_AUDIO_CHUNK", "capture chunk exceeds the 40 ms baseline limit")

    return tuple(
        AudioFrame(
            device_id=chunk.device_id,
            command_id=chunk.command_id,
            sequence=chunk.sequence,
            index=index,
            pcm=chunk.pcm[offset : offset + INTERNAL_FRAME_BYTES],
        )
        for index, offset in enumerate(range(0, len(chunk.pcm), INTERNAL_FRAME_BYTES))
    )


SpeechDetector = Callable[[AudioFrame], bool]


def energy_speech_detector(frame: AudioFrame, *, threshold: int = 8) -> bool:
    """Tiny deterministic VAD primitive used until a real VAD backend is configured."""

    return any(abs(byte - 128) > threshold for byte in frame.pcm)


class VadState(StrEnum):
    IDLE = "idle"
    SPEECH = "speech"


@dataclass(frozen=True)
class VadConfig:
    start_frames: int = 4
    end_silence_ms: int = 700
    pre_roll_ms: int = 300
    post_roll_ms: int = 200
    min_utterance_ms: int = 350
    max_utterance_ms: int = 15000
    frame_ms: int = INTERNAL_FRAME_MS

    def __post_init__(self) -> None:
        if self.start_frames < 1:
            raise ValueError("start_frames must be positive")
        if self.frame_ms <= 0:
            raise ValueError("frame_ms must be positive")


@dataclass(frozen=True)
class Utterance:
    device_id: str
    utterance_id: str
    command_id: str
    pcm: bytes
    frame_count: int
    duration_ms: int


@dataclass(frozen=True)
class VadUpdate:
    speech_detected: bool = False
    utterance: Utterance | None = None


class VadStateMachine:
    """Assemble utterances from 10 ms frames without running continuous ASR."""

    def __init__(self, *, config: VadConfig | None = None) -> None:
        self.config = config or VadConfig()
        self.state = VadState.IDLE
        self._pre_roll: deque[AudioFrame] = deque(maxlen=self._frames(self.config.pre_roll_ms))
        self._speech_frames: list[AudioFrame] = []
        self._candidate_frames: list[AudioFrame] = []
        self._silence_frames = 0
        self._utterance_counter = 0

    def feed(self, frame: AudioFrame, *, is_speech: bool) -> VadUpdate:
        if self.state is VadState.IDLE:
            self._pre_roll.append(frame)
            if not is_speech:
                self._candidate_frames.clear()
                return VadUpdate()
            self._candidate_frames.append(frame)
            if len(self._candidate_frames) < self.config.start_frames:
                return VadUpdate()
            self.state = VadState.SPEECH
            self._speech_frames = list(self._pre_roll)
            self._silence_frames = 0
            return VadUpdate(speech_detected=True)

        self._speech_frames.append(frame)
        if is_speech:
            self._silence_frames = 0
        else:
            self._silence_frames += 1

        max_frames = self._frames(self.config.max_utterance_ms)
        if len(self._speech_frames) >= max_frames:
            return VadUpdate(utterance=self._finish(frame))

        end_frames = self._frames(self.config.end_silence_ms)
        if self._silence_frames >= end_frames:
            utterance_frames = self._speech_frames[: -self._trim_silence_frames()]
            utterance = self._finish(frame, frames=utterance_frames)
            if utterance.duration_ms < self.config.min_utterance_ms:
                return VadUpdate()
            return VadUpdate(utterance=utterance)

        return VadUpdate()

    def _finish(self, frame: AudioFrame, *, frames: list[AudioFrame] | None = None) -> Utterance:
        selected = list(frames if frames is not None else self._speech_frames)
        self._utterance_counter += 1
        utterance = Utterance(
            device_id=frame.device_id,
            utterance_id=f"utt-{self._utterance_counter:08d}",
            command_id=frame.command_id,
            pcm=b"".join(item.pcm for item in selected),
            frame_count=len(selected),
            duration_ms=len(selected) * self.config.frame_ms,
        )
        self.state = VadState.IDLE
        self._speech_frames = []
        self._candidate_frames = []
        self._silence_frames = 0
        self._pre_roll.clear()
        return utterance

    def _trim_silence_frames(self) -> int:
        return max(0, self._silence_frames - self._frames(self.config.post_roll_ms))

    def _frames(self, milliseconds: int) -> int:
        return max(1, milliseconds // self.config.frame_ms)


T = TypeVar("T")


class BoundedDropQueue(Generic[T]):
    """Small queue that drops the oldest item instead of growing unbounded."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._items: deque[T] = deque()

    def push(self, item: T) -> T | None:
        dropped = None
        if len(self._items) >= self.capacity:
            dropped = self._items.popleft()
        self._items.append(item)
        return dropped

    def pop(self) -> T | None:
        if not self._items:
            return None
        return self._items.popleft()

    def __len__(self) -> int:
        return len(self._items)
