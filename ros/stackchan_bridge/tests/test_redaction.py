from __future__ import annotations

import json
import unittest

from stackchan_bridge.redaction import (
    REDACTED,
    RedactionPolicy,
    redact_fields,
    redact_payload_json,
)
from stackchan_bridge.logging import log_structured


class RedactionTests(unittest.TestCase):
    def test_redacts_speech_images_and_secrets_by_default(self) -> None:
        redacted = redact_fields(
            {
                "device_id": "default",
                "text": "hello",
                "full_transcript": "turn the light on",
                "asr_transcript": "open the window",
                "utterance_text": "hello again",
                "utterance_id": "utt-1",
                "image_payload": b"jpeg-bytes",
                "token": "secret-token",
            }
        )

        self.assertEqual(redacted["device_id"], "default")
        self.assertEqual(redacted["text"], REDACTED)
        self.assertEqual(redacted["full_transcript"], REDACTED)
        self.assertEqual(redacted["asr_transcript"], REDACTED)
        self.assertEqual(redacted["utterance_text"], REDACTED)
        self.assertEqual(redacted["utterance_id"], "utt-1")
        self.assertEqual(redacted["image_payload"], REDACTED)
        self.assertEqual(redacted["token"], REDACTED)

    def test_redacts_audio_payloads_and_keeps_logs_json_serializable(self) -> None:
        class Logger:
            def __init__(self) -> None:
                self.messages: list[str] = []

            def info(self, message: str) -> None:
                self.messages.append(message)

        logger = Logger()

        redacted = redact_fields({"audio_payload": b"pcm-bytes"})
        log_structured(logger, 20, "audio", audio_payload=b"pcm-bytes")

        self.assertEqual(redacted["audio_payload"], REDACTED)
        payload = json.loads(logger.messages[0])
        self.assertEqual(payload["audio_payload"], REDACTED)

    def test_redacts_nfc_tag_ids_by_default(self) -> None:
        redacted = redact_fields({"nfc_tag_id": "04AABBCCDD"})

        self.assertEqual(redacted["nfc_tag_id"], REDACTED)

    def test_redacts_raw_ir_remote_and_protocol_dumps_by_default(self) -> None:
        redacted = redact_fields(
            {
                "raw_ir_code": "0xDEADBEEF",
                "remote_code": "volume_up",
                "protocol_dump": "NEC raw timing data",
            }
        )

        self.assertEqual(redacted["raw_ir_code"], REDACTED)
        self.assertEqual(redacted["remote_code"], REDACTED)
        self.assertEqual(redacted["protocol_dump"], REDACTED)

    def test_can_hash_nfc_tag_ids_without_leaking_raw_value(self) -> None:
        redacted = redact_fields(
            {"nfc_tag_id": "04AABBCCDD"},
            policy=RedactionPolicy(hash_nfc_ids=True),
        )

        self.assertTrue(str(redacted["nfc_tag_id"]).startswith("sha256:"))
        self.assertNotIn("04AABBCCDD", str(redacted["nfc_tag_id"]))

    def test_redacts_nested_payload_json(self) -> None:
        redacted_json = redact_payload_json(
            json.dumps(
                {
                    "payload": {
                        "speech_text": "private speech",
                        "nested": [{"api_key": "key"}],
                    }
                }
            )
        )

        redacted = json.loads(redacted_json)

        self.assertEqual(redacted["payload"]["speech_text"], REDACTED)
        self.assertEqual(redacted["payload"]["nested"][0]["api_key"], REDACTED)

    def test_invalid_payload_json_returns_safe_marker(self) -> None:
        redacted_json = redact_payload_json("raw_ir_code=0xDEADBEEF tag_id=04AABB")
        redacted = json.loads(redacted_json)

        self.assertTrue(redacted["truncated"])
        self.assertEqual(redacted["reason"], "payload_json_invalid")
        self.assertNotIn("0xDEADBEEF", redacted_json)
        self.assertNotIn("04AABB", redacted_json)

    def test_non_object_payload_json_returns_safe_marker(self) -> None:
        for raw_payload in (
            '"raw_ir_code=0xDEADBEEF tag_id=04AABB"',
            '["raw_ir_code=0xDEADBEEF", "tag_id=04AABB"]',
        ):
            with self.subTest(raw_payload=raw_payload):
                redacted_json = redact_payload_json(raw_payload)
                redacted = json.loads(redacted_json)

                self.assertTrue(redacted["truncated"])
                self.assertEqual(redacted["reason"], "payload_json_invalid")
                self.assertNotIn("0xDEADBEEF", redacted_json)
                self.assertNotIn("04AABB", redacted_json)


if __name__ == "__main__":
    unittest.main()
