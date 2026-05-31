"""Local ASR worker boundary for speech-session tests and bridge integration."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
import io
import json
import uuid
from typing import Protocol
import urllib.error
import urllib.request
import wave

from stackchan_bridge.audio_session import BASELINE_CHANNELS, BASELINE_SAMPLE_RATE, Utterance

DEFAULT_ASR_TIMEOUT_SEC = 20.0
HttpPost = Callable[[str, bytes, dict[str, str], float], bytes]


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


class WhisperHttpAsrEngine:
    """OpenAI-compatible local Whisper transcription adapter."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str = "",
        language: str = "",
        timeout_sec: float = DEFAULT_ASR_TIMEOUT_SEC,
        http_post: HttpPost | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model.strip()
        self.language = language.strip()
        self.timeout_sec = max(0.1, float(timeout_sec))
        self._http_post = http_post or _http_post

    def transcribe(self, utterance: Utterance) -> AsrResult:
        if not self.endpoint:
            raise AsrError(
                "ASR_UNAVAILABLE",
                "local ASR provider endpoint is not configured",
                recoverable=False,
            )
        fields = {"response_format": "verbose_json"}
        if self.model:
            fields["model"] = self.model
        if self.language:
            fields["language"] = self.language
        body, content_type = _multipart_form_data(
            fields=fields,
            file_field="file",
            filename=f"{utterance.utterance_id}.wav",
            content_type="audio/wav",
            file_bytes=_utterance_wav_bytes(utterance),
        )
        try:
            response = self._http_post(
                f"{self.endpoint}/v1/audio/transcriptions",
                body,
                {"Content-Type": content_type},
                self.timeout_sec,
            )
        except urllib.error.HTTPError as exc:
            raise AsrError(
                "ASR_WORKER_FAILED",
                f"local ASR provider rejected transcription with HTTP {exc.code}",
                recoverable=True,
            ) from exc
        except TimeoutError as exc:
            raise AsrError("ASR_TIMEOUT", "local ASR provider timed out", recoverable=True) from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                raise AsrError(
                    "ASR_TIMEOUT",
                    "local ASR provider timed out",
                    recoverable=True,
                ) from exc
            raise AsrError(
                "ASR_UNAVAILABLE",
                "local ASR provider is unavailable",
                recoverable=True,
            ) from exc
        return _parse_transcription_response(response)


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


def _utterance_wav_bytes(utterance: Utterance) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(BASELINE_CHANNELS)
        wav.setsampwidth(2)
        wav.setframerate(BASELINE_SAMPLE_RATE)
        wav.writeframes(utterance.pcm)
    return output.getvalue()


def _multipart_form_data(
    *,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> tuple[bytes, str]:
    boundary = f"stackchan-{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode("ascii"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("ascii")
    )
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("ascii"))
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def _parse_transcription_response(payload: bytes) -> AsrResult:
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AsrError(
            "ASR_INVALID_OUTPUT",
            "local ASR provider returned invalid JSON",
            recoverable=True,
        ) from exc
    if isinstance(parsed, str):
        return AsrResult(text=parsed, confidence=1.0)
    if not isinstance(parsed, dict):
        raise AsrError(
            "ASR_INVALID_OUTPUT",
            "local ASR provider returned invalid response shape",
            recoverable=True,
        )
    text = parsed.get("text")
    if not isinstance(text, str):
        raise AsrError(
            "ASR_INVALID_OUTPUT",
            "local ASR provider response did not include transcript text",
            recoverable=True,
        )
    language = parsed.get("language")
    return AsrResult(
        text=text,
        confidence=_confidence_from_response(parsed),
        language=language if isinstance(language, str) else "",
    )


def _confidence_from_response(response: dict[str, object]) -> float:
    segments = response.get("segments")
    if not isinstance(segments, list) or not segments:
        return 1.0
    no_speech_values = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        value = segment.get("no_speech_prob")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            no_speech_values.append(float(value))
    if not no_speech_values:
        return 1.0
    return min(1.0, max(0.0, 1.0 - max(no_speech_values)))


def _http_post(url: str, data: bytes, headers: dict[str, str], timeout_sec: float) -> bytes:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        return response.read()
