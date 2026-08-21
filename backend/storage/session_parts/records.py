"""detail / error 记录文件与归档操作。"""

from __future__ import annotations

from pathlib import Path
import re


class SessionRecordMixin:
    """管理日志文件、归档状态和记录列表。"""

    def _record_display_title(self, session: dict) -> str:
        """返回记录页优先显示的标题。

        新记录优先显示裁判生成或用户改过的 `debate_title`；
        老记录如果没有这个字段，则继续回退到原始辩题。
        """

        runtime_state = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
        return str(runtime_state.get("debate_title") or session.get("topic") or "").strip()

    def _rewrite_record_content(self, session: dict, kind: str, content: str) -> str:
        """在读取旧记录时，把标题相关文本动态改写成裁判生成标题。

        说明：
        1. 旧的 detail markdown 在生成时只写入了用户原始辩题。
        2. 这些历史文件如果逐个重写，成本高且容易污染原始日志。
        3. 因此这里采用“读取时改写”的方式，只影响记录页展示，不改磁盘原文件。
        """

        text = str(content or "")
        display_title = self._record_display_title(session)
        if not text.strip() or not display_title:
            return text

        prefix = "错误" if kind == "error" else "详情"
        text = re.sub(r"^# .*$", f"# {prefix}·{display_title}", text, count=1, flags=re.MULTILINE)
        text = re.sub(r"^- 辩题：.*$", f"- 标题：{display_title}", text, count=1, flags=re.MULTILINE)
        return text

    def clear_record_artifacts(self, session_id: str) -> dict | None:
        with self._lock:
            session = self._normalize_session(self._read_session_unlocked(session_id))
            if session is None:
                return None
            removable = {self._detail_path(session_id), self._error_path(session_id)}
            for key in ("detail_record_path", "error_record_path"):
                record_path = str(session.get(key) or "").strip()
                if record_path:
                    removable.add(Path(record_path))
            for path in removable:
                path.unlink(missing_ok=True)
            session["detail_record_path"] = None
            session["error_record_path"] = None
            session["updated_at"] = self._now()
            return self._write_session(session)

    def append_detail_note(self, session_id: str, title: str, message: str) -> None:
        """往 detail 记录文件末尾追加一个标题块。"""

        path = self._detail_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return
            with path.open("a", encoding="utf-8") as file:
                file.write(f"## {title}\n\n{message.strip()}\n\n")
            session["detail_record_path"] = str(path)
            session["updated_at"] = self._now()
            self._write_session(session)

    def archive_session(self, session_id: str) -> dict | None:
        with self._lock:
            session = self._normalize_session(self._read_session_unlocked(session_id))
            if session is None:
                return None
            session["archived"] = True
            session["archived_at"] = self._now()
            session["updated_at"] = self._now()
            return self._write_session(session)

    def restore_session(self, session_id: str) -> dict | None:
        with self._lock:
            session = self._normalize_session(self._read_session_unlocked(session_id))
            if session is None:
                return None
            session["archived"] = False
            session["archived_at"] = None
            session["updated_at"] = self._now()
            return self._write_session(session)

    def delete_session(self, session_id: str) -> bool:
        """删除会话 JSON 及其关联日志文件。"""

        with self._lock:
            session = self._normalize_session(self._read_session_unlocked(session_id))
            if session is None:
                return False
            removable = {str(self._detail_path(session_id)), str(self._error_path(session_id))}
            for key in ("detail_record_path", "error_record_path"):
                record_path = session.get(key)
                if record_path:
                    removable.add(str(record_path))
            for record_path in removable:
                Path(record_path).unlink(missing_ok=True)
            self._runtime_config_path(session_id).unlink(missing_ok=True)
            self._session_path(session_id).unlink(missing_ok=True)
            return True

    def list_records(self) -> dict[str, list[dict]]:
        """列出所有现存的 detail / error 记录。"""

        detail_records: list[dict] = []
        error_records: list[dict] = []
        for session in self.list_sessions():
            full_session = self.load_session(session["id"])
            if full_session is None:
                continue
            if self._existing_record_path(full_session, "detail"):
                detail_records.append(
                    {
                        "session_id": full_session["id"],
                        "topic": full_session["topic"],
                        "display_title": self._record_display_title(full_session),
                        "created_at": full_session["created_at"],
                        "status": full_session["status"],
                    }
                )
            if self._existing_record_path(full_session, "error"):
                error_records.append(
                    {
                        "session_id": full_session["id"],
                        "topic": full_session["topic"],
                        "display_title": self._record_display_title(full_session),
                        "created_at": full_session["created_at"],
                        "status": full_session["status"],
                    }
                )
        return {"detail": detail_records, "error": error_records}

    def read_record(self, kind: str, session_id: str) -> dict | None:
        session = self.load_session(session_id)
        if session is None:
            return None
        path = self._existing_record_path(session, kind)
        if path is None:
            return None
        raw_content = path.read_text(encoding="utf-8")
        return {
            "session_id": session_id,
            "topic": session.get("topic"),
            "display_title": self._record_display_title(session),
            "kind": kind,
            "content": self._rewrite_record_content(session, kind, raw_content),
        }

    def delete_record(self, kind: str, session_id: str) -> bool:
        with self._lock:
            session = self._read_session_unlocked(session_id)
            if session is None:
                return False
            if kind == "detail":
                path_key = "detail_record_path"
                path = self._existing_record_path(session, "detail")
            elif kind == "error":
                path_key = "error_record_path"
                path = self._existing_record_path(session, "error")
            else:
                return False
            if path is None:
                return False
            path.unlink(missing_ok=True)
            session[path_key] = None
            session["updated_at"] = self._now()
            self._write_session(session)
            return True
