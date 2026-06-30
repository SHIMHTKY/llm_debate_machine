"""阶段跳转规则。

运行器每执行完一个阶段，只做两件事：

1. 把该阶段返回的更新合并进 runtime；
2. 根据当前 phase 和 runtime 内容决定下一步去哪里。

阶段迁移单独放一处之后，维护者就不需要在多个阶段函数之间来回跳着看。
"""

from __future__ import annotations

from ..state import DebateState
from .history import check_after_pro, check_continue


def determine_next_phase(runtime: DebateState, executed_phase: str) -> str:
    """根据当前已执行阶段和运行时状态决定下一阶段。"""

    if executed_phase == "judge_initialize":
        return "pro_first_speech"
    if executed_phase == "pro_first_speech":
        return "con_first_speech"
    if executed_phase == "con_first_speech":
        return "pro_speech"
    if executed_phase == "pro_speech":
        return "judge_summary" if check_after_pro(runtime) == "end" else "con_speech"
    if executed_phase == "con_speech":
        return "judge_summary" if check_continue(runtime) == "end" else "pro_speech"
    if executed_phase == "judge_summary":
        return "completed"
    return "completed"


def build_runtime_result(runtime: DebateState) -> dict:
    """抽取前端最终结果页需要的字段。"""

    return {
        "winner": runtime.get("winner"),
        "pro_score": runtime.get("pro_score"),
        "con_score": runtime.get("con_score"),
        "evaluation": runtime.get("evaluation"),
        "conclusion": runtime.get("conclusion"),
    }
