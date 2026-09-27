"""用户插话、撤回修改与标题编辑。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import uuid

from .base import DebateStateError


class SessionMessageManagerMixin:
    """处理暂停 / 运行状态下的用户插话与标题编辑。"""

    def _materialize_active_user_message(self, session_id: str, runtime: dict) -> dict:
        """把运行中排队的用户消息真正插入 runtime 与消息流。"""

        session = self.store.load_session(session_id)
        if session is None:
            return runtime
        active = session.get("active_user_message") or {}
        if str(active.get("stage") or "") != "queued":
            return runtime

        message_id = str(active.get("id") or "")
        content = str(active.get("content") or "").strip()
        target_role = self._normalize_target_role(active.get("target_role"))
        timestamp = str(active.get("created_at") or "").strip() or None
        if not message_id or not content:
            return runtime

        updated_runtime = deepcopy(runtime)
        updated_runtime.setdefault("debate_history", []).append(
            self._create_user_history_item(message_id, content, locked=True, target_role=target_role)
        )
        self.store.update_session(
            session_id,
            lambda current: {
                **current,
                "runtime_state": deepcopy(updated_runtime),
                "active_user_message": None,
                "messages": [
                    *(current.get("messages") or []),
                    self._create_user_message_payload(
                        message_id,
                        content,
                        locked=True,
                        target_role=target_role,
                        timestamp=timestamp,
                    ),
                ],
            },
        )
        self.store.append_detail_note(session_id, "用户插入消息", self._format_user_detail_message(content, target_role))
        self._publish_session_state(session_id)
        return updated_runtime

    def _lock_draft_user_message(self, session_id: str) -> dict | None:
        """把暂停态下的草稿用户消息锁死，准备继续辩论。"""

        locked_message: dict[str, str | None] = {}

        def updater(session: dict) -> dict:
            active = session.get("active_user_message") or {}
            if str(active.get("stage") or "") != "draft":
                return session

            message_id = str(active.get("id") or "")
            content = str(active.get("content") or "").strip()
            target_role = self._normalize_target_role(active.get("target_role"))
            if not message_id or not content:
                session["active_user_message"] = None
                return session

            runtime = deepcopy(session.get("runtime_state") or {})
            history = runtime.get("debate_history") if isinstance(runtime.get("debate_history"), list) else []
            for item in history:
                if str(item.get("id") or "") == message_id:
                    item["locked"] = True

            messages = session.get("messages") or []
            for message in messages:
                if str(message.get("id") or "") == message_id:
                    message["locked"] = True

            runtime["debate_history"] = history
            session["runtime_state"] = runtime
            session["active_user_message"] = None
            locked_message.update({"id": message_id, "content": content, "target_role": target_role})
            return session

        updated = self.store.update_session(session_id, updater)
        if updated is not None and locked_message.get("content"):
            self.store.append_detail_note(
                session_id,
                "用户插入消息",
                self._format_user_detail_message(str(locked_message["content"]), self._normalize_target_role(locked_message.get("target_role"))),
            )
            self._publish_session_state(session_id)
        return updated

    async def add_user_message(self, session_id: str, content: str, target_role: str | None = None) -> dict | None:
        """在运行中或暂停中插入一条用户消息。"""

        session = self.store.load_session(session_id)
        if session is None:
            return None

        message_text = str(content or "").strip()
        normalized_target_role = self._normalize_target_role(target_role)
        if not message_text:
            raise DebateStateError("用户消息不能为空。")
        if str(session.get("status") or "") not in {"queued", "running", "paused"}:
            raise DebateStateError("只有运行中或暂停中的辩论可以插入用户消息。")
        if self._is_judge_phase(session):
            raise DebateStateError("裁判正在拆解辩题或进行总结，当前阶段不能插入用户发言。")
        if session.get("active_user_message"):
            raise DebateStateError("请先撤回当前用户发言后再发送新消息。")

        message_id = uuid.uuid4().hex
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        if session.get("status") == "paused":
            user_message = self._create_user_message_payload(
                message_id,
                message_text,
                locked=False,
                target_role=normalized_target_role,
                timestamp=created_at,
            )
            history_item = self._create_user_history_item(
                message_id,
                message_text,
                locked=False,
                target_role=normalized_target_role,
            )
            updated = self.store.update_session(
                session_id,
                lambda current: {
                    **current,
                    "runtime_state": {
                        **(deepcopy(current.get("runtime_state")) or self._build_runtime_from_session(current)),
                        "debate_history": [
                            *(
                                deepcopy((current.get("runtime_state") or {}).get("debate_history"))
                                if isinstance((current.get("runtime_state") or {}).get("debate_history"), list)
                                else deepcopy(self._build_runtime_from_session(current).get("debate_history", []))
                            ),
                            history_item,
                        ],
                    },
                    "active_user_message": {
                        "id": message_id,
                        "content": message_text,
                        "target_role": normalized_target_role,
                        "created_at": created_at,
                        "stage": "draft",
                    },
                    "messages": [*(current.get("messages") or []), user_message],
                },
            )
        else:
            updated = self.store.update_session(
                session_id,
                lambda current: {
                    **current,
                    "active_user_message": {
                        "id": message_id,
                        "content": message_text,
                        "target_role": normalized_target_role,
                        "created_at": created_at,
                        "stage": "queued",
                    },
                },
            )

        if updated is not None:
            self._publish_session_state(session_id)
        return updated

    async def retract_user_message(self, session_id: str) -> dict | None:
        """撤回当前仍可编辑 / 待插入的用户消息。"""

        session = self.store.load_session(session_id)
        if session is None:
            return None
        active = session.get("active_user_message") or {}
        stage = str(active.get("stage") or "")
        if stage not in {"queued", "draft"}:
            raise DebateStateError("当前没有可撤回的用户消息。")

        message_id = str(active.get("id") or "")
        content = str(active.get("content") or "")
        target_role = self._normalize_target_role(active.get("target_role"))
        if stage == "draft":
            updated = self.store.update_session(
                session_id,
                lambda current: {
                    **current,
                    "runtime_state": {
                        **(deepcopy(current.get("runtime_state")) or self._build_runtime_from_session(current)),
                        "debate_history": [
                            item
                            for item in (
                                deepcopy((current.get("runtime_state") or {}).get("debate_history"))
                                if isinstance((current.get("runtime_state") or {}).get("debate_history"), list)
                                else deepcopy(self._build_runtime_from_session(current).get("debate_history", []))
                            )
                            if str(item.get("id") or "") != message_id
                        ],
                    },
                    "active_user_message": None,
                    "messages": [
                        message
                        for message in (current.get("messages") or [])
                        if str(message.get("id") or "") != message_id
                    ],
                },
            )
        else:
            updated = self.store.update_session(
                session_id,
                lambda current: {
                    **current,
                    "active_user_message": None,
                },
            )

        if updated is not None:
            self._publish_session_state(session_id)
        return {"session": updated, "content": content, "target_role": target_role} if updated is not None else None

    async def update_debate_title(self, session_id: str, title: str) -> dict | None:
        """更新当前会话展示标题，不改原始辩题。"""

        session = self.store.load_session(session_id)
        if session is None:
            return None

        next_title = str(title or "").strip()
        if not next_title:
            raise DebateStateError("标题不能为空。")

        updated = self.store.update_session(
            session_id,
            lambda current: {
                **current,
                "runtime_state": {
                    **(deepcopy(current.get("runtime_state")) or self._build_runtime_from_session(current)),
                    "debate_title": next_title,
                },
            },
        )
        if updated is not None:
            self._publish_session_state(session_id)
        return updated
