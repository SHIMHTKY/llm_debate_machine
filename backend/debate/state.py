"""辩论运行时状态定义。

这里把整场辩论在内存中流转的核心状态集中定义出来。
维护者如果想快速理解系统到底“记住了什么”，从这个文件入手最直接。
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict


class DebateHistoryEntry(TypedDict, total=False):
    """`debate_history` 单条记录的结构。

    这里既可能是辩手发言，也可能是用户插话，所以字段采用 total=False，
    让不同 kind 的记录可以共用一个 TypedDict。
    """

    id: str
    kind: str
    role: str
    content: str
    round: int | None
    locked: bool
    target_role: str | None
    required_response_roles: list[str]
    responded_roles: list[str]


class DebateState(TypedDict):
    """整场辩论在运行期的主状态。"""

    # 当前应该执行哪个阶段。
    phase: str
    # 用户原始辩题。
    topic: str
    # 当前展示标题，通常由裁判拆题生成，也可能被用户手动改名。
    debate_title: str
    # 轮数上下限。
    min_rounds: int
    max_rounds: int
    # 裁判给正反方布置的长期任务。
    pro_task: str
    con_task: str
    # 裁判对辩题的拆解分析。
    topic_analysis: str
    # 当前已经走到第几轮。
    current_round: int
    # 提供给模型继续读取的历史。
    debate_history: list[DebateHistoryEntry]
    # 是否已经满足结束条件。
    debate_ended: bool
    # 双方是否认输。
    pro_conceded: bool
    con_conceded: bool
    # 终局结果。
    winner: Optional[str]
    pro_score: Optional[int]
    con_score: Optional[int]
    evaluation: Optional[dict[str, Any]]
    conclusion: Optional[str]
    # 每个阶段的 token / 搜索增量时间线，用于撤回后精确重算。
    usage_timeline: list[dict[str, Any]]


def create_initial_state(topic: str, min_rounds: int, max_rounds: int) -> DebateState:
    """创建一场新辩论的最初 runtime_state。

    这里刻意把所有字段一次性展开写全，而不是只写局部字段，
    这样后续任何读取方都能依赖一个稳定的完整结构。
    """

    return {
        "phase": "judge_initialize",
        "topic": topic,
        "debate_title": "",
        "min_rounds": min_rounds,
        "max_rounds": max_rounds,
        "pro_task": "",
        "con_task": "",
        "topic_analysis": "",
        "current_round": 0,
        "debate_history": [],
        "debate_ended": False,
        "pro_conceded": False,
        "con_conceded": False,
        "winner": None,
        "pro_score": None,
        "con_score": None,
        "evaluation": None,
        "conclusion": None,
        "usage_timeline": [],
    }
