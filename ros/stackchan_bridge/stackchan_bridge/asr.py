"""Local ASR worker boundary for speech-session tests and bridge integration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from threading import Condition
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
        max_pending: int = 4,
    ) -> None:
        if max_pending < 1:
            raise ValueError("max_pending must be positive")
        self.engine = engine or DisabledAsrEngine()
        self.timeout_ms = timeout_ms
        self.max_pending = max_pending
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._pending = 0
        self._condition = Condition()

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
        return self._validate_result(result)

    def _transcribe_direct(self, utterance: Utterance) -> AsrResult:
        try:
            result = self.engine.transcribe(utterance)
        except AsrError:
            raise
        except Exception as exc:  # pragma: no cover - backend-specific failures vary.
            raise AsrError("ASR_WORKER_FAILED", str(exc), recoverable=True) from exc
        return self._validate_result(result)

    def _validate_result(self, result: AsrResult) -> AsrResult:
        if not result.text:
            raise AsrError("ASR_EMPTY_RESULT", "local ASR returned no transcript", recoverable=True)
        if result.confidence < 0.0 or result.confidence > 1.0:
            raise AsrError("ASR_INVALID_OUTPUT", "local ASR confidence must be 0.0..1.0", recoverable=True)
        return result

    def submit(
        self,
        utterance: Utterance,
        callback: "AsrCallback",
    ) -> None:
        """Transcribe an utterance without blocking the audio chunk callback."""

        with self._condition:
            if self._pending >= self.max_pending:
                raise AsrError("ASR_QUEUE_FULL", "local ASR worker queue is full", recoverable=True)
            self._pending += 1

        try:
            future = self._executor.submit(self._transcribe_direct, utterance)
        except Exception:
            with self._condition:
                self._pending -= 1
                self._condition.notify_all()
            raise

        def _finish(_future) -> None:
            try:
                result = _future.result()
                error = None
            except AsrError as exc:
                result = None
                error = exc
            except Exception as exc:  # pragma: no cover - callback failures vary.
                result = None
                error = AsrError("ASR_WORKER_FAILED", str(exc), recoverable=True)
            try:
                callback(utterance, result=result, error=error)
            finally:
                with self._condition:
                    self._pending -= 1
                    self._condition.notify_all()

        future.add_done_callback(_finish)

    def wait_idle(self, timeout_sec: float = 1.0) -> bool:
        """Wait for submitted ASR work to complete. Intended for tests."""

        with self._condition:
            return self._condition.wait_for(lambda: self._pending == 0, timeout=timeout_sec)

    def close(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)


class AsrCallback(Protocol):
    def __call__(
        self,
        utterance: Utterance,
        *,
        result: AsrResult | None,
        error: AsrError | None,
    ) -> None: ...
