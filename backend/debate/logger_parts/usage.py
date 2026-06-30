"""日志器的资源统计能力。

这个模块只负责 token / 搜索次数的累计与汇总输出。
这样拆分以后，业务日志和资源统计不会互相缠在一起，
后续维护者看起来会更接近“账本模块”。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .base import ROLE_LABELS, TRACKED_ROLES


class UsageLoggerMixin:
    """负责累计模型调用与工具调用的使用量。"""

    def _create_role_usage(self) -> dict[str, Any]:
        """为单个角色创建一份空统计桶。"""

        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "call_count": 0,
            "search_calls": 0,
            "estimated": False,
            "stages": {},
        }

    def _create_usage_stats(self) -> dict[str, Any]:
        """创建整场辩论级别的统计总表。"""

        return {
            "enabled": self.metrics_enabled,
            "has_estimates": False,
            "roles": {role: self._create_role_usage() for role in TRACKED_ROLES},
            "totals": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
                "search_calls": 0,
            },
        }

    def _normalized_role(self, role: str) -> str | None:
        """把任意角色文本规整成可统计的内部角色键。"""

        role_key = str(role or "").strip().lower()
        return role_key if role_key in TRACKED_ROLES else None

    def _stage_bucket(self, role_stats: dict[str, Any], stage: str) -> dict[str, Any]:
        """返回某个角色下某个阶段的统计桶，没有就现场创建。"""

        stage_key = str(stage or "模型调用").strip() or "模型调用"
        stages = role_stats.setdefault("stages", {})
        if stage_key not in stages:
            stages[stage_key] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
                "estimated": False,
            }
        return stages[stage_key]

    def record_llm_usage(
        self,
        role: str,
        stage: str,
        usage: dict[str, Any] | None,
        *,
        estimated: bool = False,
    ) -> None:
        """记录一次 LLM 调用的 token 消耗。

        这里既写角色总账，也写阶段分账。
        这样后续既能在 UI 上看整场累计，也能排查“究竟哪一步最耗 token”。
        """

        if not self.metrics_enabled:
            return
        role_key = self._normalized_role(role)
        if role_key is None or not isinstance(usage, dict):
            return

        # usage 来源可能来自不同模型 SDK，所以这里统一做兜底归一化。
        input_tokens = max(0, int(usage.get("input_tokens") or 0))
        output_tokens = max(0, int(usage.get("output_tokens") or 0))
        total_tokens = max(0, int(usage.get("total_tokens") or (input_tokens + output_tokens)))

        role_stats = self._usage_stats["roles"][role_key]
        role_stats["input_tokens"] += input_tokens
        role_stats["output_tokens"] += output_tokens
        role_stats["total_tokens"] += total_tokens
        role_stats["call_count"] += 1
        role_stats["estimated"] = bool(role_stats.get("estimated") or estimated)

        stage_stats = self._stage_bucket(role_stats, stage)
        stage_stats["input_tokens"] += input_tokens
        stage_stats["output_tokens"] += output_tokens
        stage_stats["total_tokens"] += total_tokens
        stage_stats["call_count"] += 1
        stage_stats["estimated"] = bool(stage_stats.get("estimated") or estimated)

        totals = self._usage_stats["totals"]
        totals["input_tokens"] += input_tokens
        totals["output_tokens"] += output_tokens
        totals["total_tokens"] += total_tokens
        totals["call_count"] += 1
        self._usage_stats["has_estimates"] = bool(self._usage_stats.get("has_estimates") or estimated)

    def build_usage_summary(self) -> dict[str, Any]:
        """返回一份可安全暴露到外部的 usage 快照。"""

        if not self.metrics_enabled:
            return {"enabled": False}
        return deepcopy(self._usage_stats)

    def log_usage_summary(self) -> None:
        """把累计 usage 以 Markdown 的形式写入 detail 日志。"""

        if not self.metrics_enabled:
            return

        lines = ["## Token 与工具统计", ""]
        for role in TRACKED_ROLES:
            role_stats = self._usage_stats["roles"][role]
            role_name = ROLE_LABELS.get(role, role)
            estimated_suffix = "（估算）" if role_stats.get("estimated") else ""
            lines.extend(
                [
                    f"### {role_name}",
                    "",
                    f"- 总 Token：{role_stats.get('total_tokens', 0)}{estimated_suffix}",
                    f"- 输入 Token：{role_stats.get('input_tokens', 0)}",
                    f"- 输出 Token：{role_stats.get('output_tokens', 0)}",
                    f"- 模型调用：{role_stats.get('call_count', 0)} 次",
                    f"- 网络搜索调用：{role_stats.get('search_calls', 0)} 次",
                ]
            )

            stages = role_stats.get("stages") or {}
            if stages:
                lines.extend(["", "阶段明细："])
                for stage_name, stage_stats in stages.items():
                    stage_suffix = "（估算）" if stage_stats.get("estimated") else ""
                    lines.append(
                        f"- {stage_name}：总 {stage_stats.get('total_tokens', 0)}{stage_suffix}，"
                        f"输入 {stage_stats.get('input_tokens', 0)}，"
                        f"输出 {stage_stats.get('output_tokens', 0)}，"
                        f"调用 {stage_stats.get('call_count', 0)} 次"
                    )
            lines.append("")

        totals = self._usage_stats["totals"]
        overall_suffix = "（含估算）" if self._usage_stats.get("has_estimates") else ""
        lines.extend(
            [
                "### 全部合计",
                "",
                f"- 总 Token：{totals.get('total_tokens', 0)}{overall_suffix}",
                f"- 输入 Token：{totals.get('input_tokens', 0)}",
                f"- 输出 Token：{totals.get('output_tokens', 0)}",
                f"- 模型调用：{totals.get('call_count', 0)} 次",
                f"- 网络搜索调用：{totals.get('search_calls', 0)} 次",
                "",
            ]
        )
        self._append_detail("\n".join(lines).strip() + "\n\n")
