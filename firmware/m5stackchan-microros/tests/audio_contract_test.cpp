#include <assert.h>
#include <string.h>

#include "stackchan/adpcm.hpp"
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

  {
    stackchan::ImaAdpcmDecoderState state;
    const uint8_t payload[] = {0x00, 0x00, 0x00, 0x00, 0x11};
    uint8_t decoded[6] = {};
    const stackchan::ImaAdpcmDecodeResult decoded_result =
        stackchan::decode_ima_adpcm_4bit_payload(
            payload,
            sizeof(payload),
            true,
            true,
            sizeof(decoded),
            decoded,
            sizeof(decoded),
            state);
    assert(decoded_result.result.ok);
    assert(decoded_result.bytes_written == sizeof(decoded));
    const uint8_t expected[] = {0x00, 0x00, 0x01, 0x00, 0x02, 0x00};
    assert(memcmp(decoded, expected, sizeof(expected)) == 0);
  }

  {
    stackchan::ImaAdpcmDecoderState state;
    const uint8_t payload[] = {0x00, 0x00, 0x00, 0x00, 0x01};
    uint8_t decoded[4] = {};
    const stackchan::ImaAdpcmDecodeResult decoded_result =
        stackchan::decode_ima_adpcm_4bit_payload(
            payload,
            sizeof(payload),
            true,
            true,
            sizeof(decoded),
            decoded,
            sizeof(decoded),
            state);
    assert(decoded_result.result.ok);
    assert(decoded_result.bytes_written == sizeof(decoded));
    const uint8_t expected[] = {0x00, 0x00, 0x01, 0x00};
    assert(memcmp(decoded, expected, sizeof(expected)) == 0);
  }

  {
    stackchan::ImaAdpcmDecoderState state;
    const uint8_t header[] = {0x00, 0x00, 0x00, 0x00};
    const uint8_t continuation[] = {0x11};
    uint8_t decoded[6] = {};
    stackchan::ImaAdpcmDecodeResult decoded_result =
        stackchan::decode_ima_adpcm_4bit_payload(
            header,
            sizeof(header),
            true,
            false,
            sizeof(decoded),
            decoded,
            sizeof(decoded),
            state);
    assert(decoded_result.result.ok);
    assert(decoded_result.bytes_written == 2);
    decoded_result = stackchan::decode_ima_adpcm_4bit_payload(
        continuation,
        sizeof(continuation),
        false,
        true,
        sizeof(decoded) - 2,
        decoded + 2,
        sizeof(decoded) - 2,
        state);
    assert(decoded_result.result.ok);
    assert(decoded_result.bytes_written == 4);
    const uint8_t expected[] = {0x00, 0x00, 0x01, 0x00, 0x02, 0x00};
    assert(memcmp(decoded, expected, sizeof(expected)) == 0);
  }

  {
    stackchan::ImaAdpcmDecoderState state;
    const uint8_t continuation[] = {0x11};
    uint8_t decoded[4] = {};
    const stackchan::ImaAdpcmDecodeResult decoded_result =
        stackchan::decode_ima_adpcm_4bit_payload(
            continuation,
            sizeof(continuation),
            false,
            true,
            sizeof(decoded),
            decoded,
            sizeof(decoded),
            state);
    assert(!decoded_result.result.ok);
    assert(strcmp(decoded_result.result.error_code, "MALFORMED_AUDIO_CHUNK") == 0);
  }

  {
    stackchan::ImaAdpcmDecoderState state;
    const uint8_t invalid_header[] = {0x00, 0x00, 0x59, 0x00};
    uint8_t decoded[2] = {};
    const stackchan::ImaAdpcmDecodeResult decoded_result =
        stackchan::decode_ima_adpcm_4bit_payload(
            invalid_header,
            sizeof(invalid_header),
            true,
            true,
            sizeof(decoded),
            decoded,
            sizeof(decoded),
            state);
    assert(!decoded_result.result.ok);
    assert(strcmp(decoded_result.result.error_code, "MALFORMED_AUDIO_CHUNK") == 0);
  }

  return 0;
}
