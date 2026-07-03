"""日志器的业务记录能力。

这个模块专注于“把什么业务事件写进日志，并推给前端”：
- 开场
- 拆题
- 发言
- 总结
- 工具调用
- 原始 LLM I/O
- 普通运行信息
- 报错

把这些方法集中在一起，维护者可以直接把这里理解成“事件到日志的翻译层”。
"""

from __future__ import annotations

import json
from typing import Any

from .base import ROLE_LABELS, TRACKED_ROLES


class LoggingMixin:
    """负责 detail / error 写入，以及实时事件推送。"""

    def _detail_role_key(self, role: str) -> str | None:
        """把角色规整成可挂载消息详情的内部键。"""

        normalizer = getattr(self, "_normalized_role", None)
        role_key = normalizer(role) if callable(normalizer) else str(role or "").strip().lower()
        return role_key if role_key in TRACKED_ROLES else None

    def _append_pending_model_detail(self, role: str, detail: dict[str, Any]) -> None:
        """把一次模型/工具中间步骤暂存到对应角色的下一条可见消息上。"""

        role_key = self._detail_role_key(role)
        if role_key is None:
            return
        self._pending_model_details.setdefault(role_key, []).append(detail)

    def _consume_pending_model_details(self, role: str) -> list[dict[str, Any]]:
        """取出并清空某个角色的待落盘调用链详情。"""

        role_key = self._detail_role_key(role)
        if role_key is None:
            return []
        details = list(self._pending_model_details.get(role_key, []))
        self._pending_model_details[role_key] = []
        return details

    def log_debate_start(
        self,
        topic: str,
        min_rounds: int,
        max_rounds: int,
        config_summary: dict[str, Any],
    ) -> None:
        """记录整场辩论的开场信息。"""

        tracking_note = "已开启" if self.metrics_enabled else "未开启"
        self._append_detail(
            "# 辩论详情记录\n\n"
            f"- 会话 ID：`{self.session_id}`\n"
            f"- 开始时间：{self._now()}\n"
            f"- 辩题：{topic}\n"
            f"- 最少轮数：{min_rounds}\n"
            f"- 最多轮数：{max_rounds}\n"
            f"- Token / 工具统计：{tracking_note}\n\n"
            "## 模型配置快照\n\n"
            f"{self._code_block(json.dumps(config_summary, ensure_ascii=False, indent=2))}\n\n"
        )
        # 开局后第一条前端状态一定是“裁判正在拆题”，这样用户能马上看到系统活着。
        self.log_status("judge", "裁判正在拆解辩题...")

    def log_status(self, role: str, content: str) -> None:
        """发送一条不入库的实时状态消息。"""

        self._emit(
            {
                "type": "status",
                "role": role,
                "label": ROLE_LABELS.get(role, role),
                "content": content,
                "persist": False,
            }
        )

    def log_tasks(self, debate_title: str, topic_analysis: str, pro_task: str, con_task: str) -> None:
        """记录裁判拆题结果。"""

        self._append_detail(
            "## 裁判拆题结果\n\n"
            f"### 本场主题\n\n{debate_title}\n\n"
            f"### 辩题分析\n\n{topic_analysis}\n\n"
            f"### 正方任务\n\n{pro_task}\n\n"
            f"### 反方任务\n\n{con_task}\n\n"
        )
        # 拆题阶段没有对应的前端气泡，避免它的思考详情被挂到最终总结上。
        self._consume_pending_model_details("judge")

    def log_speech(self, role: str, speech: str, round_num: int, conceded: bool = False) -> None:
        """记录某一轮辩手发言。"""

        role_name = ROLE_LABELS.get(role, role)
        suffix = "\n\n> 本轮选择认输。" if conceded else ""
        self._append_detail(f"## 第 {round_num} 轮 · {role_name}\n\n{speech}{suffix}\n\n")
        details = self._consume_pending_model_details(role)
        details.append(
            {
                "kind": "output",
                "title": f"正式输出 · 第 {round_num} 轮",
                "content": speech,
                "conceded": conceded,
            }
        )
        self._emit(
            {
                "type": "message",
                "role": role,
                "label": role_name,
                "content": speech,
                "round": round_num,
                "conceded": conceded,
                "details": details,
                "persist": True,
            }
        )

    def log_summary(
        self,
        winner: str,
        pro_score: Any,
        con_score: Any,
        evaluation: dict[str, Any] | None,
        conclusion: str,
    ) -> None:
        """记录裁判总结与打分。"""

        evaluation = evaluation or {}
        summary_lines = [
            f"胜方：{winner}",
            f"正方得分：{pro_score}",
            f"反方得分：{con_score}",
            "",
            "最终结论：",
            conclusion or "未生成总结。",
        ]
        if evaluation:
            summary_lines.extend(
                [
                    "",
                    f"正方优点：{', '.join(evaluation.get('pro_strengths', [])) or '无'}",
                    f"正方不足：{', '.join(evaluation.get('pro_weaknesses', [])) or '无'}",
                    f"反方优点：{', '.join(evaluation.get('con_strengths', [])) or '无'}",
                    f"反方不足：{', '.join(evaluation.get('con_weaknesses', [])) or '无'}",
                ]
            )

        summary_text = "\n".join(summary_lines).strip()
        self._append_detail(f"## 裁判总结\n\n{summary_text}\n\n")
        details = self._consume_pending_model_details("judge")
        details.append(
            {
                "kind": "output",
                "title": "裁判总结",
                "content": summary_text,
            }
        )
        self._emit(
            {
                "type": "summary",
                "role": "judge",
                "label": "裁判",
                "content": summary_text,
                "details": details,
                "persist": True,
            }
        )

    def log_tool_call(
        self,
        role: str,
        agent_name: str,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        *,
        fallback: bool = False,
    ) -> None:
        """记录一次工具调用。

        注意：工具调用次数本身也计入 usage 统计，但只有 web_search 会增加 search_calls。
        """

        title_prefix = "后端兜底搜索" if fallback else "工具调用"
        self._append_detail(
            f"### {title_prefix} · {agent_name}\n\n"
            f"- 工具：`{tool_name}`\n"
            f"- 类型：{'后端兜底搜索' if fallback else '模型主动工具调用'}\n"
            f"- 参数：{self._code_block(json.dumps(args, ensure_ascii=False, indent=2))}\n"
            f"- 返回：{self._code_block(result)}\n\n"
        )
        self._append_pending_model_detail(
            role,
            {
                "kind": "tool_call",
                "title": f"{title_prefix} · {agent_name}",
                "tool_name": tool_name,
                "args": args,
                "fallback": fallback,
            },
        )
        self._append_pending_model_detail(
            role,
            {
                "kind": "tool_result",
                "title": f"{'兜底返回' if fallback else '工具返回'} · {tool_name}",
                "tool_name": tool_name,
                "result": str(result),
                "fallback": fallback,
            },
        )
        if not self.metrics_enabled:
            return
        role_key = self._normalized_role(role)
        if role_key is None or tool_name != "web_search":
            return
        self._usage_stats["roles"][role_key]["search_calls"] += 1
        self._usage_stats["totals"]["search_calls"] += 1

    def log_llm_raw(self, agent_name: str, prompt: str, response: str) -> None:
        """把原始 Prompt / Response 写入 detail 日志，便于离线排查。"""

        self._append_detail(
            f"### LLM 调用 · {agent_name}\n\n"
            f"#### Prompt\n\n{self._code_block(prompt)}\n\n"
            f"#### Response\n\n{self._code_block(response)}\n\n"
        )

    def log_llm_reasoning(self, role: str, agent_name: str, reasoning_entries: list[dict[str, str]]) -> None:
        """Record provider-returned reasoning / thinking fields into the detail log."""

        if not reasoning_entries:
            return
        structured_entries: list[dict[str, str]] = []
        blocks = [f"### 模型思考信息 · {agent_name}", ""]
        for index, entry in enumerate(reasoning_entries, start=1):
            source = str(entry.get("source") or f"reasoning[{index}]")
            content = str(entry.get("content") or "").strip()
            if not content:
                continue
            structured_entries.append({"source": source, "content": content})
            blocks.extend(
                [
                    f"#### 思考内容 {index}",
                    "",
                    self._code_block(content),
                    "",
                ]
            )
        self._append_detail("\n".join(blocks).strip() + "\n\n")
        if structured_entries:
            self._append_pending_model_detail(
                role,
                {
                    "kind": "reasoning",
                    "title": f"模型思考 · {agent_name}",
                    "entries": structured_entries,
                },
            )

    def log_detail(self, source: str, message: str, data: Any = None) -> None:
        """记录普通运行信息。"""

        body = f"### 运行信息 · {source}\n\n{message}\n"
        if data is not None:
            body += f"\n{self._code_block(data)}\n"
        self._append_detail(body + "\n")

    def log_error(self, error_message: str, traceback_text: str) -> None:
        """同时记录 detail 错误摘要、独立 error 日志，并通知前端。"""

        timestamp = self._now()
        error_markdown = (
            "# 运行错误记录\n\n"
            f"- 会话 ID：`{self.session_id}`\n"
            f"- 时间：{timestamp}\n"
            f"- 辩题：{self.topic}\n\n"
            "## 错误信息\n\n"
            f"{self._code_block(error_message)}\n\n"
            "## Traceback\n\n"
            f"{self._code_block(traceback_text)}\n\n"
        )
        self._append_detail("## 运行错误\n\n" + self._code_block(error_message) + "\n\n")
        self._append_error(error_markdown)
        self._emit(
            {
                "type": "error",
                "role": "system",
                "label": "系统",
                "content": f"辩论运行失败：{error_message}\n请在回放区点击“查看错误”预览错误日志。",
                "persist": True,
            }
        )
