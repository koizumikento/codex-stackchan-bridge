from __future__ import annotations

import unittest

from stackchan_bridge.audio_codec import (
    AUDIO_CHUNK_FORMAT_ID_IMA_ADPCM_4BIT,
    IMA_ADPCM_HEADER_BYTES,
    encode_ima_adpcm_4bit,
)


class AudioCodecTests(unittest.TestCase):
    def test_ima_adpcm_encodes_header_and_low_nibble_first(self) -> None:
        pcm = b"\x00\x00\x01\x00\x02\x00"

        encoded = encode_ima_adpcm_4bit(pcm)

        self.assertEqual(encoded, b"\x00\x00\x00\x00\x11")
        self.assertEqual(AUDIO_CHUNK_FORMAT_ID_IMA_ADPCM_4BIT, 2)
        self.assertEqual(IMA_ADPCM_HEADER_BYTES, 4)

    def test_ima_adpcm_pads_single_final_nibble(self) -> None:
        encoded = encode_ima_adpcm_4bit(b"\x00\x00\x01\x00")

        self.assertEqual(encoded, b"\x00\x00\x00\x00\x01")

    def test_ima_adpcm_rejects_empty_or_odd_pcm(self) -> None:
        with self.assertRaises(ValueError):
            encode_ima_adpcm_4bit(b"")
        with self.assertRaises(ValueError):
            encode_ima_adpcm_4bit(b"\x00")


if __name__ == "__main__":
    unittest.main()
