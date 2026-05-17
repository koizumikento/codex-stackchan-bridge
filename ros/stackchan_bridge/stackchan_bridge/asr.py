"""Local ASR worker boundary for speech-session tests and bridge integration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Protocol

from stackchan_bridge.audio_session import Utterance


class AsrError(RuntimeError):
    def __init__(self, code: str, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


@dataclass(frozen=True)
class AsrResult:
    text: str
    confidence: float
    language: str = ""
    intent_hint: str = ""


class LocalAsrEngine(Protocol):
    def transcribe(self, utterance: Utterance) -> AsrResult: ...


class DisabledAsrEngine:
    def transcribe(self, utterance: Utterance) -> AsrResult:
        del utterance
        raise AsrError("ASR_UNAVAILABLE", "local ASR backend is not configured", recoverable=True)


class StaticAsrEngine:
    """Deterministic test engine; production backends sit behind the same protocol."""

    def __init__(self, result: AsrResult | None = None) -> None:
        self.result = result or AsrResult(text="test transcript", confidence=1.0)

    def transcribe(self, utterance: Utterance) -> AsrResult:
        del utterance
        return self.result


class LocalAsrWorker:
    """Run an ASR engine behind a timeout and structured failure boundary."""

    def __init__(
        self,
        engine: LocalAsrEngine | None = None,
        *,
        timeout_ms: int = 10000,
        max_workers: int = 1,
    ) -> None:
        self.engine = engine or DisabledAsrEngine()
        self.timeout_ms = timeout_ms
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def transcribe(self, utterance: Utterance) -> AsrResult:
        future = self._executor.submit(self.engine.transcribe, utterance)
        try:
            result = future.result(timeout=self.timeout_ms / 1000.0)
        except FutureTimeout as exc:
            future.cancel()
            raise AsrError("ASR_TIMEOUT", "local ASR worker timed out", recoverable=True) from exc
        except AsrError:
            raise
        except Exception as exc:  # pragma: no cover - backend-specific failures vary.
            raise AsrError("ASR_WORKER_FAILED", str(exc), recoverable=True) from exc
        if not result.text:
            raise AsrError("ASR_EMPTY_RESULT", "local ASR returned no transcript", recoverable=True)
        if result.confidence < 0.0 or result.confidence > 1.0:
            raise AsrError("ASR_INVALID_OUTPUT", "local ASR confidence must be 0.0..1.0", recoverable=True)
        return result

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
