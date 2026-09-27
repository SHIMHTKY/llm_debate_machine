"""截断撤回与从记录恢复副本。"""

from __future__ import annotations

from copy import deepcopy

from .base import DebateCapacityError, DebateStateError


class RewindManagerMixin:
    """管理“撤回到某条消息之前”和“从记录恢复副本”两类能力。"""

    def _replace_session_with_rewind_state(
        self,
        session_id: str,
        kept_messages: list[dict],
        rebuilt_runtime: dict,
        rebuilt_usage_stats: dict | None,
        restored_active_user_message: dict | None,
    ) -> dict | None:
        """把原会话直接替换成截断后的暂停状态。"""

        updated = self.store.update_session(
            session_id,
            lambda current: {
                **current,
                "status": "paused",
                "messages": deepcopy(kept_messages),
                "live_status": None,
                "result": None,
                "error_message": None,
                "error_traceback": None,
                "termination_message": None,
                "finished_at": None,
                "runtime_state": deepcopy(rebuilt_runtime),
                "active_user_message": deepcopy(restored_active_user_message),
                "usage_stats": deepcopy(rebuilt_usage_stats) if isinstance(rebuilt_usage_stats, dict) else None,
                "detail_record_path": None,
                "error_record_path": None,
            },
        )
        self.store.clear_record_artifacts(session_id)
        return self.store.load_session(session_id) if updated is not None else None

    def _create_rewind_clone(
        self,
        source_session: dict,
        kept_messages: list[dict],
        rebuilt_runtime: dict,
        rebuilt_usage_stats: dict | None,
        restored_active_user_message: dict | None,
    ) -> dict:
        """创建“原标题-恢复”的暂停副本，不改原记录。"""

        source_title = self._session_display_title(source_session) or str(source_session.get("topic") or "恢复辩论")
        clone_title = f"{source_title}-恢复"
        cloned_runtime = deepcopy(rebuilt_runtime)
        cloned_runtime["debate_title"] = clone_title

        session = self.store.create_session(
            topic=str(source_session.get("topic") or ""),
            min_rounds=int(source_session.get("min_rounds") or 1),
            max_rounds=int(source_session.get("max_rounds") or 1),
            config_summary=deepcopy(source_session.get("config_summary") or {}),
        )
        updated = self.store.update_session(
            session["id"],
            lambda current: {
                **current,
                "status": "paused",
                "messages": deepcopy(kept_messages),
                "runtime_state": deepcopy(cloned_runtime),
                "live_status": None,
                "result": None,
                "error_message": None,
                "error_traceback": None,
                "termination_message": None,
                "finished_at": None,
                "usage_stats": deepcopy(rebuilt_usage_stats) if isinstance(rebuilt_usage_stats, dict) else None,
                "active_user_message": deepcopy(restored_active_user_message),
            },
        )
        return updated or session

    async def rewind_debate(self, session_id: str, message_id: str, *, clone: bool = False) -> dict | None:
        """处理“运行中撤回”和“已完成记录恢复副本”两条路径。"""

        session = self.store.load_session(session_id)
        if session is None:
            return None

        try:
            if clone:
                if str(session.get("status") or "") != "completed":
                    raise DebateStateError("只有已完成的辩论记录支持创建恢复副本。")
                _, kept_messages, rebuilt_runtime, restored_active_user_message = self._resolve_rewind_target(session, message_id)
                rebuilt_usage_stats = self._rebuild_usage_tracking(session, kept_messages, rebuilt_runtime)
                return self._create_rewind_clone(
                    session,
                    kept_messages,
                    rebuilt_runtime,
                    rebuilt_usage_stats,
                    restored_active_user_message,
                )

            if str(session.get("status") or "") not in {"queued", "running", "paused"}:
                raise DebateStateError("只有进行中或暂停中的辩论支持截断撤回。")

            if self.is_running(session_id):
                await self.pause_debate(session_id, reason="用户手动截断撤回")
                session = self.store.load_session(session_id)
                if session is None:
                    return None

            _, kept_messages, rebuilt_runtime, restored_active_user_message = self._resolve_rewind_target(session, message_id)
            rebuilt_usage_stats = self._rebuild_usage_tracking(session, kept_messages, rebuilt_runtime)
            updated = self._replace_session_with_rewind_state(
                session_id,
                kept_messages,
                rebuilt_runtime,
                rebuilt_usage_stats,
                restored_active_user_message,
            )
            if updated is not None:
                self._publish_session_state(session_id)
            return updated
        except DebateCapacityError:
            raise
        except DebateStateError:
            raise
        except RuntimeError as exc:
            raise DebateStateError(str(exc)) from exc
