#pragma once

#include <stdint.h>
#include <string.h>

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

enum class AudioFormat : uint8_t {
  PcmS16Le = 1,
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

struct AudioPlaybackChunk {
  const char* command_id;
  AudioDirection direction;
  AudioFormat format;
  uint32_t sample_rate;
  uint8_t channels;
  uint32_t sequence;
  uint16_t pcm_size;
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

class AudioPlaybackChunkGuard {
 public:
  Result start_session(const char* command_id) {
    if (active_) {
      return Result::rejected("FIRMWARE_BUSY", "audio playback already active", true);
    }
    copy_event_string(command_id_, sizeof(command_id_), command_id == nullptr ? "" : command_id);
    expected_sequence_ = 0;
    active_ = true;
    return Result::accepted("audio playback session accepted");
  }

  Result finish_session() {
    active_ = false;
    expected_sequence_ = 0;
    copy_event_string(command_id_, sizeof(command_id_), "");
    return Result::accepted("audio playback session finished");
  }

  Result validate_chunk(const AudioPlaybackChunk& chunk) {
    if (!active_) {
      return Result::rejected(
          "UNKNOWN_COMMAND",
          "audio playback chunk arrived without an accepted session",
          true);
    }
    if (chunk.command_id == nullptr || strcmp(chunk.command_id, command_id_) != 0) {
      return Result::rejected(
          "UNKNOWN_COMMAND",
          "audio playback chunk command_id does not match active session",
          true);
    }
    if (chunk.direction != AudioDirection::Playback) {
      return Result::rejected(
          "MALFORMED_AUDIO_CHUNK",
          "audio playback chunk has wrong direction",
          true);
    }
    if (chunk.format != AudioFormat::PcmS16Le ||
        chunk.sample_rate != kAudioSampleRate ||
        chunk.channels != kAudioChannels) {
      return Result::rejected(
          "UNSUPPORTED_FEATURE",
          "audio playback chunk format is unsupported",
          false);
    }
    if (chunk.pcm_size == 0 || chunk.pcm_size > kAudioMaxChunkBytes) {
      return Result::rejected(
          "MALFORMED_AUDIO_CHUNK",
          "audio playback chunk size is invalid",
          true);
    }
    if (chunk.sequence != expected_sequence_) {
      return Result::rejected(
          "AUDIO_UNDERRUN",
          "audio playback chunk sequence gap",
          true);
    }
    expected_sequence_++;
    return Result::accepted("audio playback chunk accepted");
  }

  bool active() const { return active_; }
  uint32_t expected_sequence() const { return expected_sequence_; }

 private:
  bool active_ = false;
  uint32_t expected_sequence_ = 0;
  char command_id_[37]{};
};

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
