"""Small local audio codec helpers for firmware transports."""

from __future__ import annotations

from dataclasses import dataclass
import struct

AUDIO_CHUNK_FORMAT_ID_IMA_ADPCM_4BIT = 2
IMA_ADPCM_HEADER_BYTES = 4

_IMA_INDEX_TABLE = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)
_IMA_STEP_TABLE = (
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    16,
    17,
    19,
    21,
    23,
    25,
    28,
    31,
    34,
    37,
    41,
    45,
    50,
    55,
    60,
    66,
    73,
    80,
    88,
    97,
    107,
    118,
    130,
    143,
    157,
    173,
    190,
    209,
    230,
    253,
    279,
    307,
    337,
    371,
    408,
    449,
    494,
    544,
    598,
    658,
    724,
    796,
    876,
    963,
    1060,
    1166,
    1282,
    1411,
    1552,
    1707,
    1878,
    2066,
    2272,
    2499,
    2749,
    3024,
    3327,
    3660,
    4026,
    4428,
    4871,
    5358,
    5894,
    6484,
    7132,
    7845,
    8630,
    9493,
    10442,
    11487,
    12635,
    13899,
    15289,
    16818,
    18500,
    20350,
    22385,
    24623,
    27086,
    29794,
    32767,
)


@dataclass(frozen=True)
class EncodedAudioPayload:
    payload: bytes
    format_id: int
    decoded_bytes: int
    encoding: str


def encode_ima_adpcm_4bit(pcm: bytes) -> bytes:
    """Encode little-endian s16 PCM into the firmware's IMA ADPCM stream format."""

    if not pcm or len(pcm) % 2:
        raise ValueError("IMA ADPCM input must be non-empty little-endian s16 PCM")
    samples = list(struct.unpack(f"<{len(pcm) // 2}h", pcm))
    predictor = int(samples[0])
    step_index = 0
    output = bytearray(struct.pack("<hBB", predictor, step_index, 0))
    pending_low_nibble: int | None = None
    for sample in samples[1:]:
        nibble, predictor, step_index = _encode_ima_nibble(int(sample), predictor, step_index)
        if pending_low_nibble is None:
            pending_low_nibble = nibble
        else:
            output.append(pending_low_nibble | (nibble << 4))
            pending_low_nibble = None
    if pending_low_nibble is not None:
        output.append(pending_low_nibble)
    return bytes(output)


def _encode_ima_nibble(sample: int, predictor: int, step_index: int) -> tuple[int, int, int]:
    step = _IMA_STEP_TABLE[step_index]
    diff = sample - predictor
    nibble = 0
    if diff < 0:
        nibble = 8
        diff = -diff
    delta = step
    if diff >= delta:
        nibble |= 4
        diff -= delta
    delta >>= 1
    if diff >= delta:
        nibble |= 2
        diff -= delta
    delta >>= 1
    if diff >= delta:
        nibble |= 1
    predictor = _decode_ima_nibble(nibble, predictor, step_index)
    step_index = min(88, max(0, step_index + _IMA_INDEX_TABLE[nibble & 0x0F]))
    return nibble, predictor, step_index


def _decode_ima_nibble(nibble: int, predictor: int, step_index: int) -> int:
    step = _IMA_STEP_TABLE[step_index]
    diff = step >> 3
    if nibble & 0x01:
        diff += step >> 2
    if nibble & 0x02:
        diff += step >> 1
    if nibble & 0x04:
        diff += step
    if nibble & 0x08:
        predictor -= diff
    else:
        predictor += diff
    return min(32767, max(-32768, predictor))
