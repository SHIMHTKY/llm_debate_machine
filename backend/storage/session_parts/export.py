"""Markdown 导出相关逻辑。"""

from __future__ import annotations

from pathlib import Path


class SessionExportMixin:
    """负责把 session 渲染成 simple / detail 两类 Markdown。"""

    def _session_display_title(self, session: dict) -> str:
        """返回记录与导出优先使用的显示标题。"""

        runtime_state = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
        return str(runtime_state.get("debate_title") or session.get("topic") or "").strip()

    def _role_display_name(self, session: dict, role: str, fallback: str) -> str:
        if role == "user":
            return fallback or "用户消息"
        config_summary = session.get("config_summary") or {}
        config = config_summary.get(role, {}) if isinstance(config_summary, dict) else {}
        if not isinstance(config, dict):
            config = {}
        model_name = str(config.get("model") or config.get("azure_deployment") or "").strip()
        return f"{fallback} · {model_name}" if model_name else fallback

    def _conversation_participants(self, session: dict) -> list[dict]:
        participants = session.get("participants")
        return participants if isinstance(participants, list) else []

    def _user_target_badge(self, target_role: str | None) -> str:
        role = str(target_role or "").strip().lower()
        if role == "pro":
            return "发送正方"
        if role == "con":
            return "发送反方"
        return ""

    def _read_optional_text(self, path_str: str | None) -> str:
        if not path_str:
            return ""
        path = Path(path_str)
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _append_usage_lines(self, lines: list[str], usage_stats: dict | None) -> None:
        """把 usage 统计渲染成 Markdown 小节。"""

        if not isinstance(usage_stats, dict) or not usage_stats.get("enabled"):
            return
        roles = usage_stats.get("roles") if isinstance(usage_stats.get("roles"), dict) else {}
        role_labels = {"judge": "裁判", "pro": "正方", "con": "反方"}
        lines.extend(["", "## Token 与工具统计", ""])
        for role in ("pro", "con", "judge"):
            role_stats = roles.get(role, {}) if isinstance(roles.get(role), dict) else {}
            suffix = "（估算）" if role_stats.get("estimated") else ""
            lines.extend(
                [
                    f"### {role_labels[role]}",
                    "",
                    f"- 总 Token：{role_stats.get('total_tokens', 0)}{suffix}",
                    f"- 输入 Token：{role_stats.get('input_tokens', 0)}",
                    f"- 输出 Token：{role_stats.get('output_tokens', 0)}",
                    f"- 模型调用：{role_stats.get('call_count', 0)} 次",
                    f"- 网络搜索调用：{role_stats.get('search_calls', 0)} 次",
                    "",
                ]
            )

    def _simple_export_markdown(self, session: dict) -> str:
        """导出面向普通阅读者的简版 Markdown。"""

        status = str(session.get("status") or "未知")
        result = session.get("result") or {}
        display_title = self._session_display_title(session)
        lines = [
            f"# 详情·{display_title or '记录查看'}",
            "",
            f"- 会话 ID：`{session.get('id', '')}`",
            f"- 标题：{display_title}",
            f"- 状态：{status}",
            f"- 开始时间：{session.get('created_at') or '--'}",
            f"- 结束时间：{session.get('finished_at') or '--'}",
            f"- 最少轮数：{session.get('min_rounds') or '--'}",
            f"- 最多轮数：{session.get('max_rounds') or '--'}",
        ]

        if str(session.get("kind") or "debate") == "conversation":
            lines = [
                f"# 模型自由对话·{display_title or '记录查看'}",
                "",
                f"- 会话 ID：{session.get('id', '')}",
                f"- 标题：{display_title}",
                f"- 状态：{status}",
                f"- 开始时间：{session.get('created_at') or '--'}",
                f"- 结束时间：{session.get('finished_at') or '--'}",
                "",
                "## 初始提示词",
                "",
                str(session.get("topic") or "").strip(),
                "",
                "## 模型链路",
                "",
            ]
            for index, participant in enumerate(self._conversation_participants(session), start=1):
                label = str(participant.get("name") or participant.get("model") or f"模型 {index}")
                lines.append(f"{index}. {label}")
            if status == "error":
                lines.extend(["", "## 错误信息", "", str(session.get("error_message") or "未提供错误信息。")])
            elif status == "terminated":
                lines.extend(["", "## 终止说明", "", str(session.get("termination_message") or "用户手动终止。")])
            self._append_conversation_usage_lines(lines, session.get("usage_stats"))
            messages = [item for item in (session.get("messages") or []) if item.get("type") != "status"]
            if messages:
                lines.extend(["", "## 对话记录", ""])
                for message in messages:
                    label = str(message.get("label") or message.get("role") or "模型")
                    lines.extend([f"### {label}", "", str(message.get("content") or "（空）").strip(), ""])
            return "\n".join(lines).strip() + "\n"

        config_summary = session.get("config_summary") or {}
        if isinstance(config_summary, dict) and config_summary:
            lines.extend(["", "## 模型快照", ""])
            role_labels = {"judge": "裁判", "pro": "正方", "con": "反方"}
            for role in ("judge", "pro", "con"):
                config = config_summary.get(role, {}) if isinstance(config_summary.get(role), dict) else {}
                provider = config.get("provider") or "--"
                model_name = config.get("model") or config.get("azure_deployment") or "--"
                lines.append(f"- {role_labels[role]}：{model_name}（{provider}）")

        if status == "error":
            lines.extend(
                [
                    "",
                    "## 运行结果",
                    "",
                    "### 错误信息",
                    "",
                    "```text",
                    str(session.get("error_message") or "未提供错误信息。"),
                    "```",
                ]
            )
            if session.get("error_traceback"):
                lines.extend(
                    [
                        "",
                        "### Traceback",
                        "",
                        "```text",
                        str(session.get("error_traceback") or "").strip(),
                        "```",
                    ]
                )
        elif status == "terminated":
            lines.extend(["", "## 运行结果", "", "### 终止说明", "", str(session.get("termination_message") or "用户手动终止。")])
        elif status == "paused":
            lines.extend(["", "## 运行结果", "", "### 当前状态", "", "本场辩论已暂停，可继续恢复。"])
        else:
            lines.extend(
                [
                    "",
                    "## 裁判结论",
                    "",
                    f"- 判定：{result.get('winner') or '待定'}",
                    f"- 正方得分：{result.get('pro_score', '--')}",
                    f"- 反方得分：{result.get('con_score', '--')}",
                    "",
                    "### 最终总结",
                    "",
                    str(result.get("conclusion") or "未生成总结。"),
                ]
            )

        self._append_usage_lines(lines, session.get("usage_stats"))

        messages = session.get("messages") or []
        visible_messages = [item for item in messages if item.get("type") != "status"]
        if visible_messages:
            lines.extend(["", "## 辩论回放", ""])
            for message in visible_messages:
                role = str(message.get("role") or "system")
                label = str(message.get("label") or "系统")
                if role == "pro":
                    label = self._role_display_name(session, "pro", label)
                elif role == "con":
                    label = self._role_display_name(session, "con", label)
                heading = label
                if role == "user":
                    target_badge = self._user_target_badge(message.get("target_role"))
                    if target_badge:
                        heading += f" · {target_badge}"
                if message.get("round"):
                    heading += f" · 第 {message.get('round')} 轮"
                lines.extend([f"### {heading}", "", str(message.get("content") or "（空）").strip(), ""])

        return "\n".join(lines).strip() + "\n"

    def _append_conversation_usage_lines(self, lines: list[str], usage_stats: dict | None) -> None:
        if not isinstance(usage_stats, dict) or not usage_stats.get("enabled"):
            return
        lines.extend(["", "## Token 统计", ""])
        participants = usage_stats.get("participants") if isinstance(usage_stats.get("participants"), list) else []
        for participant in participants:
            lines.extend([
                f"### {participant.get('label') or '模型'}",
                "",
                f"- 总 Token：{participant.get('total_tokens', 0)}（{'估算' if participant.get('estimated') else '实际'}）",
                f"- 输入 Token：{participant.get('input_tokens', 0)}",
                f"- 输出 Token：{participant.get('output_tokens', 0)}",
                "",
            ])

    def _detail_export_markdown(self, session: dict) -> str:
        """导出 detail 日志 + error 日志的组合版本。"""

        detail_text = self._read_optional_text(session.get("detail_record_path") or str(self._detail_path(session.get("id", ""))))
        error_text = self._read_optional_text(session.get("error_record_path") or str(self._error_path(session.get("id", ""))))

        sections: list[str] = []
        if detail_text:
            sections.append(detail_text)
        else:
            sections.append(self._simple_export_markdown(session).strip())

        if error_text:
            sections.append(error_text)

        return "\n\n---\n\n".join(section.strip() for section in sections if section.strip()).strip() + "\n"

    def export_session_markdown(self, session_id: str, export_kind: str) -> dict[str, str] | None:
        session = self.load_session(session_id)
        if session is None:
            return None
        if export_kind == "simple":
            content = self._simple_export_markdown(session)
        elif export_kind == "detail":
            content = self._detail_export_markdown(session)
        else:
            return None
        return {
            "filename": f"{session_id}-{export_kind}.md",
            "content": content,
        }
