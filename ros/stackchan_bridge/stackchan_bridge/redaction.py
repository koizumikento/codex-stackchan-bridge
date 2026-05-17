"""Redaction helpers for bridge logs and event metadata."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

REDACTED = "<redacted>"

SPEECH_TEXT_FIELDS = frozenset({"speech_text", "text", "transcript", "utterance"})
IMAGE_FIELDS = frozenset({"image", "image_payload", "image_data", "jpeg", "frame"})
NFC_FIELDS = frozenset({"nfc_tag_id", "tag_id", "uid"})
SECRET_FIELDS = frozenset(
    {
        "api_key",
        "authorization",
        "password",
        "secret",
        "token",
    }
)


@dataclass(frozen=True)
class RedactionPolicy:
    """Controls bridge redaction behavior for diagnostics and logs."""

    reveal_sensitive: bool = False
    hash_nfc_ids: bool = False


DEFAULT_REDACTION_POLICY = RedactionPolicy()


def redact_fields(
    fields: Mapping[str, Any],
    *,
    policy: RedactionPolicy = DEFAULT_REDACTION_POLICY,
) -> dict[str, Any]:
    """Return a redacted copy of structured fields."""

    return {key: redact_value(key, value, policy=policy) for key, value in fields.items()}


def redact_payload(
    payload: Any,
    *,
    policy: RedactionPolicy = DEFAULT_REDACTION_POLICY,
) -> Any:
    """Redact sensitive values in an arbitrary JSON-like payload."""

    if isinstance(payload, Mapping):
        return redact_fields(payload, policy=policy)
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [redact_payload(item, policy=policy) for item in payload]
    return payload


def redact_payload_json(
    payload_json: str,
    *,
    policy: RedactionPolicy = DEFAULT_REDACTION_POLICY,
) -> str:
    """Redact a JSON object/array string while preserving valid JSON output."""

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return payload_json
    return json.dumps(redact_payload(payload, policy=policy), sort_keys=True)


def redact_value(
    key: str,
    value: Any,
    *,
    policy: RedactionPolicy = DEFAULT_REDACTION_POLICY,
) -> Any:
    """Redact one value based on its field name."""

    if policy.reveal_sensitive:
        return redact_payload(value, policy=policy)

    normalized_key = key.strip().lower()
    if normalized_key in SPEECH_TEXT_FIELDS:
        return REDACTED
    if normalized_key in IMAGE_FIELDS:
        return REDACTED
    if normalized_key in SECRET_FIELDS or _contains_secret_marker(normalized_key):
        return REDACTED
    if normalized_key in NFC_FIELDS:
        return _hash_sensitive(value) if policy.hash_nfc_ids else REDACTED
    return redact_payload(value, policy=policy)


def _contains_secret_marker(key: str) -> bool:
    return any(marker in key for marker in ("secret", "token", "password"))


def _hash_sensitive(value: Any) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"
