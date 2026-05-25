from __future__ import annotations

import io
import json
import unittest
import wave

from stackchan_bridge.tts_provider import (
    AUDIO_CHANNELS,
    AUDIO_FORMAT,
    AUDIO_SAMPLE_RATE,
    TtsProviderError,
    VoiceVoxTtsProvider,
    decode_wav_to_pcm_s16le_mono_16k,
    default_voice_profiles,
    trim_pcm_s16le_silence,
    tune_voicevox_query_payload,
)


def wav_bytes(*, sample_rate: int = 24000, channels: int = 2) -> bytes:
    frames = bytearray()
    for index in range(sample_rate // 100):
        value = int((index % 64) * 128)
        for _channel in range(channels):
            frames.extend(value.to_bytes(2, "little", signed=True))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))
    return output.getvalue()


class TtsProviderTests(unittest.TestCase):
    def test_decode_wav_normalizes_to_baseline_pcm(self) -> None:
        audio = decode_wav_to_pcm_s16le_mono_16k(wav_bytes())

        self.assertEqual(audio.format, AUDIO_FORMAT)
        self.assertEqual(audio.sample_rate, AUDIO_SAMPLE_RATE)
        self.assertEqual(audio.channels, AUDIO_CHANNELS)
        self.assertGreater(len(audio.pcm), 0)
        self.assertEqual(len(audio.pcm) % 2, 0)

    def test_voicevox_adapter_uses_profile_and_returns_normalized_audio(self) -> None:
        calls: list[tuple[str, bytes, dict[str, str]]] = []

        def post(url: str, data: bytes, headers: dict[str, str], timeout: float) -> bytes:
            calls.append((url, data, headers))
            if url.endswith("/audio_query?text=hello&speaker=3"):
                return b'{"accent_phrases":[]}'
            if url.endswith("/synthesis?speaker=3"):
                return wav_bytes()
            raise AssertionError(url)

        provider = VoiceVoxTtsProvider(
            profiles=default_voice_profiles("http://voicevox:50021"),
            default_profile="default",
            http_post=post,
        )

        profile, audio = provider.synthesize("hello", "default")

        self.assertEqual(profile.name, "default")
        self.assertEqual(audio.sample_rate, AUDIO_SAMPLE_RATE)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1], b'{"accent_phrases":[]}')

    def test_voicevox_adapter_applies_transport_tuning(self) -> None:
        calls: list[tuple[str, bytes, dict[str, str]]] = []

        def post(url: str, data: bytes, headers: dict[str, str], timeout: float) -> bytes:
            calls.append((url, data, headers))
            if url.endswith("/audio_query?text=hello&speaker=3"):
                return b'{"accent_phrases":[],"speedScale":1.0}'
            if url.endswith("/synthesis?speaker=3"):
                return wav_bytes()
            raise AssertionError(url)

        provider = VoiceVoxTtsProvider(
            profiles=default_voice_profiles("http://voicevox:50021"),
            default_profile="default",
            speed_scale=3.0,
            pre_phoneme_length=0.0,
            post_phoneme_length=0.0,
            http_post=post,
        )

        _profile, _audio = provider.synthesize("hello", "default")

        tuned_query = json.loads(calls[1][1].decode("utf-8"))
        self.assertEqual(tuned_query["speedScale"], 3.0)
        self.assertEqual(tuned_query["prePhonemeLength"], 0.0)
        self.assertEqual(tuned_query["postPhonemeLength"], 0.0)

    def test_tune_voicevox_query_payload_rejects_invalid_json(self) -> None:
        with self.assertRaises(TtsProviderError) as raised:
            tune_voicevox_query_payload(b"not-json", speed_scale=2.0)

        self.assertEqual(raised.exception.code, "TTS_SYNTHESIS_FAILED")

    def test_trim_pcm_s16le_silence_preserves_margin(self) -> None:
        samples = [0, 10, 400, 800, 900, 400, 5, 0]
        pcm = b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples)

        trimmed = trim_pcm_s16le_silence(pcm, threshold=512, margin_samples=1)

        decoded = [
            int.from_bytes(trimmed[index : index + 2], "little", signed=True)
            for index in range(0, len(trimmed), 2)
        ]
        self.assertEqual(decoded, [400, 800, 900, 400])

    def test_unknown_voice_profile_is_structured_error(self) -> None:
        provider = VoiceVoxTtsProvider(
            profiles=default_voice_profiles("http://voicevox:50021"),
            default_profile="default",
        )

        with self.assertRaises(TtsProviderError) as raised:
            provider.synthesize("hello", "missing")

        self.assertEqual(raised.exception.code, "UNKNOWN_VOICE_PROFILE")
        self.assertFalse(raised.exception.recoverable)


if __name__ == "__main__":
    unittest.main()
