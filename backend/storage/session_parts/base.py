"""SessionStore 的基础路径、锁和底层读写。"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class BaseSessionStore:
    """提供所有存储 mixin 共用的基础能力。"""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parents[3]
        self.session_dir = self.base_dir / "data" / "debates"
        self.runtime_config_dir = self.base_dir / "data" / "runtime_configs"
        self.detail_dir = self.base_dir / "logs" / "details"
        self.error_dir = self.base_dir / "logs" / "errors"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_config_dir.mkdir(parents=True, exist_ok=True)
        self.detail_dir.mkdir(parents=True, exist_ok=True)
        self.error_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _now(self) -> str:
        """返回带时区的统一时间戳。"""

        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _session_path(self, session_id: str) -> Path:
        return self.session_dir / f"{self._validate_session_id(session_id)}.json"

    def _detail_path(self, session_id: str) -> Path:
        return self.detail_dir / f"{self._validate_session_id(session_id)}.md"

    def _runtime_config_path(self, session_id: str) -> Path:
        return self.runtime_config_dir / f"{self._validate_session_id(session_id)}.json"

    def _error_path(self, session_id: str) -> Path:
        return self.error_dir / f"{self._validate_session_id(session_id)}.md"

    def _validate_session_id(self, session_id: Any) -> str:
        value = str(session_id or "").strip()
        if not SESSION_ID_PATTERN.fullmatch(value):
            raise ValueError("Invalid debate session ID.")
        return value

    def _write_session(self, session: dict[str, Any]) -> dict[str, Any]:
        """把单个会话写回磁盘。"""

        safe_session = deepcopy(session)
        if isinstance(safe_session.get("config_summary"), dict):
            from ...config.settings_parts.helpers import _mask_sensitive_values

            safe_session["config_summary"] = _mask_sensitive_values(safe_session["config_summary"])
        path = self._session_path(safe_session["id"])
        self._atomic_write_json(path, safe_session)
        return safe_session

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        """Atomically replace one JSON file after flushing its contents to disk."""

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

    def _read_session_unlocked(self, session_id: str) -> dict[str, Any] | None:
        """在已持有锁的前提下读取单个会话。"""

        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _existing_record_path(self, session: dict[str, Any], kind: str) -> Path | None:
        """找出当前会话实际存在的 detail / error 记录文件。"""

        session_id = str(session.get("id") or "")
        if not session_id:
            return None
        if kind == "detail":
            candidate = Path(session.get("detail_record_path") or self._detail_path(session_id))
        elif kind == "error":
            candidate = Path(session.get("error_record_path") or self._error_path(session_id))
        else:
            return None
        return candidate if candidate.exists() else None

    def _normalize_session(self, session: dict[str, Any] | None) -> dict[str, Any] | None:
        """给老记录补齐新版本依赖的默认字段。"""

        if session is None:
            return None
        normalized = dict(session)
        normalized.setdefault("kind", "debate")
        normalized.setdefault("messages", [])
        normalized.setdefault("live_status", None)
        normalized.setdefault("archived", False)
        normalized.setdefault("archived_at", None)
        normalized.setdefault("runtime_state", None)
        normalized.setdefault("runtime_config_version", None)
        normalized.setdefault("active_user_message", None)
        if isinstance(normalized.get("config_summary"), dict):
            from ...config.settings_parts.helpers import _mask_sensitive_values

            normalized["config_summary"] = _mask_sensitive_values(normalized["config_summary"])
        return normalized
