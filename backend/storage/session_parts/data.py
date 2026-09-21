"""会话主数据读写。"""

from __future__ import annotations

from copy import deepcopy
import json
import uuid
from datetime import datetime
from typing import Any


class SessionDataMixin:
    """处理会话 JSON 的创建、更新、列表和状态字段写回。"""

    def create_session(
        self,
        topic: str,
        min_rounds: int,
        max_rounds: int,
        config_summary: dict[str, Any],
        runtime_settings: dict[str, Any] | None = None,
        *,
        kind: str = "debate",
        id_prefix: str = "",
    ) -> dict[str, Any]:
        session_id = f"{id_prefix}{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        session = {
            "kind": kind,
            "id": session_id,
            "topic": topic,
            "min_rounds": min_rounds,
            "max_rounds": max_rounds,
            "created_at": self._now(),
            "updated_at": self._now(),
            "finished_at": None,
            "status": "queued",
            "messages": [],
            "live_status": None,
            "result": None,
            "error_message": None,
            "error_traceback": None,
            "termination_message": None,
            "detail_record_path": None,
            "error_record_path": None,
            "config_summary": config_summary,
            "runtime_config_version": 1 if isinstance(runtime_settings, dict) else None,
            "usage_stats": None,
            "archived": False,
            "archived_at": None,
            "runtime_state": None,
            "active_user_message": None,
        }
        with self._lock:
            runtime_path = self._runtime_config_path(session_id)
            try:
                if isinstance(runtime_settings, dict):
                    self._atomic_write_json(runtime_path, deepcopy(runtime_settings))
                return self._write_session(session)
            except Exception:
                runtime_path.unlink(missing_ok=True)
                raise

    def update_session(self, session_id: str, updater) -> dict[str, Any] | None:
        with self._lock:
            session = self._normalize_session(self._read_session_unlocked(session_id))
            if session is None:
                return None
            updated = updater(session)
            if updated is None:
                updated = session
            updated["updated_at"] = self._now()
            return self._write_session(updated)

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            raw_session = self._read_session_unlocked(session_id)
            normalized = self._normalize_session(raw_session)
            if normalized is not None and normalized != raw_session:
                return self._write_session(normalized)
            return normalized

    def list_sessions(self, archived: bool = False, *, kind: str = "debate") -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        with self._lock:
            for path in self.session_dir.glob("*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                session = self._normalize_session(payload)
                if bool(session.get("archived")) != archived:
                    continue
                if str(session.get("kind") or "debate") != kind:
                    continue
                sessions.append(session)
        sessions.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return [self._session_summary(item) for item in sessions]

    def _session_summary(self, session: dict[str, Any]) -> dict[str, Any]:
        """把完整 session 收敛成侧栏列表所需的摘要。"""

        messages = session.get("messages") or []
        preview = ""
        runtime_state = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
        display_topic = str(runtime_state.get("debate_title") or session.get("topic") or "")
        live_status = session.get("live_status") or {}
        live_preview = str(live_status.get("content", ""))[:120]
        if session.get("status") in {"queued", "running", "paused"} and live_preview:
            preview = live_preview
        elif messages:
            preview = str(messages[-1].get("content", ""))[:120]
        result = session.get("result") or {}
        return {
            "kind": str(session.get("kind") or "debate"),
            "id": session.get("id"),
            "topic": display_topic,
            "status": session.get("status"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "finished_at": session.get("finished_at"),
            "preview": preview,
            "winner": result.get("winner"),
            "message_count": len(messages),
            "archived": bool(session.get("archived")),
            "archived_at": session.get("archived_at"),
        }

    def append_message(self, session_id: str, message: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return None
            session.setdefault("messages", []).append(message)
            session["updated_at"] = self._now()
            return self._write_session(session)

    def commit_runtime_phase(
        self,
        session_id: str,
        runtime_state: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Persist one completed phase as a single session-file replacement."""

        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return None
            existing_messages = session.get("messages") if isinstance(session.get("messages"), list) else []
            existing_ids = {
                str(message.get("id") or "")
                for message in existing_messages
                if isinstance(message, dict) and str(message.get("id") or "")
            }
            committed_messages = [
                deepcopy(message)
                for message in messages
                if isinstance(message, dict) and str(message.get("id") or "") not in existing_ids
            ]
            session["messages"] = [*existing_messages, *committed_messages]
            session["runtime_state"] = deepcopy(runtime_state)
            if committed_messages:
                session["live_status"] = None
            session["updated_at"] = self._now()
            return self._write_session(session)

    def load_runtime_settings(self, session_id: str) -> dict[str, Any] | None:
        """Load the private immutable runtime configuration for a debate."""

        with self._lock:
            path = self._runtime_config_path(session_id)
            if not path.exists():
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
            return deepcopy(payload) if isinstance(payload, dict) else None

    def set_live_status(self, session_id: str, live_status: dict[str, Any] | None) -> dict[str, Any] | None:
        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return None
            session["live_status"] = live_status
            session["updated_at"] = self._now()
            return self._write_session(session)

    def set_status(
        self,
        session_id: str,
        status: str,
        error_message: str | None = None,
        error_traceback: str | None = None,
        termination_message: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return None
            session["status"] = status
            session["updated_at"] = self._now()
            if status == "error":
                session["error_message"] = error_message
                session["error_traceback"] = error_traceback
                session["termination_message"] = None
            elif status == "terminated":
                session["error_message"] = None
                session["error_traceback"] = None
                session["termination_message"] = termination_message
            else:
                session["error_message"] = None
                session["error_traceback"] = None
                session["termination_message"] = None
            if status in {"completed", "error", "terminated"}:
                session["finished_at"] = self._now()
                session["live_status"] = None
            else:
                session["finished_at"] = None
            return self._write_session(session)

    def set_runtime_state(self, session_id: str, runtime_state: dict[str, Any] | None) -> dict[str, Any] | None:
        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return None
            session["runtime_state"] = runtime_state
            session["updated_at"] = self._now()
            return self._write_session(session)

    def set_active_user_message(self, session_id: str, active_user_message: dict[str, Any] | None) -> dict[str, Any] | None:
        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return None
            session["active_user_message"] = active_user_message
            session["updated_at"] = self._now()
            return self._write_session(session)

    def set_result(self, session_id: str, result: dict[str, Any] | None) -> dict[str, Any] | None:
        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return None
            session["result"] = result
            session["updated_at"] = self._now()
            return self._write_session(session)

    def set_usage_stats(self, session_id: str, usage_stats: dict[str, Any] | None) -> dict[str, Any] | None:
        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return None
            session["usage_stats"] = usage_stats
            session["updated_at"] = self._now()
            return self._write_session(session)

    def set_record_paths(
        self,
        session_id: str,
        *,
        detail_record_path: str | None = None,
        error_record_path: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return None
            if detail_record_path is not None:
                session["detail_record_path"] = detail_record_path
            if error_record_path is not None:
                session["error_record_path"] = error_record_path
            session["updated_at"] = self._now()
            return self._write_session(session)

    def sync_record_paths(self, session_id: str) -> dict[str, Any] | None:
        """把默认日志文件路径同步回 session 元数据。"""

        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return None
            changed = False
            detail_path = self._detail_path(session_id)
            error_path = self._error_path(session_id)
            if detail_path.exists() and session.get("detail_record_path") != str(detail_path):
                session["detail_record_path"] = str(detail_path)
                changed = True
            if error_path.exists() and session.get("error_record_path") != str(error_path):
                session["error_record_path"] = str(error_path)
                changed = True
            if not changed:
                return session
            session["updated_at"] = self._now()
            return self._write_session(session)
