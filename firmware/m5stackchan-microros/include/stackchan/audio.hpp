#pragma once

#include <stdint.h>

#include "stackchan/contract.hpp"
#include "stackchan/events.hpp"

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

enum class AudioCaptureEvent : uint8_t {
  Started,
  Finished,
  Failed,
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

inline Result publish_audio_underrun_event(
    EventPublisher& events,
    uint32_t stamp_ms,
    const char* command_id = "") {
  return events.audio_playback_underrun(stamp_ms, command_id);
}

inline Result publish_mic_overrun_event(
    EventPublisher& events,
    uint32_t stamp_ms,
    const char* command_id = "") {
  return events.mic_overrun(stamp_ms, command_id);
}

inline Result publish_audio_capture_event(
    EventPublisher& events,
    AudioCaptureEvent event,
    uint32_t stamp_ms,
    const char* command_id = "") {
  switch (event) {
    case AudioCaptureEvent::Started:
      return events.audio_capture_started(stamp_ms, command_id);
    case AudioCaptureEvent::Finished:
      return events.audio_capture_finished(stamp_ms, command_id);
    case AudioCaptureEvent::Failed:
      return events.audio_capture_failed(stamp_ms, command_id);
  }
  return Result::rejected("UNKNOWN_COMMAND", "unknown audio capture event");
}

}  // namespace stackchan
