"""Local TTS provider adapters for bridge-owned speech synthesis."""

from __future__ import annotations

import array
from dataclasses import dataclass
import io
import json
import math
import sys
from typing import Callable
import urllib.error
import urllib.parse
import urllib.request
import wave

AUDIO_FORMAT = "pcm_s16le"
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_CHUNK_BYTES = 640
AUDIO_CHUNK_FORMAT_ID = 1
DEFAULT_TTS_TIMEOUT_SEC = 15.0


class TtsProviderError(RuntimeError):
    """Structured TTS error that can be mapped to stackchan_msgs/Result."""

    def __init__(self, code: str, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


@dataclass(frozen=True)
class VoiceProfile:
    """Bridge-owned voice profile mapped to provider-local settings."""

    name: str
    provider: str
    speaker_id: int
    endpoint: str
    required_credit: str = ""
    terms_url: str = ""


@dataclass(frozen=True)
class TtsAudio:
    """Normalized local audio ready for firmware playback."""

    pcm: bytes
    format: str = AUDIO_FORMAT
    sample_rate: int = AUDIO_SAMPLE_RATE
    channels: int = AUDIO_CHANNELS


HttpPost = Callable[[str, bytes, dict[str, str], float], bytes]


class VoiceVoxTtsProvider:
    """VOICEVOX Engine adapter that returns 16 kHz mono PCM."""

    def __init__(
        self,
        *,
        profiles: dict[str, VoiceProfile],
        default_profile: str = "default",
        endpoint: str = "",
        timeout_sec: float = DEFAULT_TTS_TIMEOUT_SEC,
        speed_scale: float | None = None,
        pre_phoneme_length: float | None = None,
        post_phoneme_length: float | None = None,
        silence_trim_threshold: int = 0,
        silence_trim_margin_samples: int = 0,
        http_post: HttpPost | None = None,
    ) -> None:
        self._profiles = dict(profiles)
        self._default_profile = default_profile
        self._endpoint = endpoint.rstrip("/")
        self._timeout_sec = timeout_sec
        self._speed_scale = speed_scale
        self._pre_phoneme_length = pre_phoneme_length
        self._post_phoneme_length = post_phoneme_length
        self._silence_trim_threshold = max(0, int(silence_trim_threshold))
        self._silence_trim_margin_samples = max(0, int(silence_trim_margin_samples))
        self._http_post = http_post or _http_post

    @property
    def provider_kind(self) -> str:
        return "voicevox"

    def synthesize(self, text: str, voice_profile: str = "") -> tuple[VoiceProfile, TtsAudio]:
        profile_name = (voice_profile or self._default_profile).strip() or self._default_profile
        profile = self._profiles.get(profile_name)
        if profile is None:
            raise TtsProviderError(
                "UNKNOWN_VOICE_PROFILE",
                f"unknown voice profile {profile_name!r}",
                recoverable=False,
            )
        endpoint = (profile.endpoint or self._endpoint).rstrip("/")
        if not endpoint:
            raise TtsProviderError(
                "UNSUPPORTED_FEATURE",
                "local TTS provider endpoint is not configured",
                recoverable=False,
            )
        query = self._audio_query(endpoint, profile.speaker_id, text)
        query = tune_voicevox_query_payload(
            query,
            speed_scale=self._speed_scale,
            pre_phoneme_length=self._pre_phoneme_length,
            post_phoneme_length=self._post_phoneme_length,
        )
        validate_voicevox_query_payload(query)
        wav_bytes = self._synthesis(endpoint, profile.speaker_id, query)
        audio = decode_wav_to_pcm_s16le_mono_16k(wav_bytes)
        return profile, TtsAudio(
            pcm=trim_pcm_s16le_silence(
                audio.pcm,
                threshold=self._silence_trim_threshold,
                margin_samples=self._silence_trim_margin_samples,
            )
        )

    def _audio_query(self, endpoint: str, speaker_id: int, text: str) -> bytes:
        query = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
        url = f"{endpoint}/audio_query?{query}"
        try:
            return self._http_post(url, b"", {}, self._timeout_sec)
        except urllib.error.HTTPError as exc:
            raise TtsProviderError(
                "TTS_SYNTHESIS_FAILED",
                f"local TTS provider rejected audio_query with HTTP {exc.code}",
                recoverable=True,
            ) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise TtsProviderError(
                "TTS_PROVIDER_UNAVAILABLE",
                "local TTS provider is unavailable",
                recoverable=True,
            ) from exc

    def _synthesis(self, endpoint: str, speaker_id: int, query_json: bytes) -> bytes:
        query = urllib.parse.urlencode({"speaker": speaker_id})
        url = f"{endpoint}/synthesis?{query}"
        try:
            return self._http_post(
                url,
                query_json,
                {"Content-Type": "application/json"},
                self._timeout_sec,
            )
        except urllib.error.HTTPError as exc:
            raise TtsProviderError(
                "TTS_SYNTHESIS_FAILED",
                f"local TTS provider rejected synthesis with HTTP {exc.code}",
                recoverable=True,
            ) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise TtsProviderError(
                "TTS_PROVIDER_UNAVAILABLE",
                "local TTS provider is unavailable",
                recoverable=True,
            ) from exc


def default_voice_profiles(endpoint: str = "") -> dict[str, VoiceProfile]:
    return {
        "default": VoiceProfile(
            name="default",
            provider="voicevox",
            speaker_id=3,
            endpoint=endpoint,
            required_credit="VOICEVOX",
            terms_url="https://voicevox.hiroshiba.jp/term/",
        )
    }


def decode_wav_to_pcm_s16le_mono_16k(wav_bytes: bytes) -> TtsAudio:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            if wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
                raise TtsProviderError(
                    "TTS_AUDIO_UNSUPPORTED",
                    "local TTS provider returned unsupported audio encoding",
                    recoverable=True,
                )
            channels = wav.getnchannels()
            source_rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except wave.Error as exc:
        raise TtsProviderError(
            "TTS_SYNTHESIS_FAILED",
            "local TTS provider returned invalid WAV audio",
            recoverable=True,
        ) from exc
    if channels < 1 or source_rate <= 0:
        raise TtsProviderError(
            "TTS_AUDIO_UNSUPPORTED",
            "local TTS provider returned invalid audio metadata",
            recoverable=True,
        )
    samples = array.array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    mono = _mix_to_mono(samples, channels)
    normalized = _resample(mono, source_rate, AUDIO_SAMPLE_RATE)
    if not normalized:
        raise TtsProviderError(
            "TTS_SYNTHESIS_FAILED",
            "local TTS provider returned empty audio",
            recoverable=True,
        )
    if sys.byteorder != "little":
        normalized.byteswap()
    return TtsAudio(pcm=normalized.tobytes())


def tune_voicevox_query_payload(
    payload: bytes,
    *,
    speed_scale: float | None = None,
    pre_phoneme_length: float | None = None,
    post_phoneme_length: float | None = None,
) -> bytes:
    """Apply bridge-owned VOICEVOX transport tuning to an audio_query payload."""

    if speed_scale is None and pre_phoneme_length is None and post_phoneme_length is None:
        return payload
    try:
        query = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TtsProviderError(
            "TTS_SYNTHESIS_FAILED",
            "local TTS provider returned invalid audio query JSON",
            recoverable=True,
        ) from exc
    if not isinstance(query, dict):
        raise TtsProviderError(
            "TTS_SYNTHESIS_FAILED",
            "local TTS provider returned invalid audio query JSON",
            recoverable=True,
        )
    if speed_scale is not None:
        query["speedScale"] = max(0.1, float(speed_scale))
    if pre_phoneme_length is not None:
        query["prePhonemeLength"] = max(0.0, float(pre_phoneme_length))
    if post_phoneme_length is not None:
        query["postPhonemeLength"] = max(0.0, float(post_phoneme_length))
    return json.dumps(query, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def trim_pcm_s16le_silence(
    pcm: bytes,
    *,
    threshold: int,
    margin_samples: int = 0,
) -> bytes:
    """Trim leading and trailing near-silence from little-endian signed 16-bit PCM."""

    if threshold <= 0 or len(pcm) < 2:
        return pcm
    sample_bytes = pcm[: len(pcm) - (len(pcm) % 2)]
    samples = array.array("h")
    samples.frombytes(sample_bytes)
    if sys.byteorder != "little":
        samples.byteswap()
    first = None
    last = None
    for index, sample in enumerate(samples):
        if abs(int(sample)) > threshold:
            first = index
            break
    if first is None:
        return pcm
    for index in range(len(samples) - 1, first - 1, -1):
        if abs(int(samples[index])) > threshold:
            last = index
            break
    start = max(0, first - max(0, margin_samples))
    stop = min(len(samples), (last or first) + max(0, margin_samples) + 1)
    trimmed = samples[start:stop]
    if sys.byteorder != "little":
        trimmed.byteswap()
    return trimmed.tobytes()


def _mix_to_mono(samples: array.array, channels: int) -> array.array:
    if channels == 1:
        return samples
    frame_count = len(samples) // channels
    mixed = array.array("h")
    for frame_index in range(frame_count):
        start = frame_index * channels
        total = sum(int(sample) for sample in samples[start : start + channels])
        mixed.append(_clamp_i16(round(total / channels)))
    return mixed


def _resample(samples: array.array, source_rate: int, target_rate: int) -> array.array:
    if source_rate == target_rate:
        return samples
    if not samples:
        return array.array("h")
    target_count = max(1, math.floor(len(samples) * target_rate / source_rate))
    output = array.array("h")
    ratio = source_rate / target_rate
    last_index = len(samples) - 1
    for target_index in range(target_count):
        source_position = target_index * ratio
        left_index = min(int(source_position), last_index)
        right_index = min(left_index + 1, last_index)
        fraction = source_position - left_index
        value = int(samples[left_index]) * (1.0 - fraction) + int(samples[right_index]) * fraction
        output.append(_clamp_i16(round(value)))
    return output


def _clamp_i16(value: int) -> int:
    return min(32767, max(-32768, value))


def _http_post(url: str, data: bytes, headers: dict[str, str], timeout_sec: float) -> bytes:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        return response.read()


def validate_voicevox_query_payload(payload: bytes) -> None:
    """Lightweight guard used by tests and future diagnostics."""

    try:
        json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TtsProviderError(
            "TTS_SYNTHESIS_FAILED",
            "local TTS provider returned invalid audio query JSON",
            recoverable=True,
        ) from exc
