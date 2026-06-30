"""辩论运行入口。

这个文件现在只保留三层职责：
1. 创建初始 `runtime_state`。
2. 按当前 `phase` 调度到对应阶段函数。
3. 决定下一阶段，以及把阶段增量合并回 runtime。

真正复杂的逻辑，例如：
- 历史窗口裁剪
- 用户插话处理
- 工具调用
- LLM Prompt 拼装

都已经下沉到 `backend.debate.pipeline` 目录中。
这样维护者在排查问题时，可以先从这里看清“总调度顺序”，
再顺着具体阶段跳到更细的模块。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .logger import DebateLogger
from .pipeline.context import create_runtime_context
from .pipeline.phases_debater import con_first_speech, con_speech, pro_first_speech, pro_speech
from .pipeline.phases_judge import judge_initialize, judge_summary
from .pipeline.transitions import build_runtime_result, determine_next_phase
from .state import DebateState, create_initial_state


def create_runtime_state(topic: str, min_rounds: int, max_rounds: int) -> DebateState:
    """创建一场新辩论的最初运行时状态。"""

    return create_initial_state(topic, min_rounds, max_rounds)


def prepare_runtime_context(settings: dict[str, Any]) -> dict[str, Any]:
    """把配置快照转换成可执行上下文。

    这里得到的 context 里通常会包含：
    - judge / pro / con 的模型实例
    - 搜索工具实例
    - 历史窗口大小
    - 工具模式和最大搜索轮数
    """

    return create_runtime_context(settings)


async def run_runtime_phase(runtime: DebateState, context: dict[str, Any], logger: DebateLogger) -> dict[str, Any]:
    """执行当前 `runtime["phase"]` 指向的单个阶段。

    这里故意一次只跑一个阶段，不在本函数里自己 while 循环。
    这样暂停、恢复、撤回、从记录恢复时，外层 manager 可以更精确地控制：
    - 什么时候停
    - 停在第几步之后
    - 下一步要从哪一个 phase 重新开始
    """

    phase = str(runtime.get("phase") or "judge_initialize")

    # 裁判拆题是整场辩论的起点。
    if phase == "judge_initialize":
        return await judge_initialize(runtime, logger, context["judge_llm"])

    # 正方开篇立论。
    if phase == "pro_first_speech":
        return await pro_first_speech(
            runtime,
            logger,
            context["pro_llm"],
            context["pro_tools"],
            context["pro_tool_mode"],
            context["pro_max_tool_rounds"],
        )

    # 反方开篇立论。
    if phase == "con_first_speech":
        return await con_first_speech(
            runtime,
            logger,
            context["con_llm"],
            context["con_tools"],
            context["con_tool_mode"],
            context["con_max_tool_rounds"],
        )

    # 正方常规轮次发言。
    if phase == "pro_speech":
        return await pro_speech(
            runtime,
            logger,
            context["pro_llm"],
            context["pro_tools"],
            context["pro_tool_mode"],
            context["history_window_size"],
            context["pro_max_tool_rounds"],
        )

    # 反方常规轮次发言。
    if phase == "con_speech":
        return await con_speech(
            runtime,
            logger,
            context["con_llm"],
            context["con_tools"],
            context["con_tool_mode"],
            context["history_window_size"],
            context["con_max_tool_rounds"],
        )

    # 所有发言结束后，进入裁判总结。
    if phase == "judge_summary":
        return await judge_summary(runtime, logger, context["judge_llm"])

    # 到这里说明 phase 已经脱离了受支持范围，直接报错最安全。
    raise RuntimeError(f"未知辩论阶段：{phase}")


def merge_runtime_state(runtime: DebateState, updates: dict[str, Any]) -> DebateState:
    """把单阶段返回的增量更新合并回 runtime。

    这里使用 deepcopy，是为了避免调用方手里还握着旧 runtime 引用时，
    出现“原对象被原地改掉”的隐式副作用。
    """

    merged = deepcopy(runtime)
    merged.update(updates)
    return merged


__all__ = [
    "build_runtime_result",
    "create_runtime_state",
    "determine_next_phase",
    "merge_runtime_state",
    "prepare_runtime_context",
    "run_runtime_phase",
]
