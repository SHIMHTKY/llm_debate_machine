"""Small normalization helpers for persisted settings."""

from __future__ import annotations

import ast
from copy import deepcopy
import json
import re
from typing import Any
from uuid import uuid4

from .constants import (
    DEFAULT_CONTEXT_ROUNDS,
    MASKED_SECRET,
    MAX_CONTEXT_ROUNDS,
    MIN_CONTEXT_ROUNDS,
)


_SENSITIVE_KEYS = {
    "apikey",
    "authorization",
    "auth",
    "authtoken",
    "bearertoken",
    "clientsecret",
    "cookie",
    "credential",
    "password",
    "privatekey",
    "proxyauthorization",
    "refreshtoken",
    "secret",
    "secretkey",
    "sessiontoken",
    "securitytoken",
    "token",
    "xapikey",
}


def _is_sensitive_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key or "").lower())
    if normalized in _SENSITIVE_KEYS:
        return True
    return normalized.endswith(
        (
            "apikey",
            "accesstoken",
            "authtoken",
            "clientsecret",
            "credential",
            "password",
            "privatekey",
            "privatetoken",
            "secret",
            "secretkey",
            "sessiontoken",
            "securitytoken",
        )
    )


def _mask_sensitive_values(value: Any, key: Any = "") -> Any:
    """Return a structure safe for settings APIs, session data, and logs."""

    if _is_sensitive_key(key):
        return _mask_secret(value)
    if isinstance(value, dict):
        return {
            child_key: _mask_sensitive_values(child_value, child_key)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_mask_sensitive_values(item) for item in value]
    return deepcopy(value)


def _restore_masked_values(value: Any, existing_value: Any) -> Any:
    """Replace frontend mask markers with the corresponding persisted values."""

    if value == MASKED_SECRET and existing_value is not None:
        return deepcopy(existing_value)
    if isinstance(value, dict):
        existing = existing_value if isinstance(existing_value, dict) else {}
        return {
            key: _restore_masked_values(child_value, existing.get(key))
            for key, child_value in value.items()
        }
    if isinstance(value, list):
        existing = existing_value if isinstance(existing_value, list) else []
        return [
            _restore_masked_values(item, existing[index] if index < len(existing) else None)
            for index, item in enumerate(value)
        ]
    return deepcopy(value)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _normalize_context_rounds(value: Any, default: int = DEFAULT_CONTEXT_ROUNDS, *, strict: bool = False) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        if strict:
            raise ValueError(f"context_rounds must be an integer between {MIN_CONTEXT_ROUNDS} and {MAX_CONTEXT_ROUNDS}.")
        return default
    if MIN_CONTEXT_ROUNDS <= parsed <= MAX_CONTEXT_ROUNDS:
        return parsed
    if strict:
        raise ValueError(f"context_rounds must be an integer between {MIN_CONTEXT_ROUNDS} and {MAX_CONTEXT_ROUNDS}.")
    return default


def _mask_secret(value: Any) -> str:
    return MASKED_SECRET if _text(value) else ""


def _normalize_secret(value: Any, existing_value: str = "") -> str:
    if value is None:
        return existing_value
    text = _text(value)
    if text == MASKED_SECRET and existing_value:
        return existing_value
    return text


def _normalize_extra_body(
    value: Any,
    existing_value: dict[str, Any] | None = None,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    base_value = existing_value.copy() if isinstance(existing_value, dict) else {}
    if value is None:
        return base_value
    if isinstance(value, dict):
        return _restore_masked_values(value, base_value)

    text = _text(value)
    if not text:
        return {}

    relaxed_text = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', text)
    relaxed_text = relaxed_text.replace("True", "true").replace("False", "false").replace("None", "null")

    last_error: Exception | None = None
    for parser, candidate in ((json.loads, text), (ast.literal_eval, text), (json.loads, relaxed_text)):
        try:
            parsed = parser(candidate)
        except (json.JSONDecodeError, ValueError, SyntaxError) as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return _restore_masked_values(parsed, base_value)
        last_error = ValueError("extra_body must be an object")

    if strict:
        raise ValueError('ChatOpenAI extra_body must be an object, for example {"enable_thinking": true}.') from last_error
    return base_value


def _create_preset_id() -> str:
    return f"preset_{uuid4().hex[:12]}"


def _create_supplier_id() -> str:
    return f"supplier_{uuid4().hex[:12]}"


def _create_tool_id() -> str:
    return f"tool_{uuid4().hex[:12]}"
