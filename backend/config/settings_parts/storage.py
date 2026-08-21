"""设置文件读写入口。"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import DATA_DIR, SETTINGS_FILE
from .normalize import _resolve_runtime_settings, normalize_settings


_SETTINGS_LOCK = threading.RLock()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON without ever exposing a partially written settings file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            file.write(serialized)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _quarantine_corrupt_settings() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = SETTINGS_FILE.with_name(f"{SETTINGS_FILE.name}.corrupt-{timestamp}")
    os.replace(SETTINGS_FILE, backup_path)
    return backup_path


def _load_raw_settings() -> dict[str, Any]:
    """读取并自动修复 settings.json。"""

    with _SETTINGS_LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        if not SETTINGS_FILE.exists():
            defaults = normalize_settings({})
            _atomic_write_json(SETTINGS_FILE, defaults)
            return defaults

        try:
            raw_settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Keep the original bytes for recovery instead of silently destroying secrets.
            _quarantine_corrupt_settings()
            defaults = normalize_settings({})
            _atomic_write_json(SETTINGS_FILE, defaults)
            return defaults

        if not isinstance(raw_settings, dict):
            _quarantine_corrupt_settings()
            defaults = normalize_settings({})
            _atomic_write_json(SETTINGS_FILE, defaults)
            return defaults

        normalized = normalize_settings(raw_settings)
        if normalized != raw_settings:
            _atomic_write_json(SETTINGS_FILE, normalized)
        return normalized


def _save_raw_settings(raw_settings: Any) -> dict[str, Any]:
    """保存设置，并在写盘前做严格校验。"""

    with _SETTINGS_LOCK:
        existing = _load_raw_settings()
        normalized = normalize_settings(raw_settings, base_settings=existing, strict_extra_body=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(SETTINGS_FILE, normalized)
        return normalized


def load_settings() -> dict[str, Any]:
    """提供运行时使用的 settings 结构。"""

    return _resolve_runtime_settings(_load_raw_settings())


def save_settings(raw_settings: Any) -> dict[str, Any]:
    """保存后返回运行时结构，便于调用方直接继续使用。"""

    return _resolve_runtime_settings(_save_raw_settings(raw_settings))
