#pragma once

#include <stddef.h>
#include <stdint.h>

#include "stackchan/contract.hpp"

namespace stackchan {

struct ImaAdpcmDecoderState {
  int16_t predictor = 0;
  uint8_t step_index = 0;
  bool initialized = false;
};

struct ImaAdpcmDecodeResult {
  Result result = Result::accepted("IMA ADPCM decoded");
  uint32_t bytes_written = 0;
};

constexpr uint8_t kImaAdpcmHeaderBytes = 4;

inline int16_t clamp_ima_adpcm_sample(int32_t value) {
  if (value > 32767) {
    return 32767;
  }
  if (value < -32768) {
    return -32768;
  }
  return static_cast<int16_t>(value);
}

inline uint8_t clamp_ima_adpcm_step_index(int value) {
  if (value < 0) {
    return 0;
  }
  if (value > 88) {
    return 88;
  }
  return static_cast<uint8_t>(value);
}

inline void write_pcm_s16le(uint8_t* output, uint32_t offset, int16_t sample) {
  output[offset] = static_cast<uint8_t>(sample & 0xff);
  output[offset + 1] = static_cast<uint8_t>((static_cast<uint16_t>(sample) >> 8) & 0xff);
}

inline int16_t decode_ima_adpcm_nibble(ImaAdpcmDecoderState& state, uint8_t nibble) {
  static constexpr int kStepTable[89] = {
      7,     8,     9,     10,    11,    12,    13,    14,    16,    17,
      19,    21,    23,    25,    28,    31,    34,    37,    41,    45,
      50,    55,    60,    66,    73,    80,    88,    97,    107,   118,
      130,   143,   157,   173,   190,   209,   230,   253,   279,   307,
      337,   371,   408,   449,   494,   544,   598,   658,   724,   796,
      876,   963,   1060,  1166,  1282,  1411,  1552,  1707,  1878,  2066,
      2272,  2499,  2749,  3024,  3327,  3660,  4026,  4428,  4871,  5358,
      5894,  6484,  7132,  7845,  8630,  9493,  10442, 11487, 12635, 13899,
      15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767};
  static constexpr int8_t kIndexTable[16] = {
      -1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8};

  nibble &= 0x0f;
  const int step = kStepTable[state.step_index];
  int32_t diff = step >> 3;
  if ((nibble & 0x01) != 0) {
    diff += step >> 2;
  }
  if ((nibble & 0x02) != 0) {
    diff += step >> 1;
  }
  if ((nibble & 0x04) != 0) {
    diff += step;
  }
  if ((nibble & 0x08) != 0) {
    state.predictor = clamp_ima_adpcm_sample(static_cast<int32_t>(state.predictor) - diff);
  } else {
    state.predictor = clamp_ima_adpcm_sample(static_cast<int32_t>(state.predictor) + diff);
  }
  state.step_index =
      clamp_ima_adpcm_step_index(static_cast<int>(state.step_index) + kIndexTable[nibble]);
  return state.predictor;
}

inline ImaAdpcmDecodeResult decode_ima_adpcm_4bit_payload(
    const uint8_t* input,
    size_t input_size,
    bool first_chunk,
    bool end_of_stream,
    uint32_t decoded_total_bytes,
    uint8_t* output,
    size_t output_capacity,
    ImaAdpcmDecoderState& state) {
  ImaAdpcmDecodeResult decoded;
  if (input == nullptr || output == nullptr) {
    decoded.result = Result::rejected("MALFORMED_AUDIO_CHUNK", "IMA ADPCM payload is null", true);
    return decoded;
  }
  if (decoded_total_bytes == 0 || (decoded_total_bytes % 2) != 0) {
    decoded.result = Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "IMA ADPCM decoded byte count is invalid",
        true);
    return decoded;
  }
  if (output_capacity > decoded_total_bytes) {
    output_capacity = decoded_total_bytes;
  }
  size_t offset = 0;
  if (first_chunk) {
    if (input_size < kImaAdpcmHeaderBytes) {
      decoded.result =
          Result::rejected("MALFORMED_AUDIO_CHUNK", "IMA ADPCM header is missing", true);
      return decoded;
    }
    const uint8_t step_index = input[2];
    if (step_index > 88 || input[3] != 0) {
      decoded.result =
          Result::rejected("MALFORMED_AUDIO_CHUNK", "IMA ADPCM header is invalid", true);
      return decoded;
    }
    if (output_capacity < 2) {
      decoded.result =
          Result::rejected("AUDIO_BUFFER_OVERFLOW", "IMA ADPCM decoded output overflows", false);
      return decoded;
    }
    state.predictor = static_cast<int16_t>(
        static_cast<uint16_t>(input[0]) | (static_cast<uint16_t>(input[1]) << 8));
    state.step_index = step_index;
    state.initialized = true;
    write_pcm_s16le(output, decoded.bytes_written, state.predictor);
    decoded.bytes_written += 2;
    offset = kImaAdpcmHeaderBytes;
  } else if (!state.initialized) {
    decoded.result = Result::rejected(
        "MALFORMED_AUDIO_CHUNK",
        "IMA ADPCM continuation arrived before header",
        true);
    return decoded;
  }

  for (; offset < input_size; ++offset) {
    const uint8_t value = input[offset];
    for (uint8_t nibble_index = 0; nibble_index < 2; ++nibble_index) {
      if (decoded.bytes_written >= output_capacity) {
        const bool final_padding =
            end_of_stream &&
            offset == input_size - 1 &&
            nibble_index == 1;
        if (final_padding) {
          continue;
        }
        decoded.result = Result::rejected(
            "AUDIO_BUFFER_OVERFLOW",
            "IMA ADPCM decoded output overflows",
            false);
        return decoded;
      }
      const uint8_t nibble =
          nibble_index == 0 ? (value & 0x0f) : ((value >> 4) & 0x0f);
      const int16_t sample = decode_ima_adpcm_nibble(state, nibble);
      write_pcm_s16le(output, decoded.bytes_written, sample);
      decoded.bytes_written += 2;
    }
  }

  return decoded;
}

}  // namespace stackchan
