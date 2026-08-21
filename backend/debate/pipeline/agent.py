"""模型调用与工具调用执行层。

这里处理的是“给模型喂什么消息、拿回什么结果、是否需要用工具补充资料”。
阶段函数只需要关心自己想说什么，不需要关心不同 tool mode 下的执行细节。
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from langchain_core.messages import ToolMessage

from ..logger import DebateLogger
from .common import (
    clean_tool_artifacts,
    coerce_int,
    extract_reasoning_details,
    extract_usage,
    parse_json_response,
    response_to_text,
)

DEFAULT_TOOL_OUTPUT_TRUNCATE_CHARS = 2500
MIN_TOOL_OUTPUT_TRUNCATE_CHARS = 500
MAX_TOOL_OUTPUT_TRUNCATE_CHARS = 20000
MAX_TOOL_ROUNDS = 8
MAX_MANUAL_FLOW_BLOCKS = 10
MIN_DEEP_THINKING_TOKENS = 128
MAX_DEEP_THINKING_TOKENS = 32768


async def ainvoke_with_metrics(
    runnable: Any,
    messages: list[dict[str, Any]],
    logger: DebateLogger,
    role_key: str,
    stage_label: str,
    *,
    estimate_llm: Any | None = None,
) -> Any:
    """执行一次模型调用，并把 usage 记录到 logger。"""

    # 先真正请求模型。
    response = await runnable.ainvoke(messages)
    reasoning_entries = extract_reasoning_details(response)
    if reasoning_entries:
        logger.log_llm_reasoning(role_key, stage_label, reasoning_entries)
    if logger.metrics_enabled:
        # 从响应里抽 usage；如果 SDK 没给，就退回估算。
        usage, estimated, _ = extract_usage(response, estimate_llm or runnable, messages)
        logger.record_llm_usage(role_key, stage_label, usage, estimated=estimated)
    return response


def compose_user_message(user_message: str, tool_results: list[str]) -> str:
    """把用户主指令和本轮工具结果拼接成最终用户消息。"""

    if not tool_results:
        return user_message
    # 用固定分隔线连接多次检索结果，既方便模型阅读，也便于后续排查 prompt。
    joined = "\n\n---\n\n".join(tool_results)
    return f"{user_message}\n\n【本轮检索结果】\n{joined}"


def build_emergency_final_text(user_message: str) -> str:
    """模型连续返回空正文时的最后兜底发言。"""

    topic_hint = build_fallback_search_query(user_message)[:48]
    return (
        f"基于现有资料，关于“{topic_hint}”，我方认为不能只看单一结论，"
        "而应同时比较事实依据、现实影响和制度后果。对方若忽略这些层面的权衡，"
        "就容易把复杂问题简化为立场判断；因此我方仍坚持当前论证方向。"
    )


def build_fallback_search_query(user_message: str) -> str:
    """从辩手输入里兜底提取一个简短搜索词。

    当模型没有按 react / bind_tools 协议触发工具时，后端仍然需要一个稳定查询。
    这里不追求完美语义，只追求“短、可搜索、不会把整段历史塞进搜索引擎”。
    """

    text = re.sub(r"\s+", " ", str(user_message or "")).strip()
    text = re.sub(r"【[^】]{1,40}】", " ", text)
    text = re.sub(r"(最近辩论记录|请继续发言|请开始你的开篇立论|请给出你的开篇立论|本轮检索结果)", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ，。；：、,.!?！？:：-—")
    if not text:
        return "辩论事实 背景 案例"
    # 优先取后半段，因为通常最新一轮对方观点在 user_message 后部。
    text = text[-160:]
    return text[:100].strip(" ，。；：、,.!?！？:：-—") or "辩论事实 背景 案例"


def normalize_tool_args(args: Any, fallback_query: str) -> dict[str, Any]:
    """把不同模型给出的工具参数统一成 web_search 可接受的 dict。"""

    if isinstance(args, dict):
        normalized = dict(args)
    elif isinstance(args, str):
        parsed = parse_json_response(args)
        normalized = parsed if parsed else {"query": args}
    else:
        normalized = {}

    query = normalized.get("query") or normalized.get("q") or normalized.get("search_query") or normalized.get("keywords")
    normalized_query = str(query or fallback_query).strip() or fallback_query
    # The current web_search schema accepts only query; discard hallucinated provider arguments.
    return {"query": normalized_query[:120]}


def extract_tool_action(text: str) -> dict[str, Any] | None:
    """从 react 模式响应中提取工具调用指令。"""

    payload = parse_json_response(text)
    if not payload:
        return None

    # 兼容两种协议：
    # 1. {action, action_input}
    # 2. {tool_calls: [{name, args}]}
    action_name = payload.get("action") or payload.get("tool") or payload.get("name")
    action_input = (
        payload.get("action_input")
        or payload.get("args")
        or payload.get("arguments")
        or payload.get("input")
        or payload.get("query")
        or payload.get("search_query")
    )
    if action_name in {"web_search", "search", "tavily_search"}:
        return {
            "name": "web_search",
            "args": action_input if isinstance(action_input, dict) else {"query": action_input},
        }

    tool_calls = payload.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        tool_call = tool_calls[0] if isinstance(tool_calls[0], dict) else {}
        tool_name = tool_call.get("name") or tool_call.get("tool") or tool_call.get("action")
        if tool_name in {"web_search", "search", "tavily_search"}:
            return {"name": "web_search", "args": tool_call.get("args") or tool_call.get("arguments") or {}}

    return None


def find_tool(tools: list[Any], tool_name: str) -> Any | None:
    """按名称查找工具；未知名称绝不能误执行其它工具。"""

    normalized = str(tool_name or "web_search").strip()
    for tool in tools:
        if getattr(tool, "name", "") == normalized:
            return tool
    return None


def format_tool_result(tool_name: str, args: dict[str, Any], result: str) -> str:
    query = str(args.get("query") or "").strip()
    prefix = f"工具 `{tool_name}`"
    if query:
        prefix += f" 查询：{query}"
    return f"{prefix}\n{result}"


async def invoke_tool(tool: Any, args: dict[str, Any]) -> str:
    """执行单次工具调用，并截断过长输出。"""

    if hasattr(tool, "ainvoke"):
        result = await tool.ainvoke(args)
    else:
        result = tool.invoke(args)

    text = str(result)
    metadata = getattr(tool, "metadata", None)
    configured_limit = metadata.get("output_truncate_chars") if isinstance(metadata, dict) else None
    truncate_chars = coerce_int(configured_limit) or DEFAULT_TOOL_OUTPUT_TRUNCATE_CHARS
    truncate_chars = max(MIN_TOOL_OUTPUT_TRUNCATE_CHARS, min(truncate_chars, MAX_TOOL_OUTPUT_TRUNCATE_CHARS))
    # 工具原始返回过长会严重膨胀 prompt，所以这里硬裁长度。
    return text[:truncate_chars] + ("\n...[输出已截断]" if len(text) > truncate_chars else "")


async def execute_tool_action(
    tools: list[Any],
    action: dict[str, Any],
    fallback_query: str,
    logger: DebateLogger,
    role_key: str,
    agent_name: str,
    *,
    fallback: bool = False,
) -> str:
    """执行模型给出的工具动作；失败时返回可喂给模型的文本结果。"""

    tool = find_tool(tools, str(action.get("name") or "web_search"))
    if tool is None:
        return f"工具 `{str(action.get('name') or '').strip() or 'unknown'}` 不可用。"
    tool_name = getattr(tool, "name", "web_search")
    tool_args = normalize_tool_args(action.get("args"), fallback_query)
    try:
        result = await invoke_tool(tool, tool_args)
    except Exception as exc:
        # 工具失败不应该让整轮辩论直接中断，所以这里转成文本反馈给模型。
        result = f"工具执行失败：{exc}"
    logger.log_tool_call(role_key, agent_name, tool_name, tool_args, result, fallback=fallback)
    return format_tool_result(tool_name, tool_args, result)


async def execute_fallback_search(
    tools: list[Any],
    user_message: str,
    logger: DebateLogger,
    role_key: str,
    agent_name: str,
) -> str:
    """模型没有稳定触发工具时，由后端托管执行一次搜索。"""

    query = build_fallback_search_query(user_message)
    return await execute_tool_action(
        tools,
        {"name": "web_search", "args": {"query": query}},
        query,
        logger,
        role_key,
        agent_name,
        fallback=True,
    )


def _internal_response_text(response: Any, *, include_reasoning: bool = False) -> str:
    text = clean_tool_artifacts(response_to_text(response)).strip()
    reasoning = extract_reasoning_details(response)
    reasoning_text = "\n\n".join(
        str(item.get("content") or "").strip()
        for item in reasoning
        if str(item.get("content") or "").strip()
    )
    if include_reasoning and reasoning_text and text:
        return f"【模型思考】\n{reasoning_text}\n\n【模型输出】\n{text}"
    return text or reasoning_text


def _manual_flow_prompt(user_message: str, internal_sections: list[str], instruction: str) -> str:
    sections = [user_message.strip()]
    if internal_sections:
        sections.extend(["【本次发言的内部工作记录】", "\n\n".join(internal_sections)])
    sections.extend(["【当前编排步骤】", instruction.strip()])
    return "\n\n".join(section for section in sections if section)


def _manual_tool_query(response_text: str, fallback_query: str) -> dict[str, Any]:
    payload = parse_json_response(response_text)
    candidate: Any = payload if payload else response_text
    return normalize_tool_args(candidate, fallback_query)


async def run_manual_flow(
    llm: Any,
    tools_by_id: dict[str, Any],
    response_flow: dict[str, Any],
    system_prompt: str,
    user_message: str,
    logger: DebateLogger,
    role_key: str,
    agent_name: str,
    stage_label: str,
) -> str:
    """Execute a deterministic private chain and expose only its final speech."""

    blocks = response_flow.get("blocks") if isinstance(response_flow.get("blocks"), list) else []
    internal_sections: list[str] = []
    step_index = 0
    for block in blocks[:MAX_MANUAL_FLOW_BLOCKS]:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").strip().lower()
        if block_type in {"start", "final_response"}:
            continue
        step_index += 1
        if block_type == "deep_thinking":
            max_tokens = min(
                MAX_DEEP_THINKING_TOKENS,
                max(MIN_DEEP_THINKING_TOKENS, coerce_int(block.get("max_tokens")) or 2048),
            )
            instruction = (
                "请对本轮辩论任务进行一次独立的深度思考。分析论证结构、对方漏洞、事实需求和反驳策略；"
                "这里只生成供后续步骤使用的内部分析，不要写成面向用户的正式发言，也不要调用工具。"
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _manual_flow_prompt(user_message, internal_sections, instruction)},
            ]
            try:
                thinking_llm = llm.bind(max_tokens=max_tokens)
            except Exception:
                thinking_llm = llm
            response = await ainvoke_with_metrics(
                thinking_llm,
                messages,
                logger,
                role_key,
                f"{stage_label} · 深度思考 {step_index}",
                estimate_llm=llm,
            )
            thinking_text = _internal_response_text(response, include_reasoning=True) or "本步骤未返回可用的内部分析。"
            visible_thinking = _internal_response_text(response) or thinking_text
            logger.log_manual_thinking(role_key, f"深度思考 {step_index}", visible_thinking, max_tokens)
            internal_sections.append(f"【深度思考 {step_index}】\n{thinking_text}")
            continue

        if block_type == "tool_call":
            tool_id = str(block.get("tool_id") or "").strip()
            tool = tools_by_id.get(tool_id)
            if tool is None:
                raise RuntimeError(f"人工编排的工具调用块未绑定可用工具：{tool_id or '未选择工具'}")
            fallback_query = build_fallback_search_query(user_message)
            planner_instruction = (
                "现在必须调用一次指定搜索工具。请根据辩题、最近发言和已有内部记录，自主决定最有价值的搜索参数。"
                "只返回 JSON：{\"query\":\"不超过 120 字的搜索词\"}，不要输出正式发言。"
            )
            planner_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _manual_flow_prompt(user_message, internal_sections, planner_instruction)},
            ]
            planner_response = await ainvoke_with_metrics(
                llm,
                planner_messages,
                logger,
                role_key,
                f"{stage_label} · 工具规划 {step_index}",
                estimate_llm=llm,
            )
            planner_text = _internal_response_text(planner_response)
            planner_context = _internal_response_text(planner_response, include_reasoning=True)
            tool_args = _manual_tool_query(planner_text, fallback_query)
            tool_name = str(getattr(tool, "name", "web_search") or "web_search")
            result = await execute_tool_action(
                [tool],
                {"name": tool_name, "args": tool_args},
                fallback_query,
                logger,
                role_key,
                agent_name,
            )
            internal_sections.append(
                f"【工具规划 {step_index}】\n{planner_context or planner_text or '模型未返回可见规划文本。'}\n\n"
                f"【工具调用 {step_index}】\n{result}"
            )

    final_instruction = (
        "现在进入正式发言块。请完整吸收以上仅属于本次发言的内部思考和工具结果，"
        "只输出最终辩论发言；不要提及内部流程、积木、工具协议或思考记录，也不要再次调用工具。"
    )
    return await run_plain_mode(
        llm,
        system_prompt,
        _manual_flow_prompt(user_message, internal_sections, final_instruction),
        logger,
        role_key,
        f"{stage_label} · 正式发言",
    )


async def run_plain_mode(
    llm: Any,
    system_prompt: str,
    user_message: str,
    logger: DebateLogger,
    role_key: str,
    stage_label: str,
) -> str:
    """直接调用模型，不允许显式工具调用。"""

    # plain 模式是所有其它模式的最终兜底出口。
    response = await ainvoke_with_metrics(
        llm,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        logger,
        role_key,
        stage_label,
        estimate_llm=llm,
    )
    text = clean_tool_artifacts(response_to_text(response))
    if text.strip():
        return text

    # 一些 reasoning / thinking 模型在预算不足或网关兼容性不佳时会返回空 content。
    # 这里只重试一次，并明确要求直接给最终可见正文，避免辩论流出现空消息。
    retry_response = await ainvoke_with_metrics(
        llm,
        [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"{user_message}\n\n"
                    "上一轮没有返回可见正文。请不要调用工具，不要输出思考过程，"
                    "直接给出一段 80 到 180 字的中文最终发言。"
                ),
            },
        ],
        logger,
        role_key,
        f"{stage_label}（空回复重试）",
        estimate_llm=llm,
    )
    retry_text = clean_tool_artifacts(response_to_text(retry_response))
    if retry_text.strip():
        return retry_text
    return build_emergency_final_text(user_message)


async def run_bind_tools_mode(
    llm: Any,
    tools: list[Any],
    system_prompt: str,
    user_message: str,
    logger: DebateLogger,
    role_key: str,
    agent_name: str,
    stage_label: str,
    max_tool_rounds: int,
    tool_fallback_enabled: bool = False,
) -> str:
    """使用 LangChain bind_tools 模式执行。"""

    # bind_tools 的核心思想是：让模型直接决定何时触发工具调用。
    tool_results: list[str] = []
    max_tool_rounds = min(MAX_TOOL_ROUNDS, max(1, coerce_int(max_tool_rounds) or 2))

    bind_system_prompt = (
        f"{system_prompt}\n\n"
        "工具调用协议：本轮已经启用 `web_search`。如果你需要事实、数据、案例或背景信息，"
        "请优先通过 tool_calls 调用 `web_search`，不要把工具调用格式写进正文。"
    )

    try:
        llm_with_tools = llm.bind_tools(tools)
    except Exception:
        if tool_fallback_enabled:
            fallback_result = await execute_fallback_search(tools, user_message, logger, role_key, agent_name)
            if fallback_result:
                tool_results.append(fallback_result)
        return await run_plain_mode(
            llm,
            system_prompt,
            compose_user_message(user_message, tool_results),
            logger,
            role_key,
            stage_label,
        )

    conversation: list[Any] = [
        {"role": "system", "content": bind_system_prompt},
        {"role": "user", "content": user_message},
    ]

    for round_index in range(max_tool_rounds):
        try:
            response = await ainvoke_with_metrics(
                llm_with_tools,
                conversation,
                logger,
                role_key,
                stage_label,
                estimate_llm=llm,
            )
        except Exception:
            # 某些模型/网关会接受普通聊天但不接受 tools 参数。
            # 这时不让整轮失败，而是退回“后端托管一次搜索 + 普通发言”。
            if tool_fallback_enabled and not tool_results:
                fallback_result = await execute_fallback_search(tools, user_message, logger, role_key, agent_name)
                if fallback_result:
                    tool_results.append(fallback_result)
            break

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            if tool_fallback_enabled and not tool_results and round_index == 0:
                # bind_tools API 可用但模型没有主动发起工具调用时，兜底搜索一次。
                fallback_result = await execute_fallback_search(tools, user_message, logger, role_key, agent_name)
                if fallback_result:
                    tool_results.append(fallback_result)
                    break
            # 没有工具调用通常表示最终答案；空正文则转入统一的纯回答兜底。
            final_text = clean_tool_artifacts(response_to_text(response))
            if final_text:
                return final_text
            break

        # Standard bind_tools flow: assistant tool call -> matching ToolMessage(s).
        for tool_call in tool_calls:
            if isinstance(tool_call, dict) and not str(tool_call.get("id") or "").strip():
                tool_call["id"] = f"call_{uuid.uuid4().hex}"
        conversation.append(response)
        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "")
            fallback_query = build_fallback_search_query(user_message)
            result = await execute_tool_action(
                tools,
                {"name": tool_name, "args": tool_call.get("args", {}) or {}},
                fallback_query,
                logger,
                role_key,
                agent_name,
            )
            if result:
                tool_results.append(result)
                conversation.append(
                    ToolMessage(
                        content=result,
                        tool_call_id=str(tool_call.get("id") or f"call_{uuid.uuid4().hex}"),
                        name=str(tool_name or "web_search"),
                    )
                )

    # 达到最大工具轮数后，强制进入纯回答模式，避免 agent 无限找资料不产出答案。
    return await run_plain_mode(
        llm,
        system_prompt,
        compose_user_message(user_message, tool_results),
        logger,
        role_key,
        stage_label,
    )


async def run_react_mode(
    llm: Any,
    tools: list[Any],
    system_prompt: str,
    user_message: str,
    logger: DebateLogger,
    role_key: str,
    agent_name: str,
    stage_label: str,
    max_tool_rounds: int,
    tool_fallback_enabled: bool = False,
) -> str:
    """使用“模型先输出 JSON 工具指令”的 react 风格执行。"""

    if not tools:
        return await run_plain_mode(llm, system_prompt, user_message, logger, role_key, stage_label)

    # react 模式下，必须把“工具规划”和“最终发言”拆开。
    # 原始 system_prompt 里通常会有“不要输出 JSON / 只返回正文”之类规则，
    # 如果直接复用它做工具规划，会和 ReAct JSON 协议互相打架。
    tool_descriptions = "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)
    tool_results: list[str] = []
    max_tool_rounds = min(MAX_TOOL_ROUNDS, max(1, coerce_int(max_tool_rounds) or 2))
    fallback_query = build_fallback_search_query(user_message)

    for round_index in range(max_tool_rounds):
        must_call_tool = tool_fallback_enabled and round_index == 0 and not tool_results
        react_prompt = (
            "你是辩论系统的工具规划器，不是最终发言者。\n"
            "你的唯一任务是判断是否需要调用工具，并输出机器可解析 JSON。\n"
            "不要输出解释、Markdown、代码块、最终辩论发言或思考过程。\n\n"
            "可用工具：\n"
            f"{tool_descriptions}\n\n"
            "输出协议二选一：\n"
            "1. 调用工具：\n"
            '{"action":"web_search","action_input":{"query":"简短搜索词"}}\n'
            "2. 不再调用工具：\n"
            '{"action":"final"}\n\n'
            f"本轮默认搜索词：{fallback_query}\n"
        )
        if must_call_tool:
            react_prompt += "本轮必须先调用一次 web_search。请只返回第 1 种 JSON。\n"
        else:
            react_prompt += "如果已有资料足够，请只返回第 2 种 JSON。\n"

        try:
            response = await ainvoke_with_metrics(
                llm,
                [
                    {"role": "system", "content": react_prompt},
                    {"role": "user", "content": compose_user_message(user_message, tool_results)},
                ],
                logger,
                role_key,
                stage_label,
                estimate_llm=llm,
            )
            response_text = clean_tool_artifacts(response_to_text(response))
        except Exception:
            if tool_fallback_enabled and not tool_results:
                fallback_result = await execute_fallback_search(tools, user_message, logger, role_key, agent_name)
                if fallback_result:
                    tool_results.append(fallback_result)
            break

        action = extract_tool_action(response_text)
        if not action:
            payload = parse_json_response(response_text)
            if payload.get("action") == "final" and tool_results:
                break
            if tool_fallback_enabled and not tool_results:
                # 模型没有遵守 JSON 协议时，后端兜底执行一次搜索，确保 react 模式可用。
                fallback_result = await execute_fallback_search(tools, user_message, logger, role_key, agent_name)
                if fallback_result:
                    tool_results.append(fallback_result)
            break

        result = await execute_tool_action(tools, action, fallback_query, logger, role_key, agent_name)
        if result:
            tool_results.append(result)

    # 超出允许轮数后，不再继续问工具，而是要求模型基于已有资料给终稿。
    final_message = compose_user_message(
        user_message,
        tool_results + ["请基于以上结果给出最终发言，不要再调用工具。"],
    )
    return await run_plain_mode(llm, system_prompt, final_message, logger, role_key, stage_label)


async def run_agent(
    llm: Any,
    tools: list[Any],
    system_prompt: str,
    user_message: str,
    logger: DebateLogger,
    role_key: str,
    agent_name: str,
    tool_mode: str,
    stage_label: str,
    max_tool_rounds: int,
    tool_fallback_enabled: bool = False,
    response_flow: dict[str, Any] | None = None,
    manual_tools: dict[str, Any] | None = None,
) -> str:
    """统一的辩手代理入口。"""

    normalized_flow = response_flow if isinstance(response_flow, dict) else {}
    if str(normalized_flow.get("mode") or "autonomous").lower() == "manual":
        return await run_manual_flow(
            llm,
            manual_tools or {},
            normalized_flow,
            system_prompt,
            user_message,
            logger,
            role_key,
            agent_name,
            stage_label,
        )
    if not tools:
        return await run_plain_mode(llm, system_prompt, user_message, logger, role_key, stage_label)
    if tool_mode == "react":
        # react 更显式，适合需要强约束工具协议时使用。
        return await run_react_mode(
            llm,
            tools,
            system_prompt,
            user_message,
            logger,
            role_key,
            agent_name,
            stage_label,
            max_tool_rounds,
            tool_fallback_enabled,
        )
    # 默认走 bind_tools，因为它和 LangChain 的标准工具链整合更自然。
    return await run_bind_tools_mode(
        llm,
        tools,
        system_prompt,
        user_message,
        logger,
        role_key,
        agent_name,
        stage_label,
        max_tool_rounds,
        tool_fallback_enabled,
    )
