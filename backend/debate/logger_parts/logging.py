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

from .base import ROLE_LABELS


class LoggingMixin:
    """负责 detail / error 写入，以及实时事件推送。"""

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

    def log_speech(self, role: str, speech: str, round_num: int, conceded: bool = False) -> None:
        """记录某一轮辩手发言。"""

        role_name = ROLE_LABELS.get(role, role)
        suffix = "\n\n> 本轮选择认输。" if conceded else ""
        self._append_detail(f"## 第 {round_num} 轮 · {role_name}\n\n{speech}{suffix}\n\n")
        self._emit(
            {
                "type": "message",
                "role": role,
                "label": role_name,
                "content": speech,
                "round": round_num,
                "conceded": conceded,
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
        self._emit(
            {
                "type": "summary",
                "role": "judge",
                "label": "裁判",
                "content": summary_text,
                "persist": True,
            }
        )

    def log_tool_call(self, role: str, agent_name: str, tool_name: str, args: dict[str, Any], result: Any) -> None:
        """记录一次工具调用。

        注意：工具调用次数本身也计入 usage 统计，但只有 web_search 会增加 search_calls。
        """

        self._append_detail(
            f"### 工具调用 · {agent_name}\n\n"
            f"- 工具：`{tool_name}`\n"
            f"- 参数：{self._code_block(json.dumps(args, ensure_ascii=False, indent=2))}\n"
            f"- 返回：{self._code_block(result)}\n\n"
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
