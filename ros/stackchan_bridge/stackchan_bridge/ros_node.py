"""Lazy ROS 2 node adapter for the StackChan bridge facade."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable, Iterable
from types import SimpleNamespace

from stackchan_bridge.audio_codec import (
    AUDIO_CHUNK_FORMAT_ID_IMA_ADPCM_4BIT,
    EncodedAudioPayload,
    encode_ima_adpcm_4bit,
)
from stackchan_bridge.asr import DEFAULT_ASR_TIMEOUT_SEC, LocalAsrWorker, WhisperHttpAsrEngine
from stackchan_bridge.audio_session import AudioChunk
from stackchan_bridge.event_aggregator import EventAggregator
from stackchan_bridge.event_buffer import EventBuffer, EventRecord
from stackchan_bridge.facade import StackChanBridgeFacade
from stackchan_bridge.models import CapabilitySnapshot, CommandMeta, Result, StatusSnapshot
from stackchan_bridge.models import PRIORITY_SAFETY
from stackchan_bridge.models import STATE_TIMEOUT
from stackchan_bridge.registry import DeviceAvailability, DeviceRecord, DeviceRegistry
from stackchan_bridge.speech_node import SpeechEvent, SpeechSessionProcessor
from stackchan_bridge.speech_session import SpeechTranscript, SpeechTranscriptStore
from stackchan_bridge.telemetry import HeadPoseSnapshot, HeadPoseTelemetryStore, PowerStatusSnapshot, PowerTelemetryStore
from stackchan_bridge.tts_provider import (
    AUDIO_CHANNELS,
    AUDIO_CHUNK_BYTES,
    AUDIO_CHUNK_FORMAT_ID,
    AUDIO_FORMAT,
    AUDIO_SAMPLE_RATE,
    DEFAULT_TTS_TIMEOUT_SEC,
    TtsAudio,
    TtsProviderError,
    VoiceProfile,
    VoiceVoxTtsProvider,
    default_voice_profiles,
)

EVENT_QOS_DEPTH = 32
DEFAULT_LIVENESS_TIMEOUT_SEC = 3.5
LIVENESS_CHECK_INTERVAL_SEC = 1.0
AUDIO_PLAYBACK_DIRECTION = 1
AUDIO_PLAYBACK_BUFFER_MAX_CHUNKS = 1024
AUDIO_PLAYBACK_FIRST_CHUNK_RETRY_COUNT = 3
AUDIO_PLAYBACK_FIRST_CHUNK_RETRY_INTERVAL_SEC = 0.03
AUDIO_PLAYBACK_SUBSCRIPTION_MATCH_TIMEOUT_SEC = 1.5
AUDIO_PLAYBACK_SUBSCRIPTION_MATCH_INTERVAL_SEC = 0.05
AUDIO_PLAYBACK_INPUT_IDLE_EOS_SEC = 0.35
AUDIO_PLAYBACK_BUFFERED_PUBLISH_INTERVAL_SEC = 0.15
AUDIO_PLAYBACK_TOPIC_CHUNK_RETRY_COUNT = 1
AUDIO_PLAYBACK_TOPIC_CHUNK_RETRY_INTERVAL_SEC = 0.005
AUDIO_PLAYBACK_PULL_REPUBLISH_RETRY_COUNT = 3
AUDIO_PLAYBACK_PULL_REPUBLISH_RETRY_INTERVAL_SEC = 0.03
AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS = 2
AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS = 8
AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS = 8
AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC = 0.0
AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT = 2
AUDIO_PLAYBACK_FIRST_GOAL_BYTES_DEFAULT = 64
AUDIO_PLAYBACK_CHUNK_BYTES_DEFAULT = 160
AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_DEFAULT = 64
AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES_DEFAULT = 128
AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_MAX = 1280
AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC = 0.15
AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC = 0.6
AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC = 30.0
AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS = 1
AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC = 0.0
AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES = 3
AUDIO_PLAYBACK_COMMAND_PRELOAD_WAIT_SEC = 2.5
AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES = 32 * 1024
AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES"
)
MEDIA_ACTION_SETTLE_SEC = 3.0
TTS_SPEED_SCALE_DEFAULT = 1.0
TTS_PRE_PHONEME_LENGTH_DEFAULT = 0.03
TTS_POST_PHONEME_LENGTH_DEFAULT = 0.03
TTS_SILENCE_TRIM_THRESHOLD_DEFAULT = 256
TTS_SILENCE_TRIM_MARGIN_MS_DEFAULT = 30.0
AUDIO_PLAYBACK_FIRST_GOAL_BYTES_ENV = "STACKCHAN_AUDIO_PLAYBACK_FIRST_GOAL_BYTES"
AUDIO_PLAYBACK_CHUNK_BYTES_ENV = "STACKCHAN_AUDIO_PLAYBACK_CHUNK_BYTES"
AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_ENV = "STACKCHAN_AUDIO_PLAYBACK_LOAD_CHUNK_BYTES"
AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES_ENV = "STACKCHAN_AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES"
AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS"
)
AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS"
)
AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS_ENV = "STACKCHAN_AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS"
AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC"
)
AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT"
)
AUDIO_PLAYBACK_PULL_ONLY_ENV = "STACKCHAN_AUDIO_PLAYBACK_PULL_ONLY"
AUDIO_PLAYBACK_LOADED_TTS_ENV = "STACKCHAN_TTS_LOADED_PLAYBACK"
AUDIO_PLAYBACK_LOADED_ADPCM_ENV = "STACKCHAN_TTS_LOADED_ADPCM"
AUDIO_PLAYBACK_LOADED_TRANSPORT_ENV = "STACKCHAN_TTS_LOADED_TRANSPORT"
AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC"
)
AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC"
)
AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC"
)
AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS"
)
AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC"
)
AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES_ENV = (
    "STACKCHAN_AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES"
)
MEDIA_ACTION_SETTLE_SEC_ENV = "STACKCHAN_MEDIA_ACTION_SETTLE_SEC"
ASR_ENABLED_ENV = "STACKCHAN_ASR_ENABLED"
ASR_PROVIDER_ENV = "STACKCHAN_ASR_PROVIDER"
ASR_ENDPOINT_ENV = "STACKCHAN_ASR_ENDPOINT"
ASR_MODEL_ENV = "STACKCHAN_ASR_MODEL"
ASR_LANGUAGE_ENV = "STACKCHAN_ASR_LANGUAGE"
ASR_TIMEOUT_SEC_ENV = "STACKCHAN_ASR_TIMEOUT_SEC"


class MediaActionGate:
    _IDLE_STATUS_CAPABILITIES = {
        "audio playback": "audio_playback",
        "audio capture": "audio_capture",
    }

    def __init__(
        self,
        settle_sec: float,
        *,
        clock=time.monotonic,
        idle_release_grace_sec: float = 0.5,
    ) -> None:
        self._settle_sec = max(0.0, float(settle_sec))
        self._idle_release_grace_sec = max(0.0, float(idle_release_grace_sec))
        self._clock = clock
        self._lock = threading.Lock()
        self._active: dict[str, SimpleNamespace] = {}
        self._settling: dict[str, SimpleNamespace] = {}

    def begin(self, device_id: str, command_id: str, label: str) -> Result | None:
        now = self._clock()
        with self._lock:
            settling = self._settling.get(device_id)
            if settling is not None:
                remaining = float(settling.until_monotonic) - now
                if remaining > 0:
                    return Result.rejected(
                        "FIRMWARE_BUSY",
                        (
                            f"firmware media action for '{device_id}' is settling "
                            f"after timed-out {settling.label} "
                            f"command_id={settling.command_id!r}; "
                            f"retry after {remaining:.1f}s"
                        ),
                        recoverable=True,
                    )
                self._settling.pop(device_id, None)

            active = self._active.get(device_id)
            if active is not None and active.command_id != command_id:
                return Result.rejected(
                    "FIRMWARE_BUSY",
                    (
                        f"firmware media action for '{device_id}' is already active "
                        f"command_id={active.command_id!r} label={active.label!r}"
                    ),
                    recoverable=True,
                )

            self._active[device_id] = SimpleNamespace(
                command_id=command_id,
                label=label,
                started_monotonic=now,
                busy_seen=False,
            )
            return None

    def finish(self, device_id: str, command_id: str, label: str, result: Result) -> float:
        now = self._clock()
        timed_out = (
            result.state == STATE_TIMEOUT
            or result.error_code == "TIMEOUT"
            or "timed out" in result.message.lower()
        )
        with self._lock:
            finished_active = False
            active = self._active.get(device_id)
            if active is not None and active.command_id == command_id:
                self._active.pop(device_id, None)
                finished_active = True
            if finished_active and timed_out and self._settle_sec > 0:
                until = now + self._settle_sec
                self._settling[device_id] = SimpleNamespace(
                    command_id=command_id,
                    label=label,
                    until_monotonic=until,
                )
                return until
            settling = self._settling.get(device_id)
            if settling is not None and settling.command_id == command_id:
                self._settling.pop(device_id, None)
            return 0.0

    def release_if_capability_idle(
        self,
        device_id: str,
        capabilities: Iterable[CapabilitySnapshot],
    ) -> SimpleNamespace | None:
        now = self._clock()
        capability_by_name = {
            getattr(capability, "name", ""): capability for capability in capabilities
        }
        with self._lock:
            active = self._active.get(device_id)
            if active is None:
                return None
            capability_name = self._IDLE_STATUS_CAPABILITIES.get(str(active.label))
            if capability_name is None:
                return None
            age = now - float(active.started_monotonic)
            if age < self._idle_release_grace_sec:
                return None
            capability = capability_by_name.get(capability_name)
            if capability is None:
                return None
            active_or_queued = bool(getattr(capability, "active", False)) or int(
                getattr(capability, "queued", 0)
            ) > 0
            if active_or_queued:
                active.busy_seen = True
                return None
            if not bool(getattr(active, "busy_seen", False)):
                return None
            self._active.pop(device_id, None)
            return SimpleNamespace(
                command_id=active.command_id,
                label=active.label,
                capability=capability_name,
                age_sec=age,
            )

    def mark_busy_seen(self, device_id: str, command_id: str) -> None:
        with self._lock:
            active = self._active.get(device_id)
            if active is not None and active.command_id == command_id:
                active.busy_seen = True

    def settling_command_id(self, device_id: str) -> str | None:
        now = self._clock()
        with self._lock:
            settling = self._settling.get(device_id)
            if settling is None:
                return None
            if float(settling.until_monotonic) <= now:
                self._settling.pop(device_id, None)
                return None
            return str(settling.command_id)


def _audio_playback_chunk_bytes() -> int:
    raw_value = os.environ.get(AUDIO_PLAYBACK_CHUNK_BYTES_ENV)
    if raw_value is None:
        return AUDIO_PLAYBACK_CHUNK_BYTES_DEFAULT
    return _bounded_even_audio_chunk_bytes(raw_value, AUDIO_PLAYBACK_CHUNK_BYTES_DEFAULT)


def _audio_playback_load_chunk_bytes() -> int:
    raw_value = os.environ.get(AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_ENV)
    if raw_value is None:
        return min(_audio_playback_chunk_bytes(), AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_DEFAULT)
    return _bounded_even_audio_chunk_bytes(
        raw_value,
        AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_DEFAULT,
        maximum=AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_MAX,
    )


def _audio_playback_adpcm_load_chunk_bytes() -> int:
    raw_value = os.environ.get(AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES_ENV)
    if raw_value is None:
        return AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES_DEFAULT
    return _bounded_even_audio_chunk_bytes(
        raw_value,
        AUDIO_PLAYBACK_ADPCM_LOAD_CHUNK_BYTES_DEFAULT,
        maximum=AUDIO_PLAYBACK_LOAD_CHUNK_BYTES_MAX,
    )


def _audio_playback_load_chunk_bytes_for_format(format_id: int) -> int:
    if format_id == AUDIO_CHUNK_FORMAT_ID_IMA_ADPCM_4BIT:
        return max(4, _audio_playback_adpcm_load_chunk_bytes())
    return _audio_playback_load_chunk_bytes()


def _bounded_even_audio_chunk_bytes(
    raw_value: str,
    default: int,
    *,
    maximum: int = AUDIO_CHUNK_BYTES,
) -> int:
    try:
        value = int(raw_value)
    except ValueError:
        return default
    value = min(max(value, 2), maximum)
    if value % 2:
        value -= 1
    return max(value, 2)


def _audio_playback_first_goal_bytes() -> int:
    raw_value = os.environ.get(AUDIO_PLAYBACK_FIRST_GOAL_BYTES_ENV)
    if raw_value is None:
        return AUDIO_PLAYBACK_FIRST_GOAL_BYTES_DEFAULT
    try:
        value = int(raw_value)
    except ValueError:
        return AUDIO_PLAYBACK_FIRST_GOAL_BYTES_DEFAULT
    value = min(max(value, 0), AUDIO_CHUNK_BYTES)
    if value % 2:
        value -= 1
    return max(value, 0)


def _audio_playback_pull_only() -> bool:
    return os.environ.get(AUDIO_PLAYBACK_PULL_ONLY_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _audio_playback_pull_service_fallback_after_nacks() -> int:
    raw_value = os.environ.get(AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS_ENV)
    if raw_value is None:
        return AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS
    try:
        value = int(raw_value)
    except ValueError:
        return AUDIO_PLAYBACK_PULL_SERVICE_FALLBACK_AFTER_NACKS
    return min(max(value, 0), 16)


def _bounded_positive_audio_window(raw_value: str | None, default: int) -> int:
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return min(max(value, 1), AUDIO_PLAYBACK_BUFFER_MAX_CHUNKS)


def _audio_playback_topic_initial_window_chunks() -> int:
    return _bounded_positive_audio_window(
        os.environ.get(AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS_ENV),
        AUDIO_PLAYBACK_TOPIC_INITIAL_WINDOW_CHUNKS,
    )


def _audio_playback_pull_lookahead_chunks() -> int:
    return _bounded_positive_audio_window(
        os.environ.get(AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS_ENV),
        AUDIO_PLAYBACK_PULL_LOOKAHEAD_CHUNKS,
    )


def _audio_playback_loaded_tts() -> bool:
    return os.environ.get(AUDIO_PLAYBACK_LOADED_TTS_ENV, "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _audio_playback_loaded_adpcm() -> bool:
    return os.environ.get(AUDIO_PLAYBACK_LOADED_ADPCM_ENV, "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _audio_playback_loaded_transport() -> str:
    value = os.environ.get(AUDIO_PLAYBACK_LOADED_TRANSPORT_ENV, "topic").strip().lower()
    if value in {"service", "svc", "load_service"}:
        return "service"
    return "topic"


def _loaded_audio_transfer_candidates(audio: TtsAudio) -> tuple[EncodedAudioPayload, ...]:
    pcm_payload = EncodedAudioPayload(
        payload=audio.pcm,
        format_id=AUDIO_CHUNK_FORMAT_ID,
        decoded_bytes=len(audio.pcm),
        encoding=AUDIO_FORMAT,
    )
    if not _audio_playback_loaded_adpcm():
        return (pcm_payload,)
    try:
        adpcm_payload = EncodedAudioPayload(
            payload=encode_ima_adpcm_4bit(audio.pcm),
            format_id=AUDIO_CHUNK_FORMAT_ID_IMA_ADPCM_4BIT,
            decoded_bytes=len(audio.pcm),
            encoding="ima_adpcm_4bit",
        )
    except ValueError:
        return (pcm_payload,)
    return (adpcm_payload, pcm_payload)


def _optional_positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0.0 else None


def _optional_nonnegative_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0.0 else None


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _audio_playback_ack_republish_min_interval_sec() -> float:
    return min(
        max(
            _env_float(
                AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC_ENV,
                AUDIO_PLAYBACK_ACK_REPUBLISH_MIN_INTERVAL_SEC,
            ),
            0.0,
        ),
        2.0,
    )


def _audio_playback_loaded_topic_settle_sec() -> float:
    return min(
        max(
            _env_float(
                AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC_ENV,
                AUDIO_PLAYBACK_LOADED_TOPIC_SETTLE_SEC,
            ),
            0.0,
        ),
        2.0,
    )


def _audio_playback_loaded_topic_publish_interval_sec() -> float:
    return min(
        max(
            _env_float(
                AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC_ENV,
                AUDIO_PLAYBACK_LOADED_TOPIC_PUBLISH_INTERVAL_SEC,
            ),
            0.0,
        ),
        2.0,
    )


def _audio_playback_loaded_topic_complete_timeout_sec() -> float:
    return min(
        max(
            _env_float(
                AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC_ENV,
                AUDIO_PLAYBACK_LOADED_TOPIC_COMPLETE_TIMEOUT_SEC,
            ),
            0.0,
        ),
        60.0,
    )


def _audio_playback_loaded_topic_window_chunks() -> int:
    return min(
        max(
            _env_int(
                AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS_ENV,
                AUDIO_PLAYBACK_LOADED_TOPIC_WINDOW_CHUNKS,
            ),
            1,
        ),
        8,
    )


def _audio_playback_loaded_topic_progress_timeout_sec() -> float:
    return min(
        max(
            _env_float(
                AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC_ENV,
                AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_TIMEOUT_SEC,
            ),
            0.0,
        ),
        10.0,
    )


def _audio_playback_loaded_topic_progress_retries() -> int:
    return min(
        max(
            _env_int(
                AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES_ENV,
                AUDIO_PLAYBACK_LOADED_TOPIC_PROGRESS_RETRIES,
            ),
            0,
        ),
        8,
    )


def _audio_playback_command_loaded_max_decoded_bytes() -> int:
    return min(
        max(
            _env_int(
                AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES_ENV,
                AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES,
            ),
            0,
        ),
        32 * 1024,
    )


def _loaded_audio_topic_buffered_chunks(payload: dict[str, object]) -> int:
    for key in ("expected_seq", "buf_chunks"):
        if key not in payload:
            continue
        try:
            return max(int(payload.get(key, 0)), 0)
        except (TypeError, ValueError):
            continue
    return 0


def _loaded_audio_topic_error_code(payload: dict[str, object]) -> str:
    error_code = str(payload.get("result") or "")
    return "" if error_code == "OK" else error_code


def _media_action_settle_sec() -> float:
    return min(
        max(
            _env_float(
                MEDIA_ACTION_SETTLE_SEC_ENV,
                MEDIA_ACTION_SETTLE_SEC,
            ),
            0.0,
        ),
        30.0,
    )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _audio_playback_ack_first_chunk_retry_count() -> int:
    return min(
        max(
            _env_int(
                AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT_ENV,
                AUDIO_PLAYBACK_ACK_FIRST_CHUNK_RETRY_COUNT,
            ),
            1,
        ),
        AUDIO_PLAYBACK_PULL_REPUBLISH_RETRY_COUNT,
    )


def _audio_chunk_pcm_size(message: object) -> int:
    pcm = getattr(message, "pcm", b"")
    size = getattr(pcm, "size", None)
    if size is not None:
        return int(size)
    try:
        return len(pcm)
    except TypeError:
        return 0


def _playback_chunk_sequence(message: object) -> int:
    return int(getattr(message, "sequence", 0))


def _select_playback_chunk_for_pull(
    queue: list[object], next_sequence: int
) -> tuple[object | None, int]:
    while queue and _playback_chunk_sequence(queue[0]) < next_sequence:
        queue.pop(0)
    chunk = None
    if queue and _playback_chunk_sequence(queue[0]) == next_sequence:
        # The firmware may retry the same service request after a transport
        # timeout. Keep the chunk until a later sequence proves it was accepted.
        chunk = queue[0]
    return chunk, len(queue)


def _select_playback_chunks_for_topic_window(
    queue: list[object], next_sequence: int, count: int
) -> list[object]:
    if count <= 0:
        return []
    chunks: list[object] = []
    for message in queue:
        if _playback_chunk_sequence(message) < next_sequence:
            continue
        chunks.append(message)
        if len(chunks) >= count:
            break
    return chunks


def _command_playback_audio_from_complete_chunks(
    request: object,
    chunks: Iterable[object],
    *,
    max_decoded_bytes: int = AUDIO_PLAYBACK_COMMAND_LOADED_MAX_DECODED_BYTES,
) -> tuple[TtsAudio | None, str]:
    if getattr(request, "format", "") != AUDIO_FORMAT:
        return None, "unsupported_format"
    sample_rate = int(getattr(request, "sample_rate", 0))
    channels = int(getattr(request, "channels", 0))
    if sample_rate != AUDIO_SAMPLE_RATE or channels != AUDIO_CHANNELS:
        return None, "unsupported_format"

    by_sequence: dict[int, bytes] = {}
    total_bytes = 0
    eos_sequence: int | None = None
    if bool(getattr(request, "first_chunk_present", False)):
        first_sequence = int(getattr(request, "first_chunk_sequence", 0))
        first_pcm = bytes(getattr(request, "first_chunk_pcm", b""))
        if first_sequence < 0 or not first_pcm:
            return None, "malformed"
        by_sequence[first_sequence] = first_pcm
        total_bytes += len(first_pcm)

    for chunk in chunks:
        if int(getattr(chunk, "direction", 0)) != AUDIO_PLAYBACK_DIRECTION:
            return None, "malformed"
        if int(getattr(chunk, "format", 0)) != AUDIO_CHUNK_FORMAT_ID:
            return None, "unsupported_format"
        if int(getattr(chunk, "sample_rate", 0)) != sample_rate:
            return None, "unsupported_format"
        if int(getattr(chunk, "channels", 0)) != channels:
            return None, "unsupported_format"
        sequence = int(getattr(chunk, "sequence", 0))
        pcm = bytes(getattr(chunk, "pcm", b""))
        if sequence < 0 or not pcm:
            return None, "malformed"
        existing = by_sequence.get(sequence)
        if existing is not None and existing != pcm:
            return None, "malformed"
        if existing is None:
            by_sequence[sequence] = pcm
            total_bytes += len(pcm)
        declared_total = int(getattr(chunk, "total_bytes", 0))
        if declared_total > max_decoded_bytes:
            return None, "too_large"
        if bool(getattr(chunk, "end_of_stream", False)):
            eos_sequence = sequence

    if total_bytes > max_decoded_bytes:
        return None, "too_large"
    if eos_sequence is None:
        return None, "incomplete"
    if not by_sequence:
        return None, "incomplete"
    for sequence in range(0, eos_sequence + 1):
        if sequence not in by_sequence:
            return None, "incomplete"
    pcm = b"".join(by_sequence[sequence] for sequence in range(0, eos_sequence + 1))
    if not pcm:
        return None, "incomplete"
    return TtsAudio(pcm=pcm, sample_rate=sample_rate, channels=channels), "complete"


def _loaded_playback_completion_from_events(
    records: Iterable[EventRecord],
    command_id: str,
) -> Result | None:
    if not command_id:
        return None
    for record in reversed(tuple(records)):
        if record.command_id != command_id:
            continue
        if record.event_name != "audio_playback_chunk":
            continue
        payload = dict(record.payload)
        if (
            payload.get("stage") == "loaded_playback_drained"
            and payload.get("result") == "OK"
        ):
            return Result.completed("audio playback completed from loaded playback drain")
    return None


def _next_audio_chunk_transport_control(request: object) -> tuple[int, int]:
    next_sequence = int(getattr(request, "next_sequence", 0))
    if bool(getattr(request, "has_acknowledgement", False)):
        acknowledged_sequence = int(getattr(request, "acknowledged_sequence", 0))
        next_sequence = max(next_sequence, acknowledged_sequence + 1)
    if bool(getattr(request, "has_missing_sequence", False)):
        missing_sequence = int(getattr(request, "missing_sequence", 0))
        next_sequence = max(next_sequence, missing_sequence)
    window_count = _audio_playback_pull_lookahead_chunks()
    if hasattr(request, "free_buffer_chunks"):
        free_buffer_chunks = max(int(getattr(request, "free_buffer_chunks", 0)), 0)
        window_count = min(window_count, free_buffer_chunks)
    return next_sequence, window_count


def _should_republish_audio_window_for_ack(
    stats: dict,
    next_sequence: int,
    window_count: int,
    now: float,
    min_interval_sec: float,
) -> bool:
    state = stats.setdefault("ack_republish_state", {})
    for sequence in list(state):
        if int(sequence) < next_sequence:
            state.pop(sequence, None)
    last = state.get(next_sequence)
    if last is not None:
        last_monotonic, last_window_count = last
        if (
            now - float(last_monotonic) < min_interval_sec
            and window_count <= int(last_window_count)
        ):
            return False
    state[next_sequence] = (now, window_count)
    return True


def _set_optional_field(target: object, name: str, value: object) -> None:
    if hasattr(target, name):
        setattr(target, name, value)


def _time_to_string(stamp: object) -> str:
    sec = getattr(stamp, "sec", 0)
    nanosec = getattr(stamp, "nanosec", 0)
    return f"{sec}.{nanosec:09d}"


def _meta_from_ros(meta: object, fallback_device_id: str = "default") -> CommandMeta:
    return CommandMeta(
        device_id=fallback_device_id,
        command_id=getattr(meta, "command_id", ""),
        source=getattr(meta, "source", ""),
        created_at=_time_to_string(getattr(meta, "created_at", None)),
        priority=getattr(meta, "priority", 1),
    )


def _normalize_device_ids(value: object) -> list[str]:
    raw_device_ids = [value] if isinstance(value, str) else list(value or [])
    device_ids: list[str] = []
    for raw_device_id in raw_device_ids:
        device_id = str(raw_device_id).strip()
        if device_id and device_id not in device_ids:
            device_ids.append(device_id)
    return device_ids or ["default"]


def _normalize_voice_profile_names(value: object) -> list[str]:
    raw_profiles = [value] if isinstance(value, str) else list(value or [])
    profiles: list[str] = []
    for raw_profile in raw_profiles:
        profile = str(raw_profile).strip()
        if (
            profile
            and profile not in profiles
            and all(character.isalnum() or character in "_-" for character in profile)
        ):
            profiles.append(profile)
    return profiles or ["default"]


def _configured_device_records(
    device_ids: list[str], *, connected: bool
) -> list[DeviceRecord]:
    return [DeviceRecord(device_id, connected=connected) for device_id in device_ids]


def _copy_result(result: object, source: object) -> None:
    result.ok = source.ok
    result.state = source.state
    result.error_code = source.error_code
    result.message = source.message
    result.recoverable = source.recoverable


def _copy_compressed_image_payload(target: object, source: object) -> None:
    target.format = getattr(source, "format", "")
    target.data = bytes(getattr(source, "data", b""))


def _copy_command_meta(target: object, source: CommandMeta, created_at: object) -> None:
    target.device_id = source.device_id
    target.command_id = source.command_id
    target.source = source.source
    target.created_at = created_at
    target.priority = source.priority


def _make_transport_result(message: str) -> Result:
    return Result.rejected("TRANSPORT_DISCONNECTED", message, recoverable=True)


def _make_timeout_result(message: str) -> Result:
    return Result(
        ok=False,
        state=STATE_TIMEOUT,
        error_code="TIMEOUT",
        message=message,
        recoverable=True,
    )


def _make_camera_capture_failed_result(message: str) -> Result:
    return Result.rejected("CAMERA_CAPTURE_FAILED", message, recoverable=True)


def _copy_status(response: object, status: object) -> None:
    response.device_id = status.device_id
    response.connected = status.connected
    response.state = status.state
    response.face = status.face
    response.motion = status.motion
    response.last_command_id = status.last_command_id
    _copy_result(response.last_error, status.last_error)
    if hasattr(response, "firmware_version"):
        response.firmware_version = getattr(status, "firmware_version", "")


def _copy_status_with_type(response: object, status: object, capability_type: object) -> None:
    _copy_status(response, status)
    if hasattr(response, "capabilities"):
        response.capabilities = [
            _make_capability_status(capability_type, capability)
            for capability in getattr(status, "capabilities", [])
        ]


def _make_capability_status(capability_type: object, capability: object) -> object:
    message = capability_type()
    message.name = getattr(capability, "name", "")
    message.state = getattr(capability, "state", "")
    message.detail_code = getattr(capability, "detail_code", "")
    message.active = bool(getattr(capability, "active", False))
    message.queued = int(getattr(capability, "queued", 0))
    last_update = getattr(capability, "last_update", None)
    if last_update is not None:
        _copy_seconds_to_stamp(message.last_update, float(last_update))
    return message


def _result_from_ros(source: object) -> Result:
    return Result(
        ok=bool(getattr(source, "ok", True)),
        state=int(getattr(source, "state", 1)),
        error_code=getattr(source, "error_code", ""),
        message=getattr(source, "message", ""),
        recoverable=bool(getattr(source, "recoverable", False)),
    )


def _capability_from_ros(source: object) -> CapabilitySnapshot:
    last_update = _stamp_to_seconds(getattr(source, "last_update", None))
    return CapabilitySnapshot(
        name=getattr(source, "name", ""),
        state=getattr(source, "state", ""),
        detail_code=getattr(source, "detail_code", ""),
        active=bool(getattr(source, "active", False)),
        queued=int(getattr(source, "queued", 0)),
        last_update=last_update,
    )


def _snapshot_from_stackchan_status(
    status: object, *, fallback_device_id: str
) -> StatusSnapshot:
    capabilities = [
        _capability_from_ros(capability)
        for capability in getattr(status, "capabilities", [])
    ]
    return StatusSnapshot(
        device_id=getattr(status, "device_id", "") or fallback_device_id,
        connected=bool(getattr(status, "connected", False)),
        state=getattr(status, "state", "") or "unknown",
        face=getattr(status, "face", "") or "neutral",
        motion=getattr(status, "motion", "") or "idle",
        last_command_id=getattr(status, "last_command_id", ""),
        last_error=_result_from_ros(getattr(status, "last_error", object())),
        firmware_version=getattr(status, "firmware_version", ""),
        capabilities=capabilities or StatusSnapshot().capabilities,
    )


def _reject_external_safety_priority(meta: CommandMeta, response: object) -> bool:
    if meta.priority != PRIORITY_SAFETY:
        return False

    result = Result.rejected(
        "INVALID_PRIORITY",
        "SAFETY priority is reserved for bridge and firmware internals.",
    )
    if hasattr(response, "result"):
        _copy_result(response.result, result)
    elif hasattr(response, "last_error"):
        _copy_result(response.last_error, result)

    if hasattr(response, "events"):
        response.events = []
    if hasattr(response, "cursor"):
        response.cursor = ""
    if hasattr(response, "stale"):
        response.stale = False
    if hasattr(response, "transcript"):
        response.transcript = ""
    if hasattr(response, "confidence"):
        response.confidence = 0.0
    return True


def _stamp_to_seconds(stamp: object) -> float | None:
    sec = int(getattr(stamp, "sec", 0))
    nanosec = int(getattr(stamp, "nanosec", 0))
    if sec == 0 and nanosec == 0:
        return None
    return sec + nanosec / 1_000_000_000


def _copy_seconds_to_stamp(target: object, stamp: float) -> None:
    sec = int(stamp)
    target.sec = sec
    target.nanosec = int((stamp - sec) * 1_000_000_000)


def _copy_event_record(target: object, record: EventRecord) -> None:
    target.event_id = record.event_id
    target.device_id = record.device_id
    target.event_name = record.event_name
    target.source = record.source
    _copy_seconds_to_stamp(target.stamp, record.stamp)
    target.command_id = record.command_id
    target.payload_json = json.dumps(
        dict(record.payload),
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _records_after_event_id(
    records: tuple[EventRecord, ...], event_id: str
) -> tuple[EventRecord, ...]:
    if not event_id:
        return records
    for index, record in enumerate(records):
        if record.event_id == event_id:
            return records[index + 1 :]
    return records


def _sequence_for_event_id(records: tuple[EventRecord, ...], event_id: str) -> int | None:
    if not event_id:
        return None
    for record in records:
        if record.event_id == event_id:
            return record.sequence
    return None


def _cursor_for(records: tuple[EventRecord, ...]) -> str:
    return records[-1].event_id if records else ""


def _copy_records(response: object, event_type: object, records: tuple[EventRecord, ...]) -> None:
    events = []
    for record in records:
        event = event_type()
        _copy_event_record(event, record)
        events.append(event)
    response.events = events


def _copy_transcript(response: object, transcript: SpeechTranscript) -> None:
    response.utterance_id = transcript.utterance_id
    response.transcript = transcript.text
    response.confidence = transcript.confidence
    _copy_seconds_to_stamp(response.expires_at, transcript.expires_at)


def _snapshot_from_power_status(status: object, *, fallback_device_id: str) -> PowerStatusSnapshot:
    stamp = _stamp_to_seconds(getattr(status, "stamp", None))
    return PowerStatusSnapshot(
        device_id=getattr(status, "device_id", "") or fallback_device_id,
        voltage_v=float(getattr(status, "voltage_v", float("nan"))),
        current_ma=float(getattr(status, "current_ma", float("nan"))),
        power_mw=float(getattr(status, "power_mw", float("nan"))),
        percentage=float(getattr(status, "percentage", float("nan"))),
        power_source=int(getattr(status, "power_source", 0)),
        charging=bool(getattr(status, "charging", False)),
        powered=bool(getattr(status, "powered", False)),
        low_battery=bool(getattr(status, "low_battery", False)),
        brownout_risk=bool(getattr(status, "brownout_risk", False)),
        fault_code=getattr(status, "fault_code", ""),
        stamp=stamp if stamp is not None else 0.0,
    )


def _snapshot_from_head_pose(pose: object, *, fallback_device_id: str) -> HeadPoseSnapshot:
    stamp = _stamp_to_seconds(getattr(pose, "stamp", None))
    return HeadPoseSnapshot(
        device_id=getattr(pose, "device_id", "") or fallback_device_id,
        pan_deg=float(getattr(pose, "pan_deg", float("nan"))),
        tilt_deg=float(getattr(pose, "tilt_deg", float("nan"))),
        moving=bool(getattr(pose, "moving", False)),
        frame=getattr(pose, "frame", "") or "home",
        stamp=stamp if stamp is not None else 0.0,
    )


def _copy_power_status(target: object, snapshot: PowerStatusSnapshot) -> None:
    target.device_id = snapshot.device_id
    _copy_seconds_to_stamp(target.stamp, snapshot.stamp)
    target.voltage_v = snapshot.voltage_v
    target.current_ma = snapshot.current_ma
    target.power_mw = snapshot.power_mw
    target.percentage = snapshot.percentage
    target.power_source = snapshot.power_source
    target.charging = snapshot.charging
    target.powered = snapshot.powered
    target.low_battery = snapshot.low_battery
    target.brownout_risk = snapshot.brownout_risk
    target.fault_code = snapshot.fault_code


def _copy_head_pose(target: object, snapshot: HeadPoseSnapshot) -> None:
    target.device_id = snapshot.device_id
    _copy_seconds_to_stamp(target.stamp, snapshot.stamp)
    target.pan_deg = snapshot.pan_deg
    target.tilt_deg = snapshot.tilt_deg
    target.moving = snapshot.moving
    target.frame = snapshot.frame


def _coerce_telemetry_device_id(message: object, expected_device_id: str) -> bool:
    incoming_device_id = getattr(message, "device_id", "")
    if not incoming_device_id:
        message.device_id = expected_device_id
        return True
    return incoming_device_id == expected_device_id


def _relay_telemetry_message(
    device_id: str,
    tail: str,
    message: object,
    publisher: object,
    *,
    power_store: PowerTelemetryStore | None = None,
    head_pose_store: HeadPoseTelemetryStore | None = None,
    conflict_handler: object | None = None,
) -> bool:
    if not _coerce_telemetry_device_id(message, device_id):
        if callable(conflict_handler):
            conflict_handler(device_id, tail, message)
        return False
    if tail == "power/status" and power_store is not None:
        power_store.update(_snapshot_from_power_status(message, fallback_device_id=device_id))
    if tail == "motion/pose" and head_pose_store is not None:
        head_pose_store.update(_snapshot_from_head_pose(message, fallback_device_id=device_id))
    publisher.publish(message)
    return True


def _event_matches_device_id(device_id: str, event: object) -> bool:
    incoming_device_id = getattr(event, "device_id", "")
    return not incoming_device_id or incoming_device_id == device_id


def _status_matches_device_id(device_id: str, status: object) -> bool:
    incoming_device_id = getattr(status, "device_id", "")
    return not incoming_device_id or incoming_device_id == device_id


def _mark_device_available_from_event(
    registry: DeviceRegistry,
    device_id: str,
    event: object,
) -> bool:
    if not _event_matches_device_id(device_id, event):
        return False
    source = getattr(event, "source", "") or "firmware"
    event_name = getattr(event, "event_name", "")
    if source != "firmware" or not event_name:
        return False
    was_available = registry.availability(device_id) == DeviceAvailability.AVAILABLE
    registry.set_connected(device_id, True)
    return not was_available


def _mark_device_available_from_status(
    registry: DeviceRegistry,
    device_id: str,
    status: object,
) -> bool:
    if not _status_matches_device_id(device_id, status):
        return False
    is_connected = bool(getattr(status, "connected", False))
    was_available = registry.availability(device_id) == DeviceAvailability.AVAILABLE
    registry.set_connected(device_id, is_connected)
    return is_connected and not was_available


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
        from rclpy.action import ActionClient, ActionServer
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.executors import MultiThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from stackchan_msgs.action import CaptureAudio, CaptureCamera, MoveHeadPose, PlayAudio, RunMotion, Say
        from stackchan_msgs.msg import AudioChunk as RosAudioChunk
        from stackchan_msgs.msg import AudioPlaybackAck
        from stackchan_msgs.msg import CapabilityStatus
        from stackchan_msgs.msg import (
            HeadPose,
            ImuRaw,
            LightRaw,
            PowerStatus,
            ProximityRaw,
            StackChanEvent,
            StackChanStatus,
            TouchState,
        )
        from stackchan_msgs.srv import (
            ClearEventCursor,
            GetHeadPose,
            GetPowerStatus,
            GetStatus,
            GetTranscript,
            ListEvents,
            LoadAudioChunk,
            NextAudioChunk,
            NextEvent,
            SetFace,
            SetHeadPose,
            SetLed,
            SetMotion,
        )
    except ImportError as exc:  # pragma: no cover - exercised only without ROS.
        raise RuntimeError(
            "stackchan_bridge_node requires ROS 2 Python packages."
        ) from exc

    reliable_depth_2 = QoSProfile(depth=2)
    reliable_depth_4 = QoSProfile(depth=4)
    reliable_depth_8 = QoSProfile(depth=8)
    reliable_depth_64 = QoSProfile(depth=64)
    best_effort_depth_5 = QoSProfile(depth=5)
    best_effort_depth_5.reliability = ReliabilityPolicy.BEST_EFFORT
    best_effort_depth_8 = QoSProfile(depth=8)
    best_effort_depth_8.reliability = ReliabilityPolicy.BEST_EFFORT
    best_effort_depth_10 = QoSProfile(depth=10)
    best_effort_depth_10.reliability = ReliabilityPolicy.BEST_EFFORT
    action_status_best_effort_depth_1 = QoSProfile(depth=1)
    action_status_best_effort_depth_1.reliability = ReliabilityPolicy.BEST_EFFORT
    action_status_best_effort_depth_1.durability = DurabilityPolicy.VOLATILE
    transient_depth_1 = QoSProfile(depth=1)
    transient_depth_1.durability = DurabilityPolicy.TRANSIENT_LOCAL

    class StackChanBridgeNode(Node):
        def __init__(self) -> None:
            super().__init__("stackchan_bridge")
            self.declare_parameter("device_ids", ["default"])
            configured_device_ids = _normalize_device_ids(
                self.get_parameter("device_ids").value
            )
            self.declare_parameter("device_connected", False)
            device_connected = bool(self.get_parameter("device_connected").value)
            self.declare_parameter("liveness_timeout_sec", DEFAULT_LIVENESS_TIMEOUT_SEC)
            self._liveness_timeout_sec = float(
                self.get_parameter("liveness_timeout_sec").value
            )
            self.declare_parameter("device_command_timeout_sec", 2.0)
            self._device_command_timeout_sec = float(
                self.get_parameter("device_command_timeout_sec").value
            )
            self.declare_parameter("device_media_action_timeout_sec", 35.0)
            self._device_media_action_timeout_sec = float(
                self.get_parameter("device_media_action_timeout_sec").value
            )
            self.declare_parameter("media_action_settle_sec", _media_action_settle_sec())
            self._media_action_gate = MediaActionGate(
                float(self.get_parameter("media_action_settle_sec").value)
            )
            self._tts_provider = None
            self._tts_default_voice = "default"
            registry = DeviceRegistry(
                _configured_device_records(
                    configured_device_ids,
                    connected=device_connected,
                )
            )
            self.facade = StackChanBridgeFacade(
                registry=registry,
                logger=self.get_logger(),
            )
            self.event_buffer = EventBuffer()
            self.event_aggregator = EventAggregator(self.event_buffer)
            self.transcript_store = SpeechTranscriptStore()
            self._asr_worker = self._configure_asr_worker()
            self.speech_processor = SpeechSessionProcessor(
                transcript_store=self.transcript_store,
                event_sink=self._handle_speech_event,
                asr_worker=self._asr_worker,
            )
            self.power_store = PowerTelemetryStore()
            self.head_pose_store = HeadPoseTelemetryStore()
            self._stackchan_event_type = StackChanEvent
            self._stackchan_status_type = StackChanStatus
            self._set_face_type = SetFace
            self._set_head_pose_type = SetHeadPose
            self._set_led_type = SetLed
            self._set_motion_type = SetMotion
            self._audio_chunk_type = RosAudioChunk
            self._command_callback_group = ReentrantCallbackGroup()
            self._device_client_callback_group = ReentrantCallbackGroup()
            self._public_event_publishers = {}
            self._public_status_publishers = {}
            self._device_audio_capture_clients = {}
            self._device_audio_load_clients = {}
            self._device_audio_play_clients = {}
            self._device_audio_chunk_publishers = {}
            self._device_camera_capture_clients = {}
            self._device_face_clients = {}
            self._device_led_clients = {}
            self._device_head_pose_clients = {}
            self._device_motion_clients = {}
            self._device_event_subscriptions = []
            self._device_status_subscriptions = []
            self._cmd_audio_chunk_subscriptions = []
            self._device_audio_playback_ack_subscriptions = []
            self._speech_audio_subscriptions = []
            self._pending_playback_chunks = {}
            self._active_playback_sessions = set()
            self._closed_playback_sessions = set()
            self._pull_only_playback_sessions = set()
            self._prebuffered_topic_playback_sessions = set()
            self._playback_relay_stats = {}
            self._playback_chunk_lock = threading.Lock()
            self._telemetry_publishers = {}
            self._telemetry_subscriptions = []
            self._device_last_seen = {}
            self._power_status_type = PowerStatus
            self._head_pose_type = HeadPose
            self._capability_status_type = CapabilityStatus
            self._action_servers = []
            self._configure_tts_provider()
            for device_id in configured_device_ids:
                self._create_device_resources(device_id)
            self._liveness_timer = self.create_timer(
                LIVENESS_CHECK_INTERVAL_SEC,
                self._expire_stale_devices,
            )

        def destroy_node(self) -> bool:
            self.speech_processor.close()
            self._asr_worker.close()
            return super().destroy_node()

        def _configure_asr_worker(self) -> LocalAsrWorker:
            self.declare_parameter("asr_enabled", _env_bool(ASR_ENABLED_ENV, False))
            if not bool(self.get_parameter("asr_enabled").value):
                return LocalAsrWorker()

            self.declare_parameter(
                "asr_provider",
                os.environ.get(ASR_PROVIDER_ENV, "whisper_http"),
            )
            provider = str(self.get_parameter("asr_provider").value or "").strip()
            if provider != "whisper_http":
                self.get_logger().warning("ASR is enabled but the provider is unsupported")
                return LocalAsrWorker()

            self.declare_parameter("asr_endpoint", os.environ.get(ASR_ENDPOINT_ENV, ""))
            endpoint = str(self.get_parameter("asr_endpoint").value or "").strip()
            self.declare_parameter("asr_model", os.environ.get(ASR_MODEL_ENV, ""))
            model = str(self.get_parameter("asr_model").value or "").strip()
            self.declare_parameter("asr_language", os.environ.get(ASR_LANGUAGE_ENV, ""))
            language = str(self.get_parameter("asr_language").value or "").strip()
            self.declare_parameter(
                "asr_timeout_sec",
                _env_float(ASR_TIMEOUT_SEC_ENV, DEFAULT_ASR_TIMEOUT_SEC),
            )
            timeout_sec = (
                _optional_positive_float(self.get_parameter("asr_timeout_sec").value)
                or DEFAULT_ASR_TIMEOUT_SEC
            )
            if not endpoint:
                self.get_logger().warning("ASR is enabled but no endpoint is configured")
                return LocalAsrWorker()

            return LocalAsrWorker(
                WhisperHttpAsrEngine(
                    endpoint=endpoint,
                    model=model,
                    language=language,
                    timeout_sec=timeout_sec,
                ),
                timeout_ms=max(1, int((timeout_sec + 1.0) * 1000)),
            )

        def _configure_tts_provider(self) -> None:
            self.declare_parameter("tts_enabled", False)
            if not bool(self.get_parameter("tts_enabled").value):
                self._tts_provider = None
                return
            default_endpoint = os.environ.get("STACKCHAN_TTS_ENDPOINT", "")
            self.declare_parameter("tts_endpoint", default_endpoint)
            endpoint = str(self.get_parameter("tts_endpoint").value or "").strip()
            self.declare_parameter("tts_timeout_sec", DEFAULT_TTS_TIMEOUT_SEC)
            timeout_sec = float(self.get_parameter("tts_timeout_sec").value)
            self.declare_parameter(
                "tts_speed_scale",
                _env_float("STACKCHAN_TTS_SPEED_SCALE", TTS_SPEED_SCALE_DEFAULT),
            )
            speed_scale = _optional_positive_float(self.get_parameter("tts_speed_scale").value)
            self.declare_parameter(
                "tts_pre_phoneme_length",
                _env_float(
                    "STACKCHAN_TTS_PRE_PHONEME_LENGTH",
                    TTS_PRE_PHONEME_LENGTH_DEFAULT,
                ),
            )
            pre_phoneme_length = _optional_nonnegative_float(
                self.get_parameter("tts_pre_phoneme_length").value
            )
            self.declare_parameter(
                "tts_post_phoneme_length",
                _env_float(
                    "STACKCHAN_TTS_POST_PHONEME_LENGTH",
                    TTS_POST_PHONEME_LENGTH_DEFAULT,
                ),
            )
            post_phoneme_length = _optional_nonnegative_float(
                self.get_parameter("tts_post_phoneme_length").value
            )
            self.declare_parameter(
                "tts_silence_trim_threshold",
                _env_int(
                    "STACKCHAN_TTS_SILENCE_TRIM_THRESHOLD",
                    TTS_SILENCE_TRIM_THRESHOLD_DEFAULT,
                ),
            )
            silence_trim_threshold = max(
                0,
                int(self.get_parameter("tts_silence_trim_threshold").value),
            )
            self.declare_parameter(
                "tts_silence_trim_margin_ms",
                _env_float(
                    "STACKCHAN_TTS_SILENCE_TRIM_MARGIN_MS",
                    TTS_SILENCE_TRIM_MARGIN_MS_DEFAULT,
                ),
            )
            silence_trim_margin_samples = round(
                max(0.0, float(self.get_parameter("tts_silence_trim_margin_ms").value))
                * AUDIO_SAMPLE_RATE
                / 1000.0
            )
            self.declare_parameter("tts_default_voice", "default")
            self._tts_default_voice = str(
                self.get_parameter("tts_default_voice").value or "default"
            ).strip() or "default"
            self.declare_parameter("tts_voice_profiles", ["default"])
            profile_names = _normalize_voice_profile_names(
                self.get_parameter("tts_voice_profiles").value
            )
            profiles = default_voice_profiles(endpoint)
            configured_profiles: dict[str, VoiceProfile] = {}
            for profile_name in profile_names:
                base = f"tts_voice_profile.{profile_name}"
                default_profile = profiles.get(profile_name) or profiles["default"]
                self.declare_parameter(f"{base}.provider", default_profile.provider)
                self.declare_parameter(f"{base}.speaker_id", default_profile.speaker_id)
                self.declare_parameter(f"{base}.endpoint", default_profile.endpoint)
                self.declare_parameter(
                    f"{base}.required_credit",
                    default_profile.required_credit,
                )
                self.declare_parameter(f"{base}.terms_url", default_profile.terms_url)
                provider = str(self.get_parameter(f"{base}.provider").value or "").strip()
                if provider != "voicevox":
                    self.get_logger().warning(
                        f"ignoring unsupported TTS provider for voice profile {profile_name!r}"
                    )
                    continue
                configured_profiles[profile_name] = VoiceProfile(
                    name=profile_name,
                    provider=provider,
                    speaker_id=int(self.get_parameter(f"{base}.speaker_id").value),
                    endpoint=str(self.get_parameter(f"{base}.endpoint").value or "").strip(),
                    required_credit=str(
                        self.get_parameter(f"{base}.required_credit").value or ""
                    ).strip(),
                    terms_url=str(self.get_parameter(f"{base}.terms_url").value or "").strip(),
                )
            if not configured_profiles:
                self.get_logger().warning("TTS is enabled but no voice profiles are configured")
                self._tts_provider = None
                return
            self._tts_provider = VoiceVoxTtsProvider(
                profiles=configured_profiles,
                default_profile=self._tts_default_voice,
                endpoint=endpoint,
                timeout_sec=timeout_sec,
                speed_scale=speed_scale,
                pre_phoneme_length=pre_phoneme_length,
                post_phoneme_length=post_phoneme_length,
                silence_trim_threshold=silence_trim_threshold,
                silence_trim_margin_samples=silence_trim_margin_samples,
            )

        def _create_device_resources(self, device_id: str) -> None:
            prefix = f"/stackchan/{device_id}/cmd"
            self.create_service(
                GetStatus,
                f"{prefix}/get_status",
                lambda request, response, device_id=device_id: self._handle_get_status(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                SetFace,
                f"{prefix}/face/set",
                lambda request, response, device_id=device_id: self._handle_set_face(
                    device_id,
                    request,
                    response,
                ),
                callback_group=self._command_callback_group,
            )
            self.create_service(
                SetLed,
                f"{prefix}/led/set",
                lambda request, response, device_id=device_id: self._handle_set_led(
                    device_id,
                    request,
                    response,
                ),
            )
            self._device_face_clients[device_id] = self.create_client(
                SetFace,
                f"/stackchan/{device_id}/device/face/set",
                callback_group=self._device_client_callback_group,
            )
            self._device_led_clients[device_id] = self.create_client(
                SetLed,
                f"/stackchan/{device_id}/device/led/set",
                callback_group=self._device_client_callback_group,
            )
            self._device_motion_clients[device_id] = self.create_client(
                SetMotion,
                f"/stackchan/{device_id}/device/motion/run",
                callback_group=self._device_client_callback_group,
            )
            self._device_head_pose_clients[device_id] = self.create_client(
                SetHeadPose,
                f"/stackchan/{device_id}/device/motion/pose/set",
                callback_group=self._device_client_callback_group,
            )
            self._device_audio_play_clients[device_id] = ActionClient(
                self,
                PlayAudio,
                f"/stackchan/{device_id}/device/audio/play",
                callback_group=self._device_client_callback_group,
                feedback_sub_qos_profile=action_status_best_effort_depth_1,
                status_sub_qos_profile=action_status_best_effort_depth_1,
            )
            self._device_audio_load_clients[device_id] = self.create_client(
                LoadAudioChunk,
                f"/stackchan/{device_id}/device/audio/playback/load",
                callback_group=self._device_client_callback_group,
            )
            self._device_audio_capture_clients[device_id] = ActionClient(
                self,
                CaptureAudio,
                f"/stackchan/{device_id}/device/audio/capture",
                callback_group=self._device_client_callback_group,
                feedback_sub_qos_profile=action_status_best_effort_depth_1,
                status_sub_qos_profile=action_status_best_effort_depth_1,
            )
            self._device_camera_capture_clients[device_id] = ActionClient(
                self,
                CaptureCamera,
                f"/stackchan/{device_id}/device/camera/capture",
                callback_group=self._device_client_callback_group,
                feedback_sub_qos_profile=action_status_best_effort_depth_1,
                status_sub_qos_profile=action_status_best_effort_depth_1,
            )
            self._device_audio_chunk_publishers[device_id] = self.create_publisher(
                RosAudioChunk,
                f"/stackchan/{device_id}/device/audio/playback/chunks",
                reliable_depth_8,
            )
            self.create_service(
                NextAudioChunk,
                f"/stackchan/{device_id}/audio/playback/next_chunk",
                lambda request, response, device_id=device_id: self._handle_next_audio_chunk(
                    device_id,
                    request,
                    response,
                ),
                callback_group=self._command_callback_group,
            )
            self.create_service(
                ListEvents,
                f"{prefix}/events/list",
                lambda request, response, device_id=device_id: self._handle_list_events(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                NextEvent,
                f"{prefix}/events/next",
                lambda request, response, device_id=device_id: self._handle_next_event(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                ClearEventCursor,
                f"{prefix}/events/clear_cursor",
                lambda request, response, device_id=device_id: self._handle_clear_event_cursor(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                GetTranscript,
                f"{prefix}/speech/transcript/get",
                lambda request, response, device_id=device_id: self._handle_get_transcript(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                GetPowerStatus,
                f"{prefix}/power/status",
                lambda request, response, device_id=device_id: self._handle_get_power_status(
                    device_id,
                    request,
                    response,
                ),
            )
            self.create_service(
                GetHeadPose,
                f"{prefix}/motion/status",
                lambda request, response, device_id=device_id: self._handle_get_head_pose(
                    device_id,
                    request,
                    response,
                ),
            )
            self._public_event_publishers[device_id] = self.create_publisher(
                StackChanEvent,
                f"/stackchan/{device_id}/events",
                QoSProfile(depth=EVENT_QOS_DEPTH),
            )
            self._public_status_publishers[device_id] = self.create_publisher(
                StackChanStatus,
                f"/stackchan/{device_id}/status",
                transient_depth_1,
            )
            self._create_telemetry_relay(
                device_id,
                "touch/state",
                TouchState,
                public_qos=transient_depth_1,
                device_qos=reliable_depth_4,
            )
            self._create_telemetry_relay(
                device_id,
                "proximity/raw",
                ProximityRaw,
                public_qos=best_effort_depth_10,
                device_qos=best_effort_depth_10,
            )
            self._create_telemetry_relay(
                device_id,
                "light/raw",
                LightRaw,
                public_qos=best_effort_depth_5,
                device_qos=best_effort_depth_5,
            )
            self._create_telemetry_relay(
                device_id,
                "power/status",
                PowerStatus,
                public_qos=transient_depth_1,
                device_qos=reliable_depth_2,
            )
            self._create_telemetry_relay(
                device_id,
                "motion/pose",
                HeadPose,
                public_qos=transient_depth_1,
                device_qos=reliable_depth_2,
            )
            self._create_telemetry_relay(
                device_id,
                "imu/raw",
                ImuRaw,
                public_qos=best_effort_depth_10,
                device_qos=best_effort_depth_10,
            )
            self._speech_audio_subscriptions.append(
                self.create_subscription(
                    RosAudioChunk,
                    f"/stackchan/{device_id}/device/audio/chunks",
                    lambda message, device_id=device_id: self._handle_speech_audio_chunk(
                        device_id,
                        message,
                    ),
                    best_effort_depth_8,
                )
            )
            self._cmd_audio_chunk_subscriptions.append(
                self.create_subscription(
                    RosAudioChunk,
                    f"/stackchan/{device_id}/cmd/audio/chunks",
                    lambda message, device_id=device_id: self._handle_cmd_audio_chunk(
                        device_id,
                        message,
                    ),
                    reliable_depth_64,
                )
            )
            self._device_audio_playback_ack_subscriptions.append(
                self.create_subscription(
                    AudioPlaybackAck,
                    f"/stackchan/{device_id}/device/audio/playback/acks",
                    lambda message, device_id=device_id: self._handle_audio_playback_ack(
                        device_id,
                        message,
                    ),
                    best_effort_depth_8,
                )
            )
            self._device_event_subscriptions.append(
                self.create_subscription(
                    StackChanEvent,
                    f"/stackchan/{device_id}/device/events",
                    lambda event, device_id=device_id: self._handle_device_event(
                        device_id,
                        event,
                    ),
                    QoSProfile(depth=EVENT_QOS_DEPTH),
                )
            )
            self._device_status_subscriptions.append(
                self.create_subscription(
                    StackChanStatus,
                    f"/stackchan/{device_id}/device/status",
                    lambda status, device_id=device_id: self._handle_device_status(
                        device_id,
                        status,
                    ),
                    reliable_depth_2,
                )
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    RunMotion,
                    f"{prefix}/motion/run",
                    lambda goal_handle, device_id=device_id: self._handle_run_motion(
                        device_id,
                        goal_handle,
                    ),
                    callback_group=self._command_callback_group,
                )
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    MoveHeadPose,
                    f"{prefix}/motion/pose",
                    lambda goal_handle, device_id=device_id: self._handle_move_head_pose(
                        device_id,
                        goal_handle,
                    ),
                )
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    Say,
                    f"{prefix}/say",
                    lambda goal_handle, device_id=device_id: self._handle_say(
                        device_id,
                        goal_handle,
                    ),
                )
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    PlayAudio,
                    f"{prefix}/audio/play",
                    lambda goal_handle, device_id=device_id: self._handle_play_audio(
                        device_id,
                        goal_handle,
                    ),
                )
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    CaptureAudio,
                    f"{prefix}/audio/capture",
                    lambda goal_handle, device_id=device_id: self._handle_capture_audio(
                        device_id,
                        goal_handle,
                    ),
                )
            )
            self._action_servers.append(
                ActionServer(
                    self,
                    CaptureCamera,
                    f"{prefix}/camera/capture",
                    lambda goal_handle, device_id=device_id: self._handle_capture_camera(
                        device_id,
                        goal_handle,
                    ),
                )
            )

        def _handle_get_status(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            if _reject_external_safety_priority(meta, response):
                response.device_id = meta.device_id
                response.connected = (
                    self.facade.registry.availability(meta.device_id)
                    == DeviceAvailability.AVAILABLE
                )
                response.state = "rejected"
                response.face = ""
                response.motion = ""
                response.last_command_id = meta.command_id
                return response
            status_response = self.facade.get_status(
                meta.device_id,
                command_id=meta.command_id,
            )
            _copy_status_with_type(
                response,
                status_response.status,
                self._capability_status_type,
            )
            return response

        def _handle_set_face(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            command_response = self.facade.set_face(
                meta,
                request.name,
                request.duration_ms,
            )
            if not command_response.result.ok:
                _copy_result(response.result, command_response.result)
                return response

            device_result = self._call_device_face_set(device_id, request, meta)
            _copy_result(response.result, device_result)
            return response

        def _call_device_face_set(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> Result:
            client = self._device_face_clients.get(device_id)
            if client is None:
                return _make_transport_result(
                    f"firmware face service for '{device_id}' is not configured"
                )
            if not client.wait_for_service(timeout_sec=0.1):
                return _make_transport_result(
                    f"firmware face service for '{device_id}' is unavailable"
                )

            device_request = self._set_face_type.Request()
            _copy_command_meta(
                device_request.meta,
                meta,
                getattr(request.meta, "created_at", device_request.meta.created_at),
            )
            device_request.name = request.name
            device_request.duration_ms = request.duration_ms

            future = client.call_async(device_request)
            deadline = time.monotonic() + self._device_command_timeout_sec
            while not future.done() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not future.done():
                future.cancel()
                return _make_timeout_result(
                    f"firmware face service for '{device_id}' timed out"
                )
            try:
                device_response = future.result()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                return _make_transport_result(
                    f"firmware face service for '{device_id}' failed: {exc}"
                )
            return _result_from_ros(device_response.result)

        def _call_device_motion_run(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> Result:
            client = self._device_motion_clients.get(device_id)
            if client is None:
                return _make_transport_result(
                    f"firmware motion service for '{device_id}' is not configured"
                )
            if not client.wait_for_service(timeout_sec=0.1):
                return _make_transport_result(
                    f"firmware motion service for '{device_id}' is unavailable"
                )

            device_request = self._set_motion_type.Request()
            _copy_command_meta(
                device_request.meta,
                meta,
                getattr(request.meta, "created_at", device_request.meta.created_at),
            )
            device_request.name = request.name
            device_request.intensity = request.intensity
            device_request.duration_ms = request.duration_ms

            future = client.call_async(device_request)
            deadline = time.monotonic() + self._device_command_timeout_sec
            while not future.done() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not future.done():
                future.cancel()
                return _make_timeout_result(
                    f"firmware motion service for '{device_id}' timed out"
                )
            try:
                device_response = future.result()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                return _make_transport_result(
                    f"firmware motion service for '{device_id}' failed: {exc}"
                )
            return _result_from_ros(device_response.result)

        def _handle_list_events(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            if _reject_external_safety_priority(meta, response):
                return response
            limit = max(0, min(int(request.limit), 32))
            records = self.event_buffer.records(device_id)
            records = _records_after_event_id(records, getattr(request, "since_event_id", ""))
            records = records[-limit:] if limit else ()
            _copy_result(response.result, Result.completed("events listed"))
            _copy_records(response, self._stackchan_event_type, records)
            response.cursor = _cursor_for(records)
            return response

        def _handle_next_event(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            if _reject_external_safety_priority(meta, response):
                return response
            consumer_id = getattr(request, "consumer_id", "") or meta.source or "stackchanctl"
            after_event_id = getattr(request, "after_event_id", "")
            if after_event_id:
                after_sequence = _sequence_for_event_id(
                    self.event_buffer.records(device_id),
                    after_event_id,
                )
                records = self.event_buffer.read(
                    device_id,
                    consumer_id,
                    limit=1,
                    after_sequence=0 if after_sequence is None else after_sequence,
                )
            else:
                records = self.event_buffer.read(device_id, consumer_id, limit=1)
            _copy_result(response.result, Result.completed("event read"))
            _copy_records(response, self._stackchan_event_type, records)
            response.cursor = _cursor_for(records)
            return response

        def _handle_clear_event_cursor(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            if _reject_external_safety_priority(meta, response):
                return response
            consumer_id = getattr(request, "consumer_id", "") or meta.source or "stackchanctl"
            self.event_buffer.clear_cursor(consumer_id, device_id)
            _copy_result(response.result, Result.completed("event cursor cleared"))
            response.cursor = ""
            return response

        def _handle_get_transcript(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            if _reject_external_safety_priority(meta, response):
                response.utterance_id = getattr(request, "utterance_id", "")
                return response
            utterance_id = getattr(request, "utterance_id", "")
            transcript = self.transcript_store.get(device_id, utterance_id)
            if transcript is None:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "TRANSCRIPT_NOT_FOUND",
                        f"transcript '{utterance_id}' was not found",
                    ),
                )
                response.utterance_id = utterance_id
                response.transcript = ""
                response.confidence = 0.0
                return response
            _copy_result(response.result, Result.completed("transcript found"))
            _copy_transcript(response, transcript)
            return response

        def _handle_get_power_status(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            if _reject_external_safety_priority(meta, response):
                return response
            snapshot, stale = self.power_store.get(device_id)
            if snapshot is None:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "UNSUPPORTED_FEATURE",
                        f"power telemetry for '{device_id}' has not been received",
                    ),
                )
                response.stale = False
                return response
            if stale:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "STALE_TELEMETRY",
                        f"power telemetry for '{device_id}' is stale",
                        recoverable=True,
                    ),
                )
            else:
                _copy_result(response.result, Result.completed("power status found"))
            _copy_power_status(response.status, snapshot)
            response.stale = stale
            return response

        def _handle_get_head_pose(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            if _reject_external_safety_priority(meta, response):
                return response
            status_response = self.facade.get_status(
                meta.device_id,
                command_id=meta.command_id,
            )
            if not status_response.status.connected:
                _copy_result(response.result, status_response.status.last_error)
                response.stale = False
                return response

            snapshot, stale = self.head_pose_store.get(device_id)
            if snapshot is None:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "UNSUPPORTED_FEATURE",
                        f"head pose telemetry for '{device_id}' has not been received",
                    ),
                )
                response.stale = False
                return response
            if stale:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "STALE_TELEMETRY",
                        f"head pose telemetry for '{device_id}' is stale",
                        recoverable=True,
                    ),
                )
            else:
                _copy_result(response.result, Result.completed("head pose found"))
            _copy_head_pose(response.pose, snapshot)
            response.stale = stale
            return response

        def _create_telemetry_relay(
            self,
            device_id: str,
            tail: str,
            message_type: object,
            *,
            public_qos: object,
            device_qos: object,
        ) -> None:
            public_topic = f"/stackchan/{device_id}/{tail}"
            device_topic = f"/stackchan/{device_id}/device/{tail}"
            publisher = self.create_publisher(message_type, public_topic, public_qos)
            self._telemetry_publishers[(device_id, tail)] = publisher
            self._telemetry_subscriptions.append(
                self.create_subscription(
                    message_type,
                    device_topic,
                    lambda message, device_id=device_id, tail=tail, publisher=publisher: self._handle_telemetry(
                        device_id,
                        tail,
                        message,
                        publisher,
                    ),
                    device_qos,
                )
            )

        def _handle_telemetry(
            self,
            device_id: str,
            tail: str,
            message: object,
            publisher: object,
        ) -> None:
            if not _relay_telemetry_message(
                device_id,
                tail,
                message,
                publisher,
                power_store=self.power_store,
                head_pose_store=self.head_pose_store,
                conflict_handler=self._handle_telemetry_device_id_conflict,
            ):
                return

        def _handle_telemetry_device_id_conflict(self, device_id: str, tail: str, message: object) -> None:
            received_device_id = getattr(message, "device_id", "")
            if received_device_id == device_id:
                return
            if received_device_id:
                self.get_logger().warning(
                    f"dropping {tail} telemetry for unexpected device_id={received_device_id!r}"
                )
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="telemetry_device_id_conflict",
                        source="bridge",
                        payload={
                            "topic": tail,
                            "received_device_id": received_device_id,
                        },
                    )
                )

        def _handle_cmd_audio_chunk(self, device_id: str, message: object) -> None:
            if not _coerce_telemetry_device_id(message, device_id):
                self.get_logger().warning(
                    f"dropping playback chunk for unexpected device_id={getattr(message, 'device_id', '')!r}"
                )
                return
            if int(getattr(message, "direction", 0)) != AUDIO_PLAYBACK_DIRECTION:
                self.get_logger().warning("dropping non-playback chunk on command audio ingress")
                return
            command_id = getattr(message, "command_id", "")
            if not command_id:
                self.get_logger().warning("dropping playback chunk without command_id")
                return
            key = (device_id, command_id)
            publish_now = False
            sequence = int(getattr(message, "sequence", 0))
            pcm_size = _audio_chunk_pcm_size(message)
            with self._playback_chunk_lock:
                if key in self._closed_playback_sessions:
                    self.get_logger().warning(
                        f"dropping late playback chunk for command_id={command_id!r}"
                    )
                    return
                stats = self._playback_relay_stats.setdefault(
                    key,
                    {"received": 0, "buffered": 0, "published": 0, "dropped": 0},
                )
                stats["last_received_monotonic"] = time.monotonic()
                stats["received"] += 1
                if key in self._active_playback_sessions:
                    publish_now = True
                    buffer = self._pending_playback_chunks.setdefault(key, [])
                    if len(buffer) >= AUDIO_PLAYBACK_BUFFER_MAX_CHUNKS:
                        stats["dropped"] += 1
                        self.get_logger().warning(
                            f"dropping playback chunk for command_id={command_id!r}: bridge buffer is full"
                        )
                        return
                    buffer.append(message)
                    stats["buffered"] += 1
                else:
                    buffer = self._pending_playback_chunks.setdefault(key, [])
                    if len(buffer) >= AUDIO_PLAYBACK_BUFFER_MAX_CHUNKS:
                        stats["dropped"] += 1
                        self.get_logger().warning(
                            f"dropping playback chunk for command_id={command_id!r}: bridge buffer is full"
                        )
                        return
                    buffer.append(message)
                    stats["buffered"] += 1
                    if stats["buffered"] == 1:
                        self.get_logger().info(
                            "audio playback relay buffered first chunk "
                            f"device_id={device_id!r} command_id={command_id!r} "
                            f"sequence={sequence} bytes={pcm_size} "
                            f"format={int(getattr(message, 'format', 0))} "
                            f"sample_rate={int(getattr(message, 'sample_rate', 0))} "
                            f"channels={int(getattr(message, 'channels', 0))}"
                        )
            if publish_now:
                self._publish_device_audio_chunk(device_id, message)
                return

        def _activate_playback_chunk_relay(self, device_id: str, command_id: str) -> None:
            key = (device_id, command_id)
            with self._playback_chunk_lock:
                self._closed_playback_sessions.discard(key)
                pull_only = key in self._pull_only_playback_sessions
                prebuffered_topic = key in self._prebuffered_topic_playback_sessions
                stats = self._playback_relay_stats.setdefault(
                    key,
                    {"received": 0, "buffered": 0, "published": 0, "dropped": 0},
                )
                if pull_only:
                    self._active_playback_sessions.add(key)
                    stats["activated_monotonic"] = time.monotonic()
                    buffered = list(self._pending_playback_chunks.get(key, []))
                else:
                    buffered = []
            self.get_logger().info(
                "audio playback relay activated "
                f"device_id={device_id!r} command_id={command_id!r} "
                f"buffered={len(buffered)} received={stats['received']} "
                f"pull_only={pull_only}"
            )
            if pull_only:
                return
            self._wait_for_device_audio_playback_subscription(device_id, command_id)
            with self._playback_chunk_lock:
                self._active_playback_sessions.add(key)
                buffered = list(self._pending_playback_chunks.get(key, []))
                stats = self._playback_relay_stats.setdefault(
                    key,
                    {"received": 0, "buffered": 0, "published": 0, "dropped": 0},
                )
                stats["activated_monotonic"] = time.monotonic()
            self.get_logger().info(
                "audio playback relay topic start "
                f"device_id={device_id!r} command_id={command_id!r} "
                f"buffered={len(buffered)} received={stats['received']}"
            )
            publish_window = buffered[: _audio_playback_topic_initial_window_chunks()]
            for index, message in enumerate(publish_window):
                if prebuffered_topic:
                    self._publish_device_audio_chunk_with_retries(device_id, message)
                else:
                    self._publish_device_audio_chunk(device_id, message)
                if index == 0:
                    for _retry_index in range(AUDIO_PLAYBACK_FIRST_CHUNK_RETRY_COUNT - 1):
                        time.sleep(AUDIO_PLAYBACK_FIRST_CHUNK_RETRY_INTERVAL_SEC)
                        self._publish_device_audio_chunk(device_id, message)
                if index < len(publish_window) - 1:
                    time.sleep(AUDIO_PLAYBACK_BUFFERED_PUBLISH_INTERVAL_SEC)

        def _prepare_playback_chunk_relay(self, device_id: str, command_id: str) -> None:
            key = (device_id, command_id)
            with self._playback_chunk_lock:
                self._closed_playback_sessions.discard(key)
                self._active_playback_sessions.add(key)
                stats = self._playback_relay_stats.setdefault(
                    key,
                    {"received": 0, "buffered": 0, "published": 0, "dropped": 0},
                )
                stats["activated_monotonic"] = time.monotonic()
                buffered = len(self._pending_playback_chunks.get(key, []))
            self.get_logger().info(
                "audio playback relay prepared "
                f"device_id={device_id!r} command_id={command_id!r} "
                f"buffered={buffered}"
            )

        def _handle_next_audio_chunk(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            key = (device_id, meta.command_id)
            next_sequence, pull_window_count = _next_audio_chunk_transport_control(
                request
            )
            chunk = None
            republish_chunks = []
            buffered_chunks = 0
            with self._playback_chunk_lock:
                queue = self._pending_playback_chunks.setdefault(key, [])
                chunk, buffered_chunks = _select_playback_chunk_for_pull(
                    queue,
                    next_sequence,
                )
                active = key in self._active_playback_sessions
                closed = key in self._closed_playback_sessions
                pull_only = key in self._pull_only_playback_sessions
                prebuffered_topic = key in self._prebuffered_topic_playback_sessions
                stats = self._playback_relay_stats.setdefault(
                    key,
                    {"received": 0, "buffered": 0, "published": 0, "dropped": 0},
                )
                idle_reference = float(
                    stats.get("last_received_monotonic")
                    or stats.get("activated_monotonic")
                    or 0.0
                )
                if active and chunk is None and buffered_chunks == 0:
                    input_drained = prebuffered_topic
                    input_idle = (
                        not prebuffered_topic
                        and idle_reference > 0.0
                        and time.monotonic() - idle_reference >= AUDIO_PLAYBACK_INPUT_IDLE_EOS_SEC
                    )
                    if input_drained or input_idle:
                        self._active_playback_sessions.discard(key)
                        self._closed_playback_sessions.add(key)
                        active = False
                        closed = True
                        close_reason = "drained" if input_drained else "idle"
                        self.get_logger().info(
                            "audio playback pull closed input "
                            f"device_id={device_id!r} command_id={meta.command_id!r} "
                            f"reason={close_reason} next_sequence={next_sequence}"
                        )
                if active and not pull_only and chunk is not None:
                    nack_counts = stats.setdefault("pull_nack_counts", {})
                    nack_count = int(nack_counts.get(next_sequence, 0))
                    fallback_after_nacks = _audio_playback_pull_service_fallback_after_nacks()
                    if nack_count < fallback_after_nacks:
                        nack_counts[next_sequence] = nack_count + 1
                        republish_chunks = _select_playback_chunks_for_topic_window(
                            queue,
                            next_sequence,
                            pull_window_count,
                        )
                        chunk = None
            if not active and not closed:
                _copy_result(
                    response.result,
                    Result.rejected(
                        "FIRMWARE_BUSY",
                        "audio playback pull requested before session activation",
                        recoverable=True,
                    ),
                )
                response.has_chunk = False
                response.end_of_stream = False
                response.buffered_chunks = buffered_chunks
                _set_optional_field(response, "should_publish_window", False)
                _set_optional_field(response, "publish_from_sequence", next_sequence)
                _set_optional_field(response, "publish_window_chunks", 0)
                return response
            _copy_result(response.result, Result.accepted("audio playback chunk pull ok"))
            response.has_chunk = chunk is not None
            response.end_of_stream = closed and chunk is None and buffered_chunks == 0
            response.buffered_chunks = buffered_chunks
            _set_optional_field(response, "should_publish_window", bool(republish_chunks))
            _set_optional_field(response, "publish_from_sequence", next_sequence)
            _set_optional_field(response, "publish_window_chunks", len(republish_chunks))
            if chunk is not None:
                self._copy_audio_chunk_response(response.chunk, chunk)
                if next_sequence == 0:
                    self.get_logger().info(
                        "audio playback pull served first chunk "
                        f"device_id={device_id!r} command_id={meta.command_id!r} "
                        f"bytes={_audio_chunk_pcm_size(chunk)} buffered={buffered_chunks}"
                    )
                elif active and not pull_only:
                    self.get_logger().info(
                        "audio playback pull served fallback chunk "
                        f"device_id={device_id!r} command_id={meta.command_id!r} "
                        f"sequence={_playback_chunk_sequence(chunk)} "
                        f"bytes={_audio_chunk_pcm_size(chunk)} buffered={buffered_chunks}"
                    )
                    self._republish_device_audio_chunk_for_pull_async(device_id, chunk)
            elif republish_chunks:
                republish_chunk = republish_chunks[0]
                self.get_logger().info(
                    "audio playback pull republished chunk on topic "
                    f"device_id={device_id!r} command_id={meta.command_id!r} "
                    f"sequence={_playback_chunk_sequence(republish_chunk)} "
                    f"bytes={_audio_chunk_pcm_size(republish_chunk)} "
                    f"buffered={buffered_chunks} lookahead={len(republish_chunks)}"
                )
                self._republish_device_audio_chunk_for_pull(device_id, republish_chunk)
                for lookahead_chunk in republish_chunks[1:]:
                    self._publish_device_audio_chunk(device_id, lookahead_chunk)
            return response

        def _handle_audio_playback_ack(
            self,
            device_id: str,
            message: object,
        ) -> None:
            if getattr(message, "device_id", "") not in ("", device_id):
                self.get_logger().warning(
                    "dropping audio playback ack for unexpected "
                    f"device_id={getattr(message, 'device_id', '')!r}"
                )
                return
            command_id = getattr(message, "command_id", "")
            if not command_id:
                return
            key = (device_id, command_id)
            next_sequence, window_count = _next_audio_chunk_transport_control(message)
            if window_count <= 0:
                return
            republish_chunks = []
            buffered_chunks = 0
            now = time.monotonic()
            with self._playback_chunk_lock:
                active = key in self._active_playback_sessions
                pull_only = key in self._pull_only_playback_sessions
                if not active or pull_only:
                    return
                queue = self._pending_playback_chunks.setdefault(key, [])
                republish_chunks = _select_playback_chunks_for_topic_window(
                    queue,
                    next_sequence,
                    window_count,
                )
                buffered_chunks = len(queue)
                if not republish_chunks:
                    return
                stats = self._playback_relay_stats.setdefault(
                    key,
                    {"received": 0, "buffered": 0, "published": 0, "dropped": 0},
                )
                if not _should_republish_audio_window_for_ack(
                    stats,
                    next_sequence,
                    window_count,
                    now,
                    _audio_playback_ack_republish_min_interval_sec(),
                ):
                    return
            self.get_logger().info(
                "audio playback ack republished topic window "
                f"device_id={device_id!r} command_id={command_id!r} "
                f"sequence={_playback_chunk_sequence(republish_chunks[0])} "
                f"buffered={buffered_chunks} lookahead={len(republish_chunks)}"
            )
            self._publish_device_audio_window_for_ack_async(device_id, republish_chunks)

        def _copy_audio_chunk_response(self, target: object, source: object) -> None:
            target.device_id = getattr(source, "device_id", "")
            target.command_id = getattr(source, "command_id", "")
            target.direction = int(getattr(source, "direction", 0))
            target.sequence = int(getattr(source, "sequence", 0))
            _set_optional_field(target, "total_chunks", int(getattr(source, "total_chunks", 0)))
            _set_optional_field(target, "total_bytes", int(getattr(source, "total_bytes", 0)))
            target.format = int(getattr(source, "format", 0))
            target.sample_rate = int(getattr(source, "sample_rate", 0))
            target.channels = int(getattr(source, "channels", 0))
            _set_optional_field(
                target,
                "end_of_stream",
                bool(getattr(source, "end_of_stream", False)),
            )
            target.pcm = bytes(getattr(source, "pcm", b""))

        def _buffer_synthesized_playback_chunks(
            self,
            device_id: str,
            meta: CommandMeta,
            audio: TtsAudio,
            *,
            start_sequence: int = 0,
            pcm_offset: int = 0,
            pull_only: bool = False,
        ) -> None:
            if pull_only:
                key = (device_id, meta.command_id)
                with self._playback_chunk_lock:
                    self._pull_only_playback_sessions.add(key)
            else:
                key = (device_id, meta.command_id)
                with self._playback_chunk_lock:
                    self._prebuffered_topic_playback_sessions.add(key)
            chunk_bytes = _audio_playback_chunk_bytes()
            for sequence, start in enumerate(
                range(pcm_offset, len(audio.pcm), chunk_bytes),
                start=start_sequence,
            ):
                message = self._audio_chunk_type()
                message.device_id = device_id
                message.command_id = meta.command_id
                message.direction = AUDIO_PLAYBACK_DIRECTION
                message.sequence = sequence
                _set_optional_field(message, "total_chunks", 0)
                _set_optional_field(message, "total_bytes", 0)
                message.format = AUDIO_CHUNK_FORMAT_ID
                message.sample_rate = audio.sample_rate
                message.channels = audio.channels
                _set_optional_field(message, "end_of_stream", False)
                message.pcm = audio.pcm[start : start + chunk_bytes]
                self._handle_cmd_audio_chunk(device_id, message)

        def _tts_playback_request(
            self,
            ros_meta: object,
            request: object,
            audio: TtsAudio,
        ) -> object:
            first_goal_bytes = min(_audio_playback_first_goal_bytes(), len(audio.pcm))
            if first_goal_bytes % 2:
                first_goal_bytes -= 1
            first_chunk = audio.pcm[:first_goal_bytes]
            return SimpleNamespace(
                meta=ros_meta,
                format=AUDIO_FORMAT,
                sample_rate=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS,
                first_chunk_present=bool(first_chunk),
                first_chunk_sequence=0,
                first_chunk_pcm=first_chunk,
                face_hint=getattr(request, "face_hint", ""),
                motion_hint=getattr(request, "motion_hint", ""),
                next_chunk_offset=first_goal_bytes,
                next_chunk_sequence=1 if first_chunk else 0,
            )

        def _loaded_tts_playback_request(
            self,
            ros_meta: object,
            request: object,
        ) -> object:
            return SimpleNamespace(
                meta=ros_meta,
                format=AUDIO_FORMAT,
                sample_rate=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS,
                first_chunk_present=False,
                first_chunk_sequence=0,
                first_chunk_pcm=b"",
                face_hint=getattr(request, "face_hint", ""),
                motion_hint=getattr(request, "motion_hint", ""),
                next_chunk_offset=0,
                next_chunk_sequence=0,
                loaded_playback=True,
            )

        def _try_load_command_audio_playback(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> tuple[object, Result | None]:
            key = (device_id, meta.command_id)
            deadline = time.monotonic() + AUDIO_PLAYBACK_COMMAND_PRELOAD_WAIT_SEC
            last_state = "incomplete"
            while True:
                with self._playback_chunk_lock:
                    chunks = list(self._pending_playback_chunks.get(key, []))
                audio, state = _command_playback_audio_from_complete_chunks(
                    request,
                    chunks,
                    max_decoded_bytes=_audio_playback_command_loaded_max_decoded_bytes(),
                )
                last_state = state
                if state == "too_large":
                    self.get_logger().info(
                        "audio playback command payload too large for loaded playback; "
                        "using streaming relay "
                        f"device_id={device_id!r} command_id={meta.command_id!r}"
                    )
                    return request, None
                if audio is not None:
                    loaded_result = self._load_device_audio_playback(
                        device_id,
                        meta,
                        request.meta,
                        audio,
                    )
                    if loaded_result is not None and loaded_result.ok:
                        self._finish_playback_chunk_relay(device_id, meta.command_id)
                        self.get_logger().info(
                            "audio playback command loaded before play action "
                            f"device_id={device_id!r} command_id={meta.command_id!r} "
                            f"bytes={len(audio.pcm)}"
                        )
                        return self._loaded_tts_playback_request(request.meta, request), None
                    if (
                        loaded_result is not None
                        and not loaded_result.ok
                        and loaded_result.error_code != "UNSUPPORTED_FEATURE"
                    ):
                        return request, loaded_result
                    self.get_logger().info(
                        "audio playback command loaded path unavailable; "
                        "using streaming relay "
                        f"device_id={device_id!r} command_id={meta.command_id!r} "
                        f"state={state!r}"
                    )
                    return request, None
                if time.monotonic() >= deadline:
                    if chunks:
                        self.get_logger().info(
                            "audio playback command preload window expired; "
                            "using streaming relay "
                            f"device_id={device_id!r} command_id={meta.command_id!r} "
                            f"chunks={len(chunks)} state={last_state!r}"
                        )
                    return request, None
                time.sleep(0.02)

        def _loaded_playback_completion_result(
            self,
            device_id: str,
            command_id: str,
        ) -> Result | None:
            return _loaded_playback_completion_from_events(
                self.event_buffer.records(device_id),
                command_id,
            )

        def _load_device_audio_playback(
            self,
            device_id: str,
            meta: CommandMeta,
            ros_meta: object,
            audio: TtsAudio,
        ) -> Result | None:
            if _audio_playback_loaded_transport() == "topic":
                return self._publish_loaded_audio_playback(
                    device_id,
                    meta,
                    audio,
                )
            client = self._device_audio_load_clients.get(device_id)
            if client is None or not client.wait_for_service(timeout_sec=0.1):
                self.get_logger().info(
                    "audio playback load service unavailable; falling back to topic relay "
                    f"device_id={device_id!r} command_id={meta.command_id!r}"
                )
                return None
            candidates = _loaded_audio_transfer_candidates(audio)
            for index, candidate in enumerate(candidates):
                result = self._load_device_audio_playback_payload(
                    device_id,
                    meta,
                    ros_meta,
                    audio,
                    candidate,
                    client,
                )
                if result.ok or result.error_code != "UNSUPPORTED_FEATURE":
                    return result
                if index + 1 < len(candidates):
                    self.get_logger().info(
                        "audio playback compressed load unsupported; falling back to PCM "
                        f"device_id={device_id!r} command_id={meta.command_id!r} "
                        f"format_id={candidate.format_id} error_code={result.error_code!r}"
                    )
            return Result.rejected(
                "UNSUPPORTED_FEATURE",
                "firmware rejected all loaded audio formats",
                recoverable=True,
            )

        def _publish_loaded_audio_playback(
            self,
            device_id: str,
            meta: CommandMeta,
            audio: TtsAudio,
        ) -> Result:
            publisher = self._device_audio_chunk_publishers.get(device_id)
            if publisher is None:
                return _make_transport_result(
                    f"firmware audio playback chunk topic for '{device_id}' is unavailable"
                )
            self._wait_for_device_audio_playback_subscription(device_id, meta.command_id)
            candidate = _loaded_audio_transfer_candidates(audio)[0]
            chunk_bytes = _audio_playback_load_chunk_bytes_for_format(candidate.format_id)
            total_chunks = (len(candidate.payload) + chunk_bytes - 1) // chunk_bytes
            publish_interval_sec = _audio_playback_loaded_topic_publish_interval_sec()
            window_chunks = _audio_playback_loaded_topic_window_chunks()
            progress_timeout_sec = _audio_playback_loaded_topic_progress_timeout_sec()
            progress_retries = _audio_playback_loaded_topic_progress_retries()
            publish_started_at = time.monotonic()
            for sequence, start in enumerate(range(0, len(candidate.payload), chunk_bytes)):
                message = self._audio_chunk_type()
                message.device_id = device_id
                message.command_id = meta.command_id
                message.direction = AUDIO_PLAYBACK_DIRECTION
                message.sequence = sequence
                _set_optional_field(message, "total_chunks", total_chunks)
                _set_optional_field(message, "total_bytes", candidate.decoded_bytes)
                message.format = candidate.format_id
                message.sample_rate = audio.sample_rate
                message.channels = audio.channels
                _set_optional_field(message, "end_of_stream", sequence + 1 >= total_chunks)
                message.pcm = candidate.payload[start : start + chunk_bytes]
                self._publish_device_audio_chunk(device_id, message)
                should_wait_for_progress = (
                    sequence + 1 >= total_chunks
                    or (sequence + 1) % window_chunks == 0
                )
                if should_wait_for_progress and progress_timeout_sec > 0:
                    progress_result = None
                    for retry_index in range(progress_retries + 1):
                        progress_result = self._wait_for_loaded_audio_topic_progress(
                            device_id,
                            meta.command_id,
                            min_buffered_chunks=sequence + 1,
                            timeout_sec=progress_timeout_sec,
                        )
                        if progress_result is None:
                            break
                        if (
                            progress_result.error_code != "TIMEOUT"
                            or retry_index >= progress_retries
                        ):
                            break
                        self.get_logger().warning(
                            "audio playback loaded topic progress timeout; "
                            "republishing chunk "
                            f"device_id={device_id!r} "
                            f"command_id={meta.command_id!r} "
                            f"sequence={sequence} "
                            f"min_buffered_chunks={sequence + 1} "
                            f"retry={retry_index + 1}/{progress_retries}"
                        )
                        self._publish_device_audio_chunk(device_id, message)
                    if progress_result is not None:
                        return progress_result
                if publish_interval_sec > 0 and sequence + 1 < total_chunks:
                    time.sleep(publish_interval_sec)
            publish_finished_at = time.monotonic()
            self.get_logger().info(
                "audio playback loaded topic publish complete "
                f"device_id={device_id!r} command_id={meta.command_id!r} "
                f"format_id={candidate.format_id} chunks={total_chunks} "
                f"encoded_bytes={len(candidate.payload)} "
                f"decoded_bytes={candidate.decoded_bytes} chunk_bytes={chunk_bytes} "
                f"publish_elapsed_ms={int((publish_finished_at - publish_started_at) * 1000)} "
                f"publish_interval_ms={int(publish_interval_sec * 1000)}"
            )
            settle_sec = _audio_playback_loaded_topic_settle_sec()
            if settle_sec > 0:
                time.sleep(settle_sec)
            complete_result = self._wait_for_loaded_audio_topic_complete(
                device_id,
                meta.command_id,
                timeout_sec=_audio_playback_loaded_topic_complete_timeout_sec(),
            )
            if complete_result is not None:
                return complete_result
            self.get_logger().info(
                "audio playback loaded over topic before play action "
                f"device_id={device_id!r} command_id={meta.command_id!r} "
                f"format_id={candidate.format_id} chunks={total_chunks} "
                f"encoded_bytes={len(candidate.payload)} "
                f"decoded_bytes={candidate.decoded_bytes} chunk_bytes={chunk_bytes} "
                f"window_chunks={window_chunks} "
                f"progress_timeout_ms={int(progress_timeout_sec * 1000)} "
                f"progress_retries={progress_retries} "
                f"publish_interval_ms={int(publish_interval_sec * 1000)} "
                f"settle_ms={int(settle_sec * 1000)}"
            )
            return Result.accepted("audio playback loaded over topic")

        def _wait_for_loaded_audio_topic_progress(
            self,
            device_id: str,
            command_id: str,
            *,
            min_buffered_chunks: int,
            timeout_sec: float,
        ) -> Result | None:
            if timeout_sec <= 0:
                return None
            deadline = time.monotonic() + timeout_sec
            while time.monotonic() < deadline:
                records = tuple(
                    record
                    for record in self.event_buffer.records(device_id)
                    if record.command_id == command_id
                    and record.event_name == "audio_playback_load"
                )
                for record in records:
                    payload = dict(record.payload)
                    if payload.get("stage") != "topic":
                        continue
                    error_code = _loaded_audio_topic_error_code(payload)
                    if error_code:
                        detail = str(payload.get("detail") or "")
                        return Result.rejected(
                            error_code,
                            "firmware rejected loaded audio topic payload"
                            + (f" ({detail})" if detail else ""),
                            recoverable=True,
                        )
                    if _loaded_audio_topic_buffered_chunks(payload) >= min_buffered_chunks:
                        return None
                    if bool(payload.get("complete", False)):
                        return None
                time.sleep(0.02)
            return _make_timeout_result(
                f"firmware audio playback topic load progress for '{device_id}' "
                f"timed out at {min_buffered_chunks} chunks"
            )

        def _wait_for_loaded_audio_topic_complete(
            self,
            device_id: str,
            command_id: str,
            *,
            timeout_sec: float,
        ) -> Result | None:
            if timeout_sec <= 0:
                return None
            deadline = time.monotonic() + timeout_sec
            while time.monotonic() < deadline:
                records = tuple(
                    record
                    for record in self.event_buffer.records(device_id)
                    if record.command_id == command_id
                    and record.event_name == "audio_playback_load"
                )
                for record in records:
                    payload = dict(record.payload)
                    if payload.get("stage") != "topic":
                        continue
                    error_code = _loaded_audio_topic_error_code(payload)
                    if error_code:
                        detail = str(payload.get("detail") or "")
                        return Result.rejected(
                            error_code,
                            "firmware rejected loaded audio topic payload"
                            + (f" ({detail})" if detail else ""),
                            recoverable=True,
                        )
                    if bool(payload.get("complete", False)):
                        self.get_logger().info(
                            "audio playback loaded topic complete "
                            f"device_id={device_id!r} command_id={command_id!r} "
                            f"sequence={payload.get('seq')} "
                            f"buffered_bytes={payload.get('buf')} "
                            f"chunks={payload.get('chunks')}"
                        )
                        return None
                time.sleep(0.05)
            return _make_timeout_result(
                f"firmware audio playback topic load for '{device_id}' timed out"
            )

        def _load_device_audio_playback_payload(
            self,
            device_id: str,
            meta: CommandMeta,
            ros_meta: object,
            audio: TtsAudio,
            candidate: EncodedAudioPayload,
            client: object,
        ) -> Result:
            chunk_bytes = _audio_playback_load_chunk_bytes_for_format(candidate.format_id)
            total_chunks = (len(candidate.payload) + chunk_bytes - 1) // chunk_bytes
            for sequence, start in enumerate(range(0, len(candidate.payload), chunk_bytes)):
                chunk = candidate.payload[start : start + chunk_bytes]
                device_request = LoadAudioChunk.Request()
                _copy_command_meta(
                    device_request.meta,
                    meta,
                    getattr(ros_meta, "created_at", device_request.meta.created_at),
                )
                device_request.sequence = sequence
                device_request.total_chunks = total_chunks
                device_request.total_bytes = candidate.decoded_bytes
                device_request.format = candidate.format_id
                device_request.sample_rate = audio.sample_rate
                device_request.channels = audio.channels
                device_request.end_of_stream = sequence + 1 >= total_chunks
                device_request.pcm = chunk
                started = time.monotonic()
                self.get_logger().info(
                    "audio playback load chunk request "
                    f"device_id={device_id!r} command_id={meta.command_id!r} "
                    f"format_id={candidate.format_id} "
                    f"sequence={sequence} total_chunks={total_chunks} "
                    f"bytes={len(chunk)} encoded_bytes={len(candidate.payload)} "
                    f"decoded_bytes={candidate.decoded_bytes} "
                    f"end_of_stream={device_request.end_of_stream}"
                )
                future = client.call_async(device_request)
                wait_result = self._wait_for_future(
                    future,
                    f"audio playback load service for '{device_id}'",
                    timeout_sec=self._device_media_action_timeout_sec,
                )
                if wait_result is not None:
                    self.get_logger().warning(
                        "audio playback load chunk timeout "
                        f"device_id={device_id!r} command_id={meta.command_id!r} "
                        f"format_id={candidate.format_id} "
                        f"sequence={sequence} total_chunks={total_chunks} "
                        f"bytes={len(chunk)} elapsed_ms="
                        f"{int((time.monotonic() - started) * 1000)} "
                        f"error_code={wait_result.error_code!r}"
                    )
                    return wait_result
                try:
                    response = future.result()
                except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                    return _make_transport_result(
                        f"firmware audio playback load service for '{device_id}' failed: {exc}"
                    )
                result = _result_from_ros(response.result)
                self.get_logger().info(
                    "audio playback load chunk response "
                    f"device_id={device_id!r} command_id={meta.command_id!r} "
                    f"format_id={candidate.format_id} "
                    f"sequence={sequence} accepted_sequence={response.accepted_sequence} "
                    f"buffered_chunks={response.buffered_chunks} "
                    f"buffered_bytes={response.buffered_bytes} "
                    f"complete={response.complete} ok={result.ok} "
                    f"error_code={result.error_code!r} elapsed_ms="
                    f"{int((time.monotonic() - started) * 1000)}"
                )
                if not result.ok:
                    return result
            self.get_logger().info(
                "audio playback loaded before play action "
                f"device_id={device_id!r} command_id={meta.command_id!r} "
                f"format_id={candidate.format_id} chunks={total_chunks} "
                f"encoded_bytes={len(candidate.payload)} "
                f"decoded_bytes={candidate.decoded_bytes} chunk_bytes={chunk_bytes}"
            )
            return Result.accepted("audio playback loaded")

        def _wait_for_device_audio_playback_subscription(
            self,
            device_id: str,
            command_id: str,
        ) -> None:
            publisher = self._device_audio_chunk_publishers.get(device_id)
            if publisher is None or not hasattr(publisher, "get_subscription_count"):
                return
            deadline = time.monotonic() + AUDIO_PLAYBACK_SUBSCRIPTION_MATCH_TIMEOUT_SEC
            match_count = int(publisher.get_subscription_count())
            while match_count <= 0 and time.monotonic() < deadline:
                time.sleep(AUDIO_PLAYBACK_SUBSCRIPTION_MATCH_INTERVAL_SEC)
                match_count = int(publisher.get_subscription_count())
            self.get_logger().info(
                "audio playback relay subscription match "
                f"device_id={device_id!r} command_id={command_id!r} "
                f"subscriptions={match_count}"
            )

        def _finish_playback_chunk_relay(self, device_id: str, command_id: str) -> None:
            key = (device_id, command_id)
            with self._playback_chunk_lock:
                self._active_playback_sessions.discard(key)
                self._pull_only_playback_sessions.discard(key)
                self._prebuffered_topic_playback_sessions.discard(key)
                pending = self._pending_playback_chunks.pop(key, [])
                self._closed_playback_sessions.add(key)
                stats = self._playback_relay_stats.pop(
                    key,
                    {"received": 0, "buffered": 0, "published": 0, "dropped": 0},
                )
            self.get_logger().info(
                "audio playback relay finished "
                f"device_id={device_id!r} command_id={command_id!r} "
                f"received={stats['received']} buffered={stats['buffered']} "
                f"published={stats['published']} dropped={stats['dropped']} "
                f"pending={len(pending)}"
            )

        def _publish_device_audio_chunk(self, device_id: str, message: object) -> None:
            publisher = self._device_audio_chunk_publishers.get(device_id)
            command_id = getattr(message, "command_id", "")
            key = (device_id, command_id)
            sequence = int(getattr(message, "sequence", 0))
            pcm_size = _audio_chunk_pcm_size(message)
            if publisher is None:
                with self._playback_chunk_lock:
                    stats = self._playback_relay_stats.setdefault(
                        key,
                        {"received": 0, "buffered": 0, "published": 0, "dropped": 0},
                    )
                    stats["dropped"] += 1
                self.get_logger().warning(
                    f"dropping playback chunk for unconfigured device_id={device_id!r}"
                )
                return
            with self._playback_chunk_lock:
                stats = self._playback_relay_stats.setdefault(
                    key,
                    {"received": 0, "buffered": 0, "published": 0, "dropped": 0},
                )
                stats["published"] += 1
                published_count = stats["published"]
            if published_count == 1:
                self.get_logger().info(
                    "audio playback relay published first chunk "
                    f"device_id={device_id!r} command_id={command_id!r} "
                    f"sequence={sequence} bytes={pcm_size}"
                )
            publisher.publish(message)

        def _publish_device_audio_chunk_with_retries(
            self, device_id: str, message: object
        ) -> None:
            for retry_index in range(AUDIO_PLAYBACK_TOPIC_CHUNK_RETRY_COUNT):
                self._publish_device_audio_chunk(device_id, message)
                if retry_index < AUDIO_PLAYBACK_TOPIC_CHUNK_RETRY_COUNT - 1:
                    time.sleep(AUDIO_PLAYBACK_TOPIC_CHUNK_RETRY_INTERVAL_SEC)

        def _republish_device_audio_chunk_for_pull(
            self, device_id: str, message: object
        ) -> None:
            for retry_index in range(AUDIO_PLAYBACK_PULL_REPUBLISH_RETRY_COUNT):
                self._publish_device_audio_chunk(device_id, message)
                if retry_index < AUDIO_PLAYBACK_PULL_REPUBLISH_RETRY_COUNT - 1:
                    time.sleep(AUDIO_PLAYBACK_PULL_REPUBLISH_RETRY_INTERVAL_SEC)

        def _republish_device_audio_chunk_for_pull_async(
            self, device_id: str, message: object
        ) -> None:
            threading.Thread(
                target=self._republish_device_audio_chunk_for_pull,
                args=(device_id, message),
                daemon=True,
            ).start()

        def _publish_device_audio_window_for_ack(
            self, device_id: str, messages: list[object]
        ) -> None:
            first_chunk_retry_count = _audio_playback_ack_first_chunk_retry_count()
            for index, message in enumerate(messages):
                repeat_count = first_chunk_retry_count if index == 0 else 1
                for retry_index in range(repeat_count):
                    self._publish_device_audio_chunk(device_id, message)
                    if retry_index < repeat_count - 1:
                        time.sleep(AUDIO_PLAYBACK_PULL_REPUBLISH_RETRY_INTERVAL_SEC)
                if index < len(messages) - 1:
                    time.sleep(AUDIO_PLAYBACK_TOPIC_CHUNK_RETRY_INTERVAL_SEC)

        def _publish_device_audio_window_for_ack_async(
            self, device_id: str, messages: list[object]
        ) -> None:
            threading.Thread(
                target=self._publish_device_audio_window_for_ack,
                args=(device_id, list(messages)),
                daemon=True,
            ).start()

        def _handle_speech_audio_chunk(self, device_id: str, message: object) -> None:
            if not _coerce_telemetry_device_id(message, device_id):
                self.get_logger().warning(
                    f"dropping audio chunk for unexpected device_id={getattr(message, 'device_id', '')!r}"
                )
                return
            chunk = AudioChunk(
                device_id=getattr(message, "device_id", "") or device_id,
                command_id=getattr(message, "command_id", ""),
                direction=int(getattr(message, "direction", 0)),
                sequence=int(getattr(message, "sequence", 0)),
                format=int(getattr(message, "format", 0)),
                sample_rate=int(getattr(message, "sample_rate", 0)),
                channels=int(getattr(message, "channels", 0)),
                pcm=bytes(getattr(message, "pcm", b"")),
            )
            self.speech_processor.handle_audio_chunk(chunk)

        def _handle_speech_event(self, event: SpeechEvent) -> None:
            record = self.event_aggregator.add(
                event.device_id,
                event.event_name,
                command_id=event.command_id,
                source=event.source,
                payload=event.payload,
            )
            if record is None:
                return
            self._publish_event_record(record)

        def _publish_event_record(self, record: EventRecord) -> None:
            publisher = self._public_event_publishers.get(record.device_id)
            if publisher is None:
                return
            public_event = self._stackchan_event_type()
            _copy_event_record(public_event, record)
            publisher.publish(public_event)

        def _publish_status(self, device_id: str) -> None:
            publisher = self._public_status_publishers.get(device_id)
            if publisher is None:
                return
            status_response = self.facade.get_status(device_id)
            public_status = self._stackchan_status_type()
            _copy_status_with_type(
                public_status,
                status_response.status,
                self._capability_status_type,
            )
            publisher.publish(public_status)

        def _handle_device_status(self, device_id: str, status: object) -> None:
            if not _status_matches_device_id(device_id, status):
                self.get_logger().warning(
                    f"dropping firmware status for unexpected device_id={getattr(status, 'device_id', '')!r}"
                )
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="device_conflict_detected",
                        source="bridge",
                        payload={
                            "topic": "status",
                            "received_device_id": getattr(status, "device_id", ""),
                        },
                    )
                )
                return
            now = self.get_clock().now().nanoseconds / 1_000_000_000
            self._device_last_seen[device_id] = now
            became_available = _mark_device_available_from_status(
                self.facade.registry,
                device_id,
                status,
            )
            snapshot = _snapshot_from_stackchan_status(
                status,
                fallback_device_id=device_id,
            )
            released_media_action = self._media_action_gate.release_if_capability_idle(
                device_id,
                snapshot.capabilities,
            )
            if released_media_action is not None:
                self.get_logger().info(
                    "firmware media action gate released from idle status "
                    f"device_id={device_id!r} "
                    f"command_id={released_media_action.command_id!r} "
                    f"label={released_media_action.label!r} "
                    f"capability={released_media_action.capability!r} "
                    f"age_ms={int(released_media_action.age_sec * 1000)}"
                )
                if released_media_action.label == "audio playback":
                    self._finish_playback_chunk_relay(
                        device_id,
                        released_media_action.command_id,
                    )
            self.facade.update_status(snapshot)
            if became_available:
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="device_connected",
                        source="bridge",
                        payload={"reason": "firmware_status"},
                    )
                )
            self._publish_status(device_id)

        def _expire_stale_devices(self) -> None:
            if self._liveness_timeout_sec <= 0:
                return
            now = self.get_clock().now().nanoseconds / 1_000_000_000
            for device_id, last_seen in tuple(self._device_last_seen.items()):
                if now - last_seen <= self._liveness_timeout_sec:
                    continue
                if self.facade.registry.availability(device_id) != DeviceAvailability.AVAILABLE:
                    continue
                self.facade.registry.set_connected(device_id, False)
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="device_disconnected",
                        source="bridge",
                        payload={
                            "reason": "liveness_timeout",
                            "timeout_sec": self._liveness_timeout_sec,
                        },
                    )
                )
                self._publish_status(device_id)
            for device_id in self.facade.registry.device_ids():
                self._publish_status(device_id)

        def _handle_device_event(self, device_id: str, event: object) -> None:
            if not _event_matches_device_id(device_id, event):
                self.get_logger().warning(
                    f"dropping firmware event for unexpected device_id={getattr(event, 'device_id', '')!r}"
                )
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="device_conflict_detected",
                        source="bridge",
                        payload={
                            "topic": "events",
                            "received_device_id": getattr(event, "device_id", ""),
                        },
                    )
                )
                return
            became_available = _mark_device_available_from_event(
                self.facade.registry,
                device_id,
                event,
            )
            if became_available:
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="device_connected",
                        source="bridge",
                        payload={"reason": "firmware_event"},
                    )
                )
            payload_json = getattr(event, "payload_json", "")
            record = self.event_aggregator.add(
                device_id,
                getattr(event, "event_name", ""),
                command_id=getattr(event, "command_id", ""),
                source=getattr(event, "source", "") or "firmware",
                event_id=getattr(event, "event_id", ""),
                payload=payload_json,
                stamp=_stamp_to_seconds(getattr(event, "stamp", None)),
            )
            if record is None:
                return
            self._publish_event_record(record)

        def _handle_set_led(
            self,
            device_id: str,
            request: object,
            response: object,
        ) -> object:
            meta = _meta_from_ros(request.meta, device_id)
            command_response = self.facade.set_led(
                meta,
                request.pattern,
                request.color,
                request.duration_ms,
            )
            if not command_response.result.ok:
                _copy_result(response.result, command_response.result)
                return response

            device_result = self._call_device_led_set(device_id, request, meta)
            _copy_result(response.result, device_result)
            return response

        def _call_device_led_set(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> Result:
            client = self._device_led_clients.get(device_id)
            if client is None:
                return _make_transport_result(
                    f"firmware LED service for '{device_id}' is not configured"
                )
            if not client.wait_for_service(timeout_sec=0.1):
                return _make_transport_result(
                    f"firmware LED service for '{device_id}' is unavailable"
                )

            device_request = self._set_led_type.Request()
            _copy_command_meta(
                device_request.meta,
                meta,
                getattr(request.meta, "created_at", device_request.meta.created_at),
            )
            device_request.pattern = request.pattern
            device_request.color = request.color
            device_request.duration_ms = request.duration_ms

            future = client.call_async(device_request)
            deadline = time.monotonic() + self._device_command_timeout_sec
            while not future.done() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not future.done():
                future.cancel()
                return _make_timeout_result(
                    f"firmware LED service for '{device_id}' timed out"
                )
            try:
                device_response = future.result()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                return _make_transport_result(
                    f"firmware LED service for '{device_id}' failed: {exc}"
                )
            return _result_from_ros(device_response.result)

        def _handle_run_motion(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            meta = _meta_from_ros(request.meta, device_id)
            command_response = self.facade.run_motion(
                meta,
                request.name,
                request.intensity,
                request.duration_ms,
            )
            self._publish_status(device_id)
            if command_response.result.ok:
                device_result = self._call_device_motion_run(device_id, request, meta)
                command_response = type(command_response)(
                    command_response.device_id,
                    command_response.command_id,
                    device_result,
                )
            result = RunMotion.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _call_device_head_pose(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> object:
            client = self._device_head_pose_clients.get(device_id)
            response = type("HeadPoseDeviceResponse", (), {})()
            response.result = _make_transport_result(
                f"firmware head pose service for '{device_id}' is not configured"
            )
            response.pose = self._head_pose_type()
            if client is None:
                return response
            if not client.wait_for_service(timeout_sec=0.1):
                response.result = _make_transport_result(
                    f"firmware head pose service for '{device_id}' is unavailable"
                )
                return response

            device_request = self._set_head_pose_type.Request()
            _copy_command_meta(
                device_request.meta,
                meta,
                getattr(request.meta, "created_at", device_request.meta.created_at),
            )
            device_request.home = bool(getattr(request, "home", False))
            device_request.pan_deg = float(getattr(request, "pan_deg", 0.0))
            device_request.tilt_deg = float(getattr(request, "tilt_deg", 0.0))
            device_request.speed = int(getattr(request, "speed", 0))
            device_request.duration_ms = int(getattr(request, "duration_ms", 0))

            future = client.call_async(device_request)
            deadline = time.monotonic() + self._device_command_timeout_sec
            while not future.done() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not future.done():
                future.cancel()
                response.result = _make_timeout_result(
                    f"firmware head pose service for '{device_id}' timed out"
                )
                return response
            try:
                device_response = future.result()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                response.result = _make_transport_result(
                    f"firmware head pose service for '{device_id}' failed: {exc}"
                )
                return response
            response.result = _result_from_ros(device_response.result)
            response.pose = device_response.pose
            return response

        def _handle_move_head_pose(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            meta = _meta_from_ros(request.meta, device_id)
            is_home = bool(getattr(request, "home", False))
            if is_home:
                command_response = self.facade.home_head_pose(
                    meta,
                    int(request.speed),
                    int(request.duration_ms),
                )
            else:
                command_response = self.facade.move_head_pose(
                    meta,
                    float(request.pan_deg),
                    float(request.tilt_deg),
                    int(request.speed),
                    int(request.duration_ms),
                )
            result = MoveHeadPose.Result()
            if command_response.result.ok:
                device_response = self._call_device_head_pose(device_id, request, meta)
                command_response = type(command_response)(
                    command_response.device_id,
                    command_response.command_id,
                    device_response.result,
                )
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                snapshot = _snapshot_from_head_pose(
                    device_response.pose,
                    fallback_device_id=meta.device_id,
                )
                if snapshot.device_id != meta.device_id:
                    _copy_result(
                        result.result,
                        Result.rejected(
                            "DEVICE_ID_CONFLICT",
                            "firmware head pose response device_id does not match target",
                            recoverable=True,
                        ),
                    )
                    goal_handle.abort()
                    return result
                self.head_pose_store.update(snapshot)
                publisher = self._telemetry_publishers.get((device_id, "motion/pose"))
                if publisher is not None:
                    message = self._head_pose_type()
                    _copy_head_pose(message, snapshot)
                    publisher.publish(message)
                _copy_head_pose(result.pose, snapshot)
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _handle_say(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            meta = _meta_from_ros(request.meta, device_id)
            command_response = self.facade.say(
                meta,
                request.text,
                str(getattr(request, "face_hint", "") or "").strip(),
                str(getattr(request, "motion_hint", "") or "").strip(),
                str(getattr(request, "after_face_hint", "") or "").strip(),
            )
            result = Say.Result()
            if not command_response.result.ok:
                _copy_result(result.result, command_response.result)
                goal_handle.abort()
                return result
            if self._tts_provider is None:
                tts_result = Result.rejected(
                    "UNSUPPORTED_FEATURE",
                    "local TTS provider is not configured",
                    recoverable=False,
                )
                _copy_result(result.result, tts_result)
                goal_handle.abort()
                return result
            voice_profile = str(getattr(request, "voice", "") or "").strip()
            if not voice_profile:
                voice_profile = self._tts_default_voice
            self._handle_speech_event(
                SpeechEvent(
                    device_id=device_id,
                    event_name="tts_started",
                    command_id=meta.command_id,
                    source="bridge",
                    payload={
                        "voice_profile": voice_profile,
                        "provider": getattr(self._tts_provider, "provider_kind", "local"),
                    },
                )
            )
            try:
                profile, audio = self._tts_provider.synthesize(
                    str(request.text),
                    voice_profile,
                )
            except TtsProviderError as exc:
                tts_result = Result.rejected(
                    exc.code,
                    str(exc),
                    recoverable=exc.recoverable,
                )
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="tts_failed",
                        command_id=meta.command_id,
                        source="bridge",
                        payload={
                            "voice_profile": voice_profile,
                            "provider": getattr(self._tts_provider, "provider_kind", "local"),
                            "error_code": exc.code,
                        },
                    )
                )
                _copy_result(result.result, tts_result)
                goal_handle.abort()
                return result
            if (
                audio.format != AUDIO_FORMAT
                or audio.sample_rate != AUDIO_SAMPLE_RATE
                or audio.channels != AUDIO_CHANNELS
            ):
                tts_result = Result.rejected(
                    "TTS_AUDIO_UNSUPPORTED",
                    "local TTS provider returned unsupported audio format",
                    recoverable=True,
                )
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="tts_failed",
                        command_id=meta.command_id,
                        source="bridge",
                        payload={
                            "voice_profile": profile.name,
                            "provider": profile.provider,
                            "error_code": tts_result.error_code,
                        },
                    )
                )
                _copy_result(result.result, tts_result)
                goal_handle.abort()
                return result
            playback_request = self._tts_playback_request(request.meta, request, audio)
            loaded_result = None
            if _audio_playback_loaded_tts() and not _audio_playback_pull_only():
                loaded_result = self._load_device_audio_playback(
                    device_id,
                    meta,
                    request.meta,
                    audio,
                )
            if loaded_result is None:
                self._buffer_synthesized_playback_chunks(
                    device_id,
                    meta,
                    audio,
                    start_sequence=int(getattr(playback_request, "next_chunk_sequence", 0)),
                    pcm_offset=int(getattr(playback_request, "next_chunk_offset", 0)),
                    pull_only=_audio_playback_pull_only(),
                )
            elif not loaded_result.ok:
                _copy_result(result.result, loaded_result)
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="tts_failed",
                        command_id=meta.command_id,
                        source="bridge",
                        payload={
                            "voice_profile": profile.name,
                            "provider": profile.provider,
                            "error_code": loaded_result.error_code,
                        },
                    )
                )
                goal_handle.abort()
                return result
            else:
                playback_request = self._loaded_tts_playback_request(request.meta, request)
            face_hint_result = self._run_say_face_hint(device_id, request, meta)
            if face_hint_result is not None and not face_hint_result.ok:
                _copy_result(result.result, face_hint_result)
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="tts_failed",
                        command_id=meta.command_id,
                        source="bridge",
                        payload={
                            "voice_profile": profile.name,
                            "provider": profile.provider,
                            "error_code": face_hint_result.error_code,
                        },
                    )
                )
                goal_handle.abort()
                return result
            motion_hint_result = self._run_say_motion_hint(device_id, request, meta)
            if motion_hint_result is not None and not motion_hint_result.ok:
                _copy_result(result.result, motion_hint_result)
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="tts_failed",
                        command_id=meta.command_id,
                        source="bridge",
                        payload={
                            "voice_profile": profile.name,
                            "provider": profile.provider,
                            "error_code": motion_hint_result.error_code,
                        },
                    )
                )
                goal_handle.abort()
                return result
            playback_result = self._call_device_audio_play(
                device_id,
                playback_request,
                meta,
            )
            after_face_result = self._run_say_after_face(
                device_id,
                request,
                meta,
                playback_ok=playback_result.ok,
            )
            final_result = playback_result
            if playback_result.ok and after_face_result is not None and not after_face_result.ok:
                final_result = after_face_result
            _copy_result(result.result, final_result)
            if final_result.ok:
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="tts_finished",
                        command_id=meta.command_id,
                        source="bridge",
                        payload={
                            "voice_profile": profile.name,
                            "provider": profile.provider,
                            "format": audio.format,
                            "sample_rate": audio.sample_rate,
                            "channels": audio.channels,
                        },
                    )
                )
                goal_handle.succeed()
            else:
                error_code = final_result.error_code
                self._handle_speech_event(
                    SpeechEvent(
                        device_id=device_id,
                        event_name="tts_failed",
                        command_id=meta.command_id,
                        source="bridge",
                        payload={
                            "voice_profile": profile.name,
                            "provider": profile.provider,
                            "error_code": error_code,
                        },
                    )
                )
                goal_handle.abort()
            return result

        def _run_say_face_hint(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> Result | None:
            face_hint = str(getattr(request, "face_hint", "") or "").strip()
            if not face_hint:
                return None
            return self._run_say_face(device_id, request.meta, meta, face_hint)

        def _run_say_after_face(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
            *,
            playback_ok: bool,
        ) -> Result | None:
            after_face = self._resolve_say_after_face(request, playback_ok=playback_ok)
            if not after_face:
                return None
            return self._run_say_face(device_id, request.meta, meta, after_face)

        def _resolve_say_after_face(
            self,
            request: object,
            *,
            playback_ok: bool,
        ) -> str:
            explicit = str(getattr(request, "after_face_hint", "") or "").strip()
            if explicit:
                return explicit
            face_hint = str(getattr(request, "face_hint", "") or "").strip()
            motion_hint = str(getattr(request, "motion_hint", "") or "").strip()
            if not playback_ok:
                return "thinking" if face_hint or motion_hint else ""
            return {
                "happy": "happy",
                "thinking": "thinking",
                "sleepy": "sleepy",
                "surprised": "happy",
                "error": "thinking",
                "neutral": "neutral",
            }.get(face_hint, "")

        def _run_say_face(
            self,
            device_id: str,
            ros_meta: object,
            meta: CommandMeta,
            face_name: str,
        ) -> Result:
            command_response = self.facade.set_face(meta, face_name, 0)
            self._publish_status(device_id)
            if not command_response.result.ok:
                return command_response.result
            device_request = SimpleNamespace(
                meta=ros_meta,
                name=face_name,
                duration_ms=0,
            )
            return self._call_device_face_set(device_id, device_request, meta)

        def _run_say_motion_hint(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> Result | None:
            motion_hint = str(getattr(request, "motion_hint", "") or "").strip()
            if not motion_hint:
                return None
            command_response = self.facade.run_motion(meta, motion_hint, 1.0, 0)
            self._publish_status(device_id)
            if not command_response.result.ok:
                return command_response.result
            device_request = SimpleNamespace(
                meta=request.meta,
                name=motion_hint,
                intensity=1.0,
                duration_ms=0,
            )
            return self._call_device_motion_run(device_id, device_request, meta)

        def _handle_play_audio(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            meta = _meta_from_ros(request.meta, device_id)
            command_response = self.facade.play_audio(
                meta,
                format=request.format,
                sample_rate=int(request.sample_rate),
                channels=int(request.channels),
            )
            if command_response.result.ok:
                device_result = self._call_device_audio_play(device_id, request, meta)
                command_response = type(command_response)(
                    command_response.device_id,
                    command_response.command_id,
                    device_result,
                )
            result = PlayAudio.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _handle_capture_audio(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            meta = _meta_from_ros(request.meta, device_id)
            command_response = self.facade.capture_audio(
                meta,
                format=request.format,
                sample_rate=int(request.sample_rate),
                channels=int(request.channels),
                duration_ms=int(request.duration_ms),
            )
            if command_response.result.ok:
                device_result = self._call_device_audio_capture(device_id, request, meta)
                command_response = type(command_response)(
                    command_response.device_id,
                    command_response.command_id,
                    device_result,
                )
            result = CaptureAudio.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _handle_capture_camera(self, device_id: str, goal_handle: object) -> object:
            request = goal_handle.request
            meta = _meta_from_ros(request.meta, device_id)
            command_response = self.facade.capture_camera(
                meta,
                format=request.format,
                width=int(request.width),
                height=int(request.height),
                quality=int(request.quality),
            )
            if command_response.result.ok:
                device_result = self._call_device_camera_capture(
                    device_id, request, meta
                )
                command_response = type(command_response)(
                    command_response.device_id,
                    command_response.command_id,
                    device_result,
                )
            result = CaptureCamera.Result()
            _copy_result(result.result, command_response.result)
            if command_response.result.ok:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result

        def _begin_device_media_action(
            self,
            device_id: str,
            command_id: str,
            label: str,
        ) -> Result | None:
            result = self._media_action_gate.begin(device_id, command_id, label)
            if result is not None:
                self.get_logger().warning(
                    "firmware media action gate rejected command "
                    f"device_id={device_id!r} command_id={command_id!r} "
                    f"label={label!r} error_code={result.error_code!r} "
                    f"message={result.message!r}"
                )
            return result

        def _finish_device_media_action(
            self,
            device_id: str,
            command_id: str,
            label: str,
            result: Result,
        ) -> None:
            settle_until = self._media_action_gate.finish(
                device_id,
                command_id,
                label,
                result,
            )
            if settle_until <= 0:
                return
            self.get_logger().warning(
                "firmware media action timed out; settling before next media command "
                f"device_id={device_id!r} command_id={command_id!r} "
                f"label={label!r} settle_ms="
                f"{int(max(0.0, settle_until - time.monotonic()) * 1000)}"
            )

        def _log_late_device_action_future(
            self,
            future: object,
            *,
            device_id: str,
            command_id: str,
            label: str,
            phase: str,
        ) -> None:
            def _callback(done_future: object) -> None:
                try:
                    value = done_future.result()
                except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                    self.get_logger().warning(
                        "late firmware media action future failed "
                        f"device_id={device_id!r} command_id={command_id!r} "
                        f"label={label!r} phase={phase!r} error={exc!r}"
                    )
                    return
                accepted = getattr(value, "accepted", None)
                result = getattr(getattr(value, "result", None), "result", None)
                error_code = getattr(result, "error_code", "")
                ok = getattr(result, "ok", None)
                self.get_logger().warning(
                    "late firmware media action future completed "
                    f"device_id={device_id!r} command_id={command_id!r} "
                    f"label={label!r} phase={phase!r} accepted={accepted!r} "
                    f"ok={ok!r} error_code={error_code!r}"
                )

            if hasattr(future, "add_done_callback"):
                future.add_done_callback(_callback)

        def _call_device_camera_capture(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> Result:
            client = self._device_camera_capture_clients.get(device_id)
            if client is None:
                return _make_transport_result(
                    f"firmware camera capture action for '{device_id}' is not configured"
                )
            goal = CaptureCamera.Goal()
            _copy_command_meta(
                goal.meta,
                meta,
                getattr(request.meta, "created_at", goal.meta.created_at),
            )
            goal.format = request.format
            goal.width = int(request.width)
            goal.height = int(request.height)
            goal.quality = int(request.quality)
            label = "camera capture"
            gate_result = self._begin_device_media_action(
                device_id,
                meta.command_id,
                label,
            )
            if gate_result is not None:
                return gate_result
            device_result = _make_transport_result(
                f"firmware camera capture action for '{device_id}' did not complete"
            )
            try:
                device_result = self._send_device_camera_capture_goal(
                    client,
                    goal,
                    f"camera capture action for '{device_id}'",
                    timeout_sec=self._device_media_action_timeout_sec,
                    device_id=device_id,
                    command_id=meta.command_id,
                )
                return device_result
            finally:
                self._finish_device_media_action(
                    device_id,
                    meta.command_id,
                    label,
                    device_result,
                )

        def _call_device_audio_play(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> Result:
            client = self._device_audio_play_clients.get(device_id)
            if client is None:
                return _make_transport_result(
                    f"firmware audio playback action for '{device_id}' is not configured"
                )
            label = "audio playback"
            gate_result = self._begin_device_media_action(
                device_id,
                meta.command_id,
                label,
            )
            if gate_result is not None:
                return gate_result
            if not bool(getattr(request, "loaded_playback", False)):
                request, preload_result = self._try_load_command_audio_playback(
                    device_id,
                    request,
                    meta,
                )
                if preload_result is not None:
                    self._finish_device_media_action(
                        device_id,
                        meta.command_id,
                        label,
                        preload_result,
                    )
                    return preload_result
            loaded_playback = bool(getattr(request, "loaded_playback", False))
            goal = PlayAudio.Goal()
            _copy_command_meta(
                goal.meta,
                meta,
                getattr(request.meta, "created_at", goal.meta.created_at),
            )
            goal.format = request.format
            goal.sample_rate = int(request.sample_rate)
            goal.channels = int(request.channels)
            goal.first_chunk_present = bool(
                getattr(request, "first_chunk_present", False)
            )
            goal.first_chunk_sequence = int(
                getattr(request, "first_chunk_sequence", 0)
            )
            goal.first_chunk_pcm = bytes(getattr(request, "first_chunk_pcm", b""))
            goal.face_hint = getattr(request, "face_hint", "")
            goal.motion_hint = getattr(request, "motion_hint", "")
            device_result = _make_transport_result(
                f"firmware audio playback action for '{device_id}' did not complete"
            )
            try:
                if not loaded_playback:
                    self._prepare_playback_chunk_relay(device_id, meta.command_id)
                if loaded_playback:
                    def accepted_callback() -> None:
                        self._media_action_gate.mark_busy_seen(
                            device_id,
                            meta.command_id,
                        )

                    finished_callback = None

                    def completion_result() -> Result:
                        return self._loaded_playback_completion_result(
                            device_id,
                            meta.command_id,
                        )
                else:
                    def accepted_callback() -> None:
                        self._activate_playback_chunk_relay(
                            device_id,
                            meta.command_id,
                        )

                    def finished_callback() -> None:
                        self._finish_playback_chunk_relay(
                            device_id,
                            meta.command_id,
                        )

                    completion_result = None
                device_result = self._send_device_action_goal(
                    client,
                    goal,
                    f"audio playback action for '{device_id}'",
                    timeout_sec=self._device_media_action_timeout_sec,
                    device_id=device_id,
                    command_id=meta.command_id,
                    on_accepted=accepted_callback,
                    on_finished=finished_callback,
                    completion_result=completion_result,
                )
                if (
                    not loaded_playback
                    and (
                        device_result.state == STATE_TIMEOUT
                        or device_result.error_code == "UNKNOWN_COMMAND"
                    )
                ):
                    self._finish_playback_chunk_relay(device_id, meta.command_id)
                return device_result
            finally:
                self._finish_device_media_action(
                    device_id,
                    meta.command_id,
                    label,
                    device_result,
                )

        def _call_device_audio_capture(
            self,
            device_id: str,
            request: object,
            meta: CommandMeta,
        ) -> Result:
            client = self._device_audio_capture_clients.get(device_id)
            if client is None:
                return _make_transport_result(
                    f"firmware audio capture action for '{device_id}' is not configured"
                )
            goal = CaptureAudio.Goal()
            _copy_command_meta(
                goal.meta,
                meta,
                getattr(request.meta, "created_at", goal.meta.created_at),
            )
            goal.format = request.format
            goal.sample_rate = int(request.sample_rate)
            goal.channels = int(request.channels)
            goal.duration_ms = int(request.duration_ms)
            timeout_sec = max(
                self._device_media_action_timeout_sec,
                (goal.duration_ms / 1000.0) + 2.0,
            )
            label = "audio capture"
            gate_result = self._begin_device_media_action(
                device_id,
                meta.command_id,
                label,
            )
            if gate_result is not None:
                return gate_result
            device_result = _make_transport_result(
                f"firmware audio capture action for '{device_id}' did not complete"
            )
            try:
                device_result = self._send_device_action_goal(
                    client,
                    goal,
                    f"audio capture action for '{device_id}'",
                    timeout_sec=timeout_sec,
                    device_id=device_id,
                    command_id=meta.command_id,
                    cancel_on_result_timeout=True,
                )
                return device_result
            finally:
                self.speech_processor.flush_session(device_id, meta.command_id)
                self._finish_device_media_action(
                    device_id,
                    meta.command_id,
                    label,
                    device_result,
                )

        def _send_device_camera_capture_goal(
            self,
            client: object,
            goal: object,
            label: str,
            *,
            timeout_sec: float | None = None,
            device_id: str = "",
            command_id: str = "",
        ) -> Result:
            if not client.wait_for_server(timeout_sec=0.1):
                return _make_transport_result(f"firmware {label} is unavailable")

            goal_future = client.send_goal_async(goal)
            wait_result = self._wait_for_future(
                goal_future,
                label,
                timeout_sec=timeout_sec,
                cancel_on_timeout=False,
            )
            if wait_result is not None:
                self._log_late_device_action_future(
                    goal_future,
                    device_id=device_id,
                    command_id=command_id,
                    label=label,
                    phase="goal_response",
                )
                return wait_result
            try:
                device_goal_handle = goal_future.result()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                return _make_transport_result(f"firmware {label} failed: {exc}")
            if device_goal_handle is None or not getattr(device_goal_handle, "accepted", False):
                return Result.rejected(
                    "UNKNOWN_COMMAND",
                    f"firmware {label} rejected the goal",
                    recoverable=False,
                )

            result_future = device_goal_handle.get_result_async()
            wait_result = self._wait_for_future(
                result_future,
                label,
                timeout_sec=timeout_sec,
                cancel_on_timeout=False,
            )
            if wait_result is not None:
                self._log_late_device_action_future(
                    result_future,
                    device_id=device_id,
                    command_id=command_id,
                    label=label,
                    phase="result_response",
                )
                return _make_camera_capture_failed_result(f"firmware {label} timed out")
            try:
                result_response = result_future.result()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                return _make_camera_capture_failed_result(
                    f"firmware {label} result failed: {exc}"
                )
            action_result = result_response.result
            return _result_from_ros(action_result.result)

        def _send_device_action_goal(
            self,
            client: object,
            goal: object,
            label: str,
            *,
            timeout_sec: float | None = None,
            device_id: str = "",
            command_id: str = "",
            on_accepted=None,
            on_finished=None,
            completion_result: Callable[[], Result | None] | None = None,
            cancel_on_result_timeout: bool = False,
        ) -> Result:
            if not client.wait_for_server(timeout_sec=0.1):
                return _make_transport_result(f"firmware {label} is unavailable")

            goal_future = client.send_goal_async(goal)
            wait_result = self._wait_for_future(
                goal_future,
                label,
                timeout_sec=timeout_sec,
                cancel_on_timeout=False,
            )
            if wait_result is not None:
                self._log_late_device_action_future(
                    goal_future,
                    device_id=device_id,
                    command_id=command_id,
                    label=label,
                    phase="goal_response",
                )
                return wait_result
            try:
                device_goal_handle = goal_future.result()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                return _make_transport_result(f"firmware {label} failed: {exc}")
            if device_goal_handle is None or not getattr(device_goal_handle, "accepted", False):
                return Result.rejected(
                    "UNKNOWN_COMMAND",
                    f"firmware {label} rejected the goal",
                    recoverable=False,
                )
            if on_accepted is not None:
                on_accepted()

            try:
                result_future = device_goal_handle.get_result_async()
                wait_result = self._wait_for_future(
                    result_future,
                    label,
                    timeout_sec=timeout_sec,
                    cancel_on_timeout=False,
                    completion_result=completion_result,
                )
                if wait_result is not None:
                    if not wait_result.ok:
                        if cancel_on_result_timeout:
                            self._cancel_device_action_goal(
                                device_goal_handle,
                                label,
                                device_id=device_id,
                                command_id=command_id,
                            )
                        self._log_late_device_action_future(
                            result_future,
                            device_id=device_id,
                            command_id=command_id,
                            label=label,
                            phase="result_response",
                        )
                    return wait_result
                try:
                    result_response = result_future.result()
                except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                    return _make_transport_result(f"firmware {label} result failed: {exc}")
                return _result_from_ros(result_response.result.result)
            finally:
                if on_finished is not None:
                    on_finished()

        def _cancel_device_action_goal(
            self,
            device_goal_handle: object,
            label: str,
            *,
            device_id: str,
            command_id: str,
        ) -> None:
            if not hasattr(device_goal_handle, "cancel_goal_async"):
                self.get_logger().warning(
                    "firmware media action goal handle cannot be cancelled "
                    f"device_id={device_id!r} command_id={command_id!r} "
                    f"label={label!r}"
                )
                return
            try:
                cancel_future = device_goal_handle.cancel_goal_async()
            except Exception as exc:  # pragma: no cover - defensive ROS boundary.
                self.get_logger().warning(
                    "firmware media action cancel request failed "
                    f"device_id={device_id!r} command_id={command_id!r} "
                    f"label={label!r} error={exc!r}"
                )
                return
            if cancel_future is None:
                self.get_logger().warning(
                    "firmware media action cancel request returned no future "
                    f"device_id={device_id!r} command_id={command_id!r} "
                    f"label={label!r}"
                )
                return
            wait_result = self._wait_for_future(
                cancel_future,
                f"{label} cancel",
                timeout_sec=1.0,
                cancel_on_timeout=True,
            )
            if wait_result is not None:
                self.get_logger().warning(
                    "firmware media action cancel timed out "
                    f"device_id={device_id!r} command_id={command_id!r} "
                    f"label={label!r}"
                )

        def _wait_for_future(
            self,
            future: object,
            label: str,
            *,
            timeout_sec: float | None = None,
            cancel_on_timeout: bool = True,
            completion_result: Callable[[], Result | None] | None = None,
        ) -> Result | None:
            deadline = time.monotonic() + (
                self._device_command_timeout_sec if timeout_sec is None else timeout_sec
            )
            while not future.done() and time.monotonic() < deadline:
                if completion_result is not None:
                    early_result = completion_result()
                    if early_result is not None:
                        return early_result
                time.sleep(0.01)
            if future.done():
                return None
            if cancel_on_timeout and hasattr(future, "cancel"):
                future.cancel()
            return _make_timeout_result(f"firmware {label} timed out")

    rclpy.init(args=args)
    node = StackChanBridgeNode()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.remove_node(node)
        node.destroy_node()
        rclpy.shutdown()
