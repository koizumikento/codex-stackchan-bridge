#include <assert.h>
#include <string.h>

#include "stackchan/audio.hpp"

namespace {

stackchan::AudioPlaybackChunk playback_chunk(
    const char* command_id,
    uint32_t sequence,
    uint16_t pcm_size = stackchan::kAudioChunkBytes) {
  return {
      command_id,
      stackchan::AudioDirection::Playback,
      stackchan::AudioFormat::PcmS16Le,
      stackchan::kAudioSampleRate,
      stackchan::kAudioChannels,
      sequence,
      pcm_size,
  };
}

}  // namespace

int main() {
  stackchan::AudioPlaybackChunkGuard guard;

  stackchan::Result result = guard.validate_chunk(playback_chunk("cmd-1", 0));
  assert(!result.ok);
  assert(strcmp(result.error_code, "UNKNOWN_COMMAND") == 0);

  result = guard.start_session("cmd-1");
  assert(result.ok);
  assert(guard.active());

  result = guard.start_session("cmd-2");
  assert(!result.ok);
  assert(strcmp(result.error_code, "FIRMWARE_BUSY") == 0);

  result = guard.validate_chunk(playback_chunk("cmd-1", 0));
  assert(result.ok);
  assert(guard.expected_sequence() == 1);

  result = guard.validate_chunk(playback_chunk("cmd-1", 2));
  assert(!result.ok);
  assert(strcmp(result.error_code, "AUDIO_UNDERRUN") == 0);

  stackchan::AudioPlaybackChunk wrong_format = playback_chunk("cmd-1", 1);
  wrong_format.format = static_cast<stackchan::AudioFormat>(99);
  result = guard.validate_chunk(wrong_format);
  assert(!result.ok);
  assert(strcmp(result.error_code, "UNSUPPORTED_FEATURE") == 0);

  stackchan::AudioPlaybackChunk wrong_command = playback_chunk("other", 1);
  result = guard.validate_chunk(wrong_command);
  assert(!result.ok);
  assert(strcmp(result.error_code, "UNKNOWN_COMMAND") == 0);

  result = guard.finish_session();
  assert(result.ok);
  assert(!guard.active());
  assert(guard.expected_sequence() == 0);

  return 0;
}
