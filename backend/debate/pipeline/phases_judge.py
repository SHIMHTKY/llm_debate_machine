"""裁判阶段实现。

这里专门放裁判拥有控制权的两个阶段：

- `judge_initialize`：拆题、生成短标题、给正反方分配任务；
- `judge_summary`：读取整场历史并给出裁决。

把裁判阶段单独放一个文件，是为了让维护者能很快找到：
“裁判到底在什么时候说话、依据什么材料说话、输出哪些字段”。
"""

from __future__ import annotations

from typing import Any

from ..logger import DebateLogger
from ..prompts import JUDGE_INIT_PROMPT, JUDGE_SUMMARY_PROMPT
from ..state import DebateState
from .agent import ainvoke_with_metrics
from .common import normalize_debate_title, parse_json_response, response_to_text
from .history import build_context_history, history_text


async def judge_initialize(state: DebateState, logger: DebateLogger, judge_llm: Any) -> dict[str, Any]:
    """让裁判在开场时完成拆题和任务分配。"""

    logger.log_status("judge", "裁判正在拆解辩题...")
    prompt = JUDGE_INIT_PROMPT.format(topic=state["topic"])
    response = await ainvoke_with_metrics(
        judge_llm,
        [{"role": "user", "content": prompt}],
        logger,
        "judge",
        "裁判拆题",
        estimate_llm=judge_llm,
    )
    response_text = response_to_text(response)
    logger.log_llm_raw("裁判-任务拆解", prompt, response_text)

    # 裁判输出理论上应该是 JSON，但这里依旧做兜底，避免单次格式漂移让整场辩论中断。
    parsed = parse_json_response(response_text)
    debate_title = normalize_debate_title(parsed.get("debate_title"), state["topic"])
    topic_analysis = parsed.get("topic_analysis") or f"围绕“{state['topic']}”的价值、事实和现实影响展开。"
    pro_task = parsed.get("pro_task") or f"作为正方，请论证为什么“{state['topic']}”成立。"
    con_task = parsed.get("con_task") or f"作为反方，请论证为什么“{state['topic']}”不成立。"

    logger.log_tasks(debate_title, topic_analysis, pro_task, con_task)
    return {
        "debate_title": debate_title,
        "topic_analysis": topic_analysis,
        "pro_task": pro_task,
        "con_task": con_task,
        "current_round": 0,
    }


async def judge_summary(state: DebateState, logger: DebateLogger, judge_llm: Any) -> dict[str, Any]:
    """在整场辩论结束后，让裁判基于历史给出最终评分与结论。"""

    logger.log_status("judge", "裁判正在给出总结与判决...")

    # 总结阶段不做窗口裁剪，等价于把整场历史都交给裁判。
    history_view = build_context_history(state["debate_history"], max(len(state["debate_history"]), 1))
    prompt = JUDGE_SUMMARY_PROMPT.format(
        pro_task=state["pro_task"],
        con_task=state["con_task"],
        debate_history=history_text(history_view),
    )
    response = await ainvoke_with_metrics(
        judge_llm,
        [{"role": "user", "content": prompt}],
        logger,
        "judge",
        "裁判总结",
        estimate_llm=judge_llm,
    )
    response_text = response_to_text(response)
    logger.log_llm_raw("裁判-最终判决", prompt, response_text)

    parsed = parse_json_response(response_text)
    winner = parsed.get("winner", "平局")
    pro_score = parsed.get("pro_score", 50)
    con_score = parsed.get("con_score", 50)
    evaluation = parsed.get("evaluation", {})
    conclusion = parsed.get("conclusion", "裁判没有返回最终总结。")

    logger.log_summary(winner, pro_score, con_score, evaluation, conclusion)
    return {
        "winner": winner,
        "pro_score": pro_score,
        "con_score": con_score,
        "evaluation": evaluation,
        "conclusion": conclusion,
    }
