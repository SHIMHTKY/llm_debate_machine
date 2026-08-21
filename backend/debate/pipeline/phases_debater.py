"""正反方发言阶段实现。

这里的每个函数都只负责一个“说话阶段”：
- 正方开篇
- 反方开篇
- 正方常规轮次
- 反方常规轮次

共享的历史裁剪、用户要求处理、工具调用细节都已经下沉到其它模块，
所以本文件更接近“业务流程脚本”。
"""

from __future__ import annotations

import uuid
from typing import Any

from ..logger import DebateLogger
from ..prompts import get_debater_prompt, get_first_speech_prompt
from ..state import DebateState
from .agent import run_agent
from .common import normalize_debater_response
from .history import (
    build_context_history,
    history_text,
    mark_user_requirements_responded,
    render_pending_user_requirement_notice,
)


async def pro_first_speech(
    state: DebateState,
    logger: DebateLogger,
    pro_llm: Any,
    pro_tools: list[Any],
    tool_mode: str,
    max_tool_rounds: int,
    tool_fallback_enabled: bool,
    response_flow: dict[str, Any] | None = None,
    manual_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """正方开篇立论。"""

    logger.log_status("pro", "正方正在准备开篇立论...")
    prompt = get_first_speech_prompt("pro", state["pro_task"], bool(pro_tools), tool_mode)

    # 开篇虽然还没有完整轮次历史，但仍可能已经有用户插话，所以这里也要吸收上下文。
    opening_context = history_text(state["debate_history"], "pro").strip()
    pending_notice = render_pending_user_requirement_notice(state["debate_history"], "pro")

    user_message = "请开始你的开篇立论。"
    if opening_context:
        user_message = f"在你正式开篇前，请先吸收以下上下文：\n{opening_context}\n\n请开始你的开篇立论。"
    if pending_notice:
        # 如果这时正方还有待回应的用户要求，要把它放在最前面提醒。
        user_message = f"{pending_notice}\n\n{user_message}"

    response_text = await run_agent(
        pro_llm,
        pro_tools,
        prompt,
        user_message,
        logger,
        "pro",
        "正方",
        tool_mode,
        "开篇立论",
        max_tool_rounds,
        tool_fallback_enabled,
        response_flow,
        manual_tools,
    )
    speech_text, _ = normalize_debater_response(response_text, allow_concede=False)

    logger.log_speech("pro", speech_text, 1)
    updated_history = mark_user_requirements_responded(state["debate_history"], "pro")
    return {
        "debate_history": updated_history
        + [{"id": uuid.uuid4().hex, "kind": "speech", "role": "pro", "content": speech_text, "round": 1}],
        "current_round": 1,
    }


async def con_first_speech(
    state: DebateState,
    logger: DebateLogger,
    con_llm: Any,
    con_tools: list[Any],
    tool_mode: str,
    max_tool_rounds: int,
    tool_fallback_enabled: bool,
    response_flow: dict[str, Any] | None = None,
    manual_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """反方开篇立论。"""

    logger.log_status("con", "反方正在回应开篇立论...")

    # 反方开篇之前，至少已经能看到正方第一轮发言，所以取最近两条历史足够。
    recent_history = build_context_history(state["debate_history"], 2)
    prompt = get_first_speech_prompt("con", state["con_task"], bool(con_tools), tool_mode)
    pending_notice = render_pending_user_requirement_notice(state["debate_history"], "con")
    user_message = f"最近辩论记录：\n{history_text(recent_history, 'con')}\n\n请给出你的开篇立论。"
    if pending_notice:
        user_message = f"{pending_notice}\n\n{user_message}"

    response_text = await run_agent(
        con_llm,
        con_tools,
        prompt,
        user_message,
        logger,
        "con",
        "反方",
        tool_mode,
        "开篇立论",
        max_tool_rounds,
        tool_fallback_enabled,
        response_flow,
        manual_tools,
    )
    speech_text, _ = normalize_debater_response(response_text, allow_concede=False)

    logger.log_speech("con", speech_text, 1)
    updated_history = mark_user_requirements_responded(state["debate_history"], "con")
    return {
        "debate_history": updated_history
        + [{"id": uuid.uuid4().hex, "kind": "speech", "role": "con", "content": speech_text, "round": 1}]
    }


async def pro_speech(
    state: DebateState,
    logger: DebateLogger,
    pro_llm: Any,
    pro_tools: list[Any],
    tool_mode: str,
    history_window_size: int,
    max_tool_rounds: int,
    tool_fallback_enabled: bool,
    response_flow: dict[str, Any] | None = None,
    manual_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """正方常规轮次发言。"""

    # 正方发言会推进一个新的轮次编号，所以这里是 current_round + 1。
    round_num = state["current_round"] + 1
    # 只有达到最少轮数之后，才允许模型通过 concede 主动认输。
    can_concede = round_num >= state["min_rounds"]

    logger.log_status("pro", f"正方正在准备第 {round_num} 轮发言...")
    prompt = get_debater_prompt("pro", state["pro_task"], can_concede, bool(pro_tools), tool_mode)

    recent_history = build_context_history(state["debate_history"], history_window_size)
    pending_notice = render_pending_user_requirement_notice(state["debate_history"], "pro")
    user_message = f"最近辩论记录：\n{history_text(recent_history, 'pro')}\n\n请继续发言。"
    if pending_notice:
        user_message = f"{pending_notice}\n\n{user_message}"

    response_text = await run_agent(
        pro_llm,
        pro_tools,
        prompt,
        user_message,
        logger,
        "pro",
        "正方",
        tool_mode,
        f"第 {round_num} 轮发言",
        max_tool_rounds,
        tool_fallback_enabled,
        response_flow,
        manual_tools,
    )
    speech_text, conceded = normalize_debater_response(response_text, allow_concede=can_concede)

    logger.log_speech("pro", speech_text, round_num, conceded=conceded)
    new_history = mark_user_requirements_responded(state["debate_history"], "pro") + [
        {"id": uuid.uuid4().hex, "kind": "speech", "role": "pro", "content": speech_text, "round": round_num}
    ]
    return {
        "debate_history": new_history,
        "current_round": round_num,
        "pro_conceded": conceded,
        # 如果正方认输，这里直接把 debate_ended 置真，后续转场逻辑会据此进入总结。
        "debate_ended": conceded,
    }


async def con_speech(
    state: DebateState,
    logger: DebateLogger,
    con_llm: Any,
    con_tools: list[Any],
    tool_mode: str,
    history_window_size: int,
    max_tool_rounds: int,
    tool_fallback_enabled: bool,
    response_flow: dict[str, Any] | None = None,
    manual_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """反方常规轮次发言。"""

    # 反方发言与正方同属同一轮，所以这里直接沿用 current_round。
    round_num = state["current_round"]
    can_concede = round_num >= state["min_rounds"]

    logger.log_status("con", f"反方正在准备第 {round_num} 轮发言...")
    prompt = get_debater_prompt("con", state["con_task"], can_concede, bool(con_tools), tool_mode)

    recent_history = build_context_history(state["debate_history"], history_window_size)
    pending_notice = render_pending_user_requirement_notice(state["debate_history"], "con")
    user_message = f"最近辩论记录：\n{history_text(recent_history, 'con')}\n\n请继续发言。"
    if pending_notice:
        user_message = f"{pending_notice}\n\n{user_message}"

    response_text = await run_agent(
        con_llm,
        con_tools,
        prompt,
        user_message,
        logger,
        "con",
        "反方",
        tool_mode,
        f"第 {round_num} 轮发言",
        max_tool_rounds,
        tool_fallback_enabled,
        response_flow,
        manual_tools,
    )
    speech_text, conceded = normalize_debater_response(response_text, allow_concede=can_concede)

    logger.log_speech("con", speech_text, round_num, conceded=conceded)
    new_history = mark_user_requirements_responded(state["debate_history"], "con") + [
        {"id": uuid.uuid4().hex, "kind": "speech", "role": "con", "content": speech_text, "round": round_num}
    ]
    return {
        "debate_history": new_history,
        "con_conceded": conceded,
        # 这里不能直接覆盖 debate_ended，因为前面也可能已经被别的条件置真。
        "debate_ended": state["debate_ended"] or conceded,
    }
