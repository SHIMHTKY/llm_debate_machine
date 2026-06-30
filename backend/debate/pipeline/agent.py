"""模型调用与工具调用执行层。

这里处理的是“给模型喂什么消息、拿回什么结果、是否需要用工具补充资料”。
阶段函数只需要关心自己想说什么，不需要关心不同 tool mode 下的执行细节。
"""

from __future__ import annotations

from typing import Any

from ..logger import DebateLogger
from .common import clean_tool_artifacts, coerce_int, extract_usage, parse_json_response, response_to_text


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


def extract_tool_action(text: str) -> dict[str, Any] | None:
    """从 react 模式响应中提取工具调用指令。"""

    payload = parse_json_response(text)
    if not payload:
        return None

    # 兼容两种协议：
    # 1. {action, action_input}
    # 2. {tool_calls: [{name, args}]}
    action_name = payload.get("action")
    action_input = payload.get("action_input")
    if action_name == "web_search":
        return {
            "name": "web_search",
            "args": action_input if isinstance(action_input, dict) else {"query": action_input},
        }

    tool_calls = payload.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        tool_call = tool_calls[0] if isinstance(tool_calls[0], dict) else {}
        if tool_call.get("name") == "web_search":
            return {"name": "web_search", "args": tool_call.get("args", {})}

    return None


async def invoke_tool(tool: Any, args: dict[str, Any]) -> str:
    """执行单次工具调用，并截断过长输出。"""

    if hasattr(tool, "ainvoke"):
        result = await tool.ainvoke(args)
    else:
        result = tool.invoke(args)

    text = str(result)
    # 工具原始返回过长会严重膨胀 prompt，所以这里硬裁长度。
    return text[:2500] + ("\n...[输出已截断]" if len(text) > 2500 else "")


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
    return clean_tool_artifacts(response_to_text(response))


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
) -> str:
    """使用 LangChain bind_tools 模式执行。"""

    # bind_tools 的核心思想是：让模型直接决定何时触发工具调用。
    llm_with_tools = llm.bind_tools(tools)
    tool_results: list[str] = []
    max_tool_rounds = coerce_int(max_tool_rounds) or 2

    for _ in range(max_tool_rounds):
        response = await ainvoke_with_metrics(
            llm_with_tools,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": compose_user_message(user_message, tool_results)},
            ],
            logger,
            role_key,
            stage_label,
            estimate_llm=llm,
        )

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            # 没有工具调用时，说明模型已经给出了最终答案。
            return clean_tool_artifacts(response_to_text(response))

        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("args", {}) or {}
            for tool in tools:
                if tool.name != tool_name:
                    continue
                try:
                    result = await invoke_tool(tool, tool_args)
                except Exception as exc:
                    # 工具失败不应该让整轮辩论直接中断，所以这里转成文本反馈给模型。
                    result = f"工具执行失败：{exc}"
                logger.log_tool_call(role_key, agent_name, tool_name, tool_args, result)
                tool_results.append(result)
                break

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
) -> str:
    """使用“模型先输出 JSON 工具指令”的 react 风格执行。"""

    if not tools:
        return await run_plain_mode(llm, system_prompt, user_message, logger, role_key, stage_label)

    # react 模式下，我们把工具协议写死到 prompt 里，让模型先返回指令，再由后端执行。
    tool_descriptions = "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)
    react_prompt = (
        f"{system_prompt}\n\n"
        "如果需要使用工具，请严格返回 JSON，不要输出别的内容：\n"
        "{\n"
        '  "action": "web_search",\n'
        '  "action_input": {"query": "简短搜索词"}\n'
        "}\n\n"
        "可用工具：\n"
        f"{tool_descriptions}\n\n"
        "如果不需要工具，直接返回最终发言。"
    )

    tool_results: list[str] = []
    max_tool_rounds = coerce_int(max_tool_rounds) or 2
    for _ in range(max_tool_rounds):
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
        action = extract_tool_action(response_text)
        if not action:
            # 一旦模型不再输出工具指令，就把当前文本视为最终发言。
            return response_text

        for tool in tools:
            if tool.name != action["name"]:
                continue
            try:
                result = await invoke_tool(tool, action["args"])
            except Exception as exc:
                result = f"工具执行失败：{exc}"
            logger.log_tool_call(role_key, agent_name, action["name"], action["args"], result)
            tool_results.append(result)
            break

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
) -> str:
    """统一的辩手代理入口。"""

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
    )
