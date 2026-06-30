"""设置文件读写入口。"""

from __future__ import annotations

import json
from typing import Any

from .constants import DATA_DIR, SETTINGS_FILE
from .normalize import _resolve_runtime_settings, normalize_settings


def _load_raw_settings() -> dict[str, Any]:
    """读取并自动修复 settings.json。"""

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not SETTINGS_FILE.exists():
        defaults = normalize_settings({})
        SETTINGS_FILE.write_text(json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8")
        return defaults

    try:
        raw_settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raw_settings = {}

    normalized = normalize_settings(raw_settings)
    SETTINGS_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def _save_raw_settings(raw_settings: Any) -> dict[str, Any]:
    """保存设置，并在写盘前做严格校验。"""

    existing = _load_raw_settings()
    normalized = normalize_settings(raw_settings, base_settings=existing, strict_extra_body=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def load_settings() -> dict[str, Any]:
    """提供运行时使用的 settings 结构。"""

    return _resolve_runtime_settings(_load_raw_settings())


def save_settings(raw_settings: Any) -> dict[str, Any]:
    """保存后返回运行时结构，便于调用方直接继续使用。"""

    return _resolve_runtime_settings(_save_raw_settings(raw_settings))
