"""manager 内部大量会复用的小型辅助方法。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...config.settings import load_settings
from .. import manager_support as support
from .base import DebateResumeError, DebateStateError


class SupportManagerMixin:
    """把纯辅助逻辑收口成 manager 内部可调用的方法。"""

    def _normalize_target_role(self, target_role: Any) -> str | None:
        return support.normalize_target_role(target_role)

    def _required_response_roles(self, target_role: str | None) -> list[str]:
        return support.required_response_roles(target_role)

    def _user_target_badge(self, target_role: str | None) -> str:
        return support.user_target_badge(target_role)

    def _format_user_detail_message(self, content: str, target_role: str | None) -> str:
        return support.format_user_detail_message(content, target_role)

    def _create_user_message_payload(
        self,
        message_id: str,
        content: str,
        *,
        locked: bool,
        target_role: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        return support.create_user_message_payload(
            message_id,
            content,
            locked=locked,
            target_role=target_role,
            timestamp=timestamp,
        )

    def _create_user_history_item(self, message_id: str, content: str, *, locked: bool, target_role: str | None = None) -> dict[str, Any]:
        return support.create_user_history_item(message_id, content, locked=locked, target_role=target_role)

    def _build_runtime_from_session(self, session: dict[str, Any]) -> dict[str, Any]:
        return support.build_runtime_from_session(session)

    def _empty_usage_stage_stats(self) -> dict[str, Any]:
        return support.empty_usage_stage_stats()

    def _empty_usage_role_stats(self) -> dict[str, Any]:
        return support.empty_usage_role_stats()

    def _empty_usage_summary(self, *, enabled: bool) -> dict[str, Any]:
        return support.empty_usage_summary(enabled=enabled)

    def _combine_usage_summaries(self, existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any] | None:
        return support.combine_usage_summaries(existing, incoming)

    def _diff_usage_summaries(self, previous: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any] | None:
        return support.diff_usage_summaries(previous, current)

    def _append_usage_timeline_entry(
        self,
        runtime: dict[str, Any],
        *,
        phase: str,
        usage_delta: dict[str, Any] | None,
        message_id: str | None = None,
    ) -> None:
        support.append_usage_timeline_entry(runtime, phase=phase, usage_delta=usage_delta, message_id=message_id)

    def _resolve_new_message_id(self, session_id: str, previous_message_ids: set[str]) -> str | None:
        """从落盘后的 messages 中识别本轮新追加的那条消息。"""

        session = self.store.load_session(session_id) or {}
        messages = session.get("messages") if isinstance(session.get("messages"), list) else []
        new_ids = [
            str(message.get("id") or "").strip()
            for message in messages
            if str(message.get("id") or "").strip() and str(message.get("id") or "").strip() not in previous_message_ids
        ]
        return new_ids[-1] if new_ids else None

    def _attach_message_usage(self, session_id: str, message_id: str, usage_delta: dict[str, Any], phase: str) -> None:
        """把某个阶段产生的 usage 增量挂回对应消息，便于后续截断回算。"""

        if not message_id or not isinstance(usage_delta, dict) or not usage_delta.get("enabled"):
            return

        self.store.update_session(
            session_id,
            lambda current: {
                **current,
                "messages": [
                    {
                        **message,
                        **(
                            {
                                "usage_delta": deepcopy(usage_delta),
                                "usage_phase": phase,
                            }
                            if str(message.get("id") or "") == message_id
                            else {}
                        ),
                    }
                    for message in (current.get("messages") or [])
                ],
            },
        )

    def _rebuild_usage_tracking(
        self,
        session: dict[str, Any],
        kept_messages: list[dict[str, Any]],
        rebuilt_runtime: dict[str, Any],
    ) -> dict[str, Any] | None:
        return support.rebuild_usage_tracking(session, kept_messages, rebuilt_runtime)

    def _find_preset_by_name(self, settings: dict[str, Any], preset_name: str) -> dict[str, Any] | None:
        return support.find_preset_by_name(settings, preset_name)

    def _build_resume_settings(self, session: dict[str, Any]) -> dict[str, Any]:
        """恢复辩论时，强制按照原会话快照绑定的辩手配置继续执行。"""

        settings = load_settings()
        summary = session.get("config_summary") or {}
        pro_name = str(((summary.get("pro") or {}) if isinstance(summary, dict) else {}).get("preset_name") or "").strip()
        con_name = str(((summary.get("con") or {}) if isinstance(summary, dict) else {}).get("preset_name") or "").strip()

        pro_preset = self._find_preset_by_name(settings, pro_name)
        if pro_preset is None:
            raise DebateResumeError(f"请恢复{pro_name or '正方'}辩手配置后继续辩论。")
        con_preset = self._find_preset_by_name(settings, con_name)
        if con_preset is None:
            raise DebateResumeError(f"请恢复{con_name or '反方'}辩手配置后继续辩论。")

        pro_preset["preset_id"] = str(pro_preset.get("id") or "")
        pro_preset["preset_name"] = pro_name or str(pro_preset.get("name") or "")
        con_preset["preset_id"] = str(con_preset.get("id") or "")
        con_preset["preset_name"] = con_name or str(con_preset.get("name") or "")

        return {
            "judge": deepcopy(settings.get("judge") or {}),
            "pro": pro_preset,
            "con": con_preset,
            "tool_configs": deepcopy(settings.get("tool_configs") or []),
            "debater_presets": deepcopy(settings.get("debater_presets") or []),
            "pro_preset_id": pro_preset["preset_id"],
            "con_preset_id": con_preset["preset_id"],
            "context_rounds": (summary.get("context_rounds") if isinstance(summary, dict) else None) or settings.get("context_rounds", 3),
            "usage_tracking_enabled": bool(
                (summary.get("usage_tracking_enabled") if isinstance(summary, dict) else None)
                if isinstance(summary, dict) and "usage_tracking_enabled" in summary
                else settings.get("usage_tracking_enabled")
            ),
        }

    def _is_judge_phase(self, session: dict[str, Any]) -> bool:
        return support.is_judge_phase(session)

    def _session_display_title(self, session: dict[str, Any]) -> str:
        return support.session_display_title(session)

    def _mark_pending_user_requirements_responded(self, history: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
        return support.mark_pending_user_requirements_responded(history, role)

    def _rebuild_runtime_from_messages(
        self,
        session: dict[str, Any],
        kept_messages: list[dict[str, Any]],
        next_phase: str,
        *,
        title_override: str | None = None,
    ) -> dict[str, Any]:
        return support.rebuild_runtime_from_messages(session, kept_messages, next_phase, title_override=title_override)

    def _resolve_rewind_phase(self, message: dict[str, Any]) -> str:
        try:
            return support.resolve_rewind_phase(message)
        except RuntimeError as exc:
            raise DebateStateError(str(exc)) from exc

    def _restore_trailing_user_message(self, kept_messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        return support.restore_trailing_user_message(kept_messages)

    def _resolve_rewind_target(self, session: dict[str, Any], message_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
        try:
            return support.resolve_rewind_target(session, message_id)
        except RuntimeError as exc:
            raise DebateStateError(str(exc)) from exc

    def _merge_usage_stats(self, session_id: str, usage_stats: dict[str, Any] | None) -> dict[str, Any] | None:
        """把一次运行中累计到的 usage 合并进会话总统计。"""

        if not isinstance(usage_stats, dict):
            return self.store.load_session(session_id)

        current_session = self.store.load_session(session_id) or {}
        existing = current_session.get("usage_stats")
        merged = self._combine_usage_summaries(existing if isinstance(existing, dict) else None, usage_stats)
        if merged is None:
            return current_session
        self.store.set_usage_stats(session_id, merged)
        return self.store.load_session(session_id)
