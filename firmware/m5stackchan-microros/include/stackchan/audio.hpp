#pragma once

#include <stdint.h>

#include "stackchan/contract.hpp"

namespace stackchan {

constexpr uint32_t kAudioSampleRate = 16000;
constexpr uint8_t kAudioChannels = 1;
constexpr uint16_t kAudioChunkMs = 20;
constexpr uint16_t kAudioMaxChunkMs = 40;
constexpr uint16_t kAudioChunkBytes = 640;
constexpr uint16_t kAudioMaxChunkBytes = 1280;

enum class AudioDirection : uint8_t {
  Playback = 1,
  Capture = 2,
};

struct AudioChunkPolicy {
  uint32_t sample_rate;
  uint8_t channels;
  uint16_t chunk_ms;
  uint16_t max_chunk_ms;
  uint16_t max_chunk_bytes;
};

inline AudioChunkPolicy baseline_audio_policy() {
  return {
      kAudioSampleRate,
      kAudioChannels,
      kAudioChunkMs,
      kAudioMaxChunkMs,
      kAudioMaxChunkBytes,
  };
}

inline Result audio_underrun() {
  return Result::rejected("AUDIO_UNDERRUN", "audio playback underrun", true);
}

inline Result mic_overrun() {
  return Result::rejected("MIC_OVERRUN", "microphone capture overrun", true);
}

}  // namespace stackchan
