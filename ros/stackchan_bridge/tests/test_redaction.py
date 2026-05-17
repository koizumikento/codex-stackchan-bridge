from __future__ import annotations

import json
import unittest

from stackchan_bridge.redaction import (
    REDACTED,
    RedactionPolicy,
    redact_fields,
    redact_payload_json,
)


class RedactionTests(unittest.TestCase):
    def test_redacts_speech_images_and_secrets_by_default(self) -> None:
        redacted = redact_fields(
            {
                "device_id": "default",
                "text": "hello",
                "image_payload": b"jpeg-bytes",
                "token": "secret-token",
            }
        )

        self.assertEqual(redacted["device_id"], "default")
        self.assertEqual(redacted["text"], REDACTED)
        self.assertEqual(redacted["image_payload"], REDACTED)
        self.assertEqual(redacted["token"], REDACTED)

    def test_redacts_nfc_tag_ids_by_default(self) -> None:
        redacted = redact_fields({"nfc_tag_id": "04AABBCCDD"})

        self.assertEqual(redacted["nfc_tag_id"], REDACTED)

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


if __name__ == "__main__":
    unittest.main()
