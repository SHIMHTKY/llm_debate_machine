"""SessionStore 的基础路径、锁和底层读写。"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class BaseSessionStore:
    """提供所有存储 mixin 共用的基础能力。"""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parents[3]
        self.session_dir = self.base_dir / "data" / "debates"
        self.detail_dir = self.base_dir / "logs" / "details"
        self.error_dir = self.base_dir / "logs" / "errors"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.detail_dir.mkdir(parents=True, exist_ok=True)
        self.error_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _now(self) -> str:
        """返回带时区的统一时间戳。"""

        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _session_path(self, session_id: str) -> Path:
        return self.session_dir / f"{session_id}.json"

    def _detail_path(self, session_id: str) -> Path:
        return self.detail_dir / f"{session_id}.md"

    def _error_path(self, session_id: str) -> Path:
        return self.error_dir / f"{session_id}.md"

    def _write_session(self, session: dict[str, Any]) -> dict[str, Any]:
        """把单个会话写回磁盘。"""

        path = self._session_path(session["id"])
        path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        return session

    def _read_session_unlocked(self, session_id: str) -> dict[str, Any] | None:
        """在已持有锁的前提下读取单个会话。"""

        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

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
        normalized.setdefault("messages", [])
        normalized.setdefault("live_status", None)
        normalized.setdefault("archived", False)
        normalized.setdefault("archived_at", None)
        normalized.setdefault("runtime_state", None)
        normalized.setdefault("active_user_message", None)
        return normalized
