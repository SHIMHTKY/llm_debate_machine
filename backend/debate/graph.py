"""兼容层：保留旧的 graph 导入路径，但内部实现已经改成线性 pipeline。

历史上这个文件承载了整套 LangGraph 风格实现。
现在真实逻辑已经拆入 `backend.debate.pipeline` 目录，按职责分层后更容易维护。

仍然保留本文件，原因只有一个：
不打断旧导入路径。

也就是说，项目里历史代码仍然可以继续写：
- `from backend.debate.graph import judge_initialize`
- `build_debate_graph(...).ainvoke(state)`

但底层不再返回 LangGraph，而是返回一个“线性执行兼容对象”。
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from .engine import create_runtime_state, determine_next_phase, merge_runtime_state, prepare_runtime_context
from .logger import DebateLogger
from .pipeline.history import check_after_pro, check_continue
from .pipeline.phases_debater import con_first_speech, con_speech, pro_first_speech, pro_speech
from .pipeline.phases_judge import judge_initialize, judge_summary


class LinearDebateGraph:
    """兼容旧 `build_debate_graph().ainvoke(...)` 调用方式的轻量包装器。"""

    def __init__(self, logger: DebateLogger, settings: dict[str, Any]) -> None:
        self.logger = logger
        # 这里提前把 settings 变成上下文，避免每一轮重复建模实例和工具实例。
        self.context = prepare_runtime_context(settings)

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        """线性跑完整场辩论，直到 phase 进入 `completed`。"""

        runtime = deepcopy(state)
        while str(runtime.get("phase") or "judge_initialize") != "completed":
            phase = str(runtime.get("phase") or "judge_initialize")

            if phase == "judge_initialize":
                updates = await judge_initialize(runtime, self.logger, self.context["judge_llm"])
            elif phase == "pro_first_speech":
                updates = await pro_first_speech(
                    runtime,
                    self.logger,
                    self.context["pro_llm"],
                    self.context["pro_tools"],
                    self.context["pro_tool_mode"],
                    self.context["pro_max_tool_rounds"],
                )
            elif phase == "con_first_speech":
                updates = await con_first_speech(
                    runtime,
                    self.logger,
                    self.context["con_llm"],
                    self.context["con_tools"],
                    self.context["con_tool_mode"],
                    self.context["con_max_tool_rounds"],
                )
            elif phase == "pro_speech":
                updates = await pro_speech(
                    runtime,
                    self.logger,
                    self.context["pro_llm"],
                    self.context["pro_tools"],
                    self.context["pro_tool_mode"],
                    self.context["history_window_size"],
                    self.context["pro_max_tool_rounds"],
                )
            elif phase == "con_speech":
                updates = await con_speech(
                    runtime,
                    self.logger,
                    self.context["con_llm"],
                    self.context["con_tools"],
                    self.context["con_tool_mode"],
                    self.context["history_window_size"],
                    self.context["con_max_tool_rounds"],
                )
            elif phase == "judge_summary":
                updates = await judge_summary(runtime, self.logger, self.context["judge_llm"])
            else:
                raise RuntimeError(f"未知辩论阶段：{phase}")

            # 先把当前阶段的输出并回 runtime。
            runtime = merge_runtime_state(runtime, updates)
            # 再明确计算下一阶段，而不是把跳转逻辑塞在阶段函数内部。
            runtime["phase"] = determine_next_phase(runtime, phase)

        return runtime

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        """同步兼容入口，给少量旧调用方使用。"""

        return asyncio.run(self.ainvoke(state))


def build_debate_graph(logger: DebateLogger, settings: dict[str, Any]) -> LinearDebateGraph:
    """保留旧工厂名，但底层已改成线性执行器。"""

    return LinearDebateGraph(logger, settings)


__all__ = [
    "LinearDebateGraph",
    "build_debate_graph",
    "check_after_pro",
    "check_continue",
    "con_first_speech",
    "con_speech",
    "create_runtime_state",
    "judge_initialize",
    "judge_summary",
    "pro_first_speech",
    "pro_speech",
]
