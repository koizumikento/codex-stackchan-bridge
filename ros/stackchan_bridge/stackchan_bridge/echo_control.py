"""Echo control abstractions for bridge-local speech processing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from stackchan_bridge.audio_session import AudioFrame, BoundedDropQueue


class EchoState(StrEnum):
    AEC_ACTIVE = "aec_active"
    GATED = "gated"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class EchoCaptureResult:
    frame: AudioFrame | None
    state: EchoState
    suppressed_reason: str = "none"


class EchoController(Protocol):
    def process_render(self, frame: AudioFrame) -> None: ...

    def process_capture(self, frame: AudioFrame, *, delay_ms: int | None = None) -> EchoCaptureResult: ...


class NullEchoController:
    """Pass-through controller used when a reference-aware AEC worker is healthy."""

    def process_render(self, frame: AudioFrame) -> None:
        del frame

    def process_capture(self, frame: AudioFrame, *, delay_ms: int | None = None) -> EchoCaptureResult:
        del delay_ms
        return EchoCaptureResult(frame=frame, state=EchoState.AEC_ACTIVE)


class EchoGateFallback:
    """Fallback policy: suppress normal ASR while playback may still be audible."""

    def __init__(self, *, hangover_frames: int = 40) -> None:
        self.hangover_frames = max(0, hangover_frames)
        self._remaining_hangover = 0

    def process_render(self, frame: AudioFrame) -> None:
        del frame
        self._remaining_hangover = self.hangover_frames

    def process_capture(self, frame: AudioFrame, *, delay_ms: int | None = None) -> EchoCaptureResult:
        del delay_ms
        if self._remaining_hangover > 0:
            self._remaining_hangover -= 1
            return EchoCaptureResult(frame=None, state=EchoState.GATED, suppressed_reason="playback_hangover")
        return EchoCaptureResult(frame=frame, state=EchoState.UNAVAILABLE, suppressed_reason="aec_unavailable")


class WorkerEchoController:
    """Isolate AEC worker errors and fall back to an echo gate."""

    def __init__(
        self,
        worker: EchoController,
        *,
        render_queue_capacity: int = 128,
        fallback: EchoGateFallback | None = None,
    ) -> None:
        self.worker = worker
        self.render_queue: BoundedDropQueue[AudioFrame] = BoundedDropQueue(render_queue_capacity)
        self.fallback = fallback or EchoGateFallback()
        self.available = True
        self.last_error: str | None = None

    def process_render(self, frame: AudioFrame) -> None:
        dropped = self.render_queue.push(frame)
        if dropped is not None:
            self.available = False
            self.last_error = "render_reference_queue_full"
            self.fallback.process_render(frame)
            return
        if not self.available:
            self.fallback.process_render(frame)
            return
        try:
            self.worker.process_render(frame)
        except Exception as exc:  # pragma: no cover - exact worker failures vary.
            self.available = False
            self.last_error = f"worker_crash:{exc}"
            self.fallback.process_render(frame)

    def process_capture(self, frame: AudioFrame, *, delay_ms: int | None = None) -> EchoCaptureResult:
        if not self.available:
            return self.fallback.process_capture(frame, delay_ms=delay_ms)
        try:
            return self.worker.process_capture(frame, delay_ms=delay_ms)
        except TimeoutError:
            self.available = False
            self.last_error = "worker_timeout"
            return self.fallback.process_capture(frame, delay_ms=delay_ms)
        except Exception as exc:  # pragma: no cover - exact worker failures vary.
            self.available = False
            self.last_error = f"worker_crash:{exc}"
            return self.fallback.process_capture(frame, delay_ms=delay_ms)
