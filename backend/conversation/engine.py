"""模型自由对话的顺序接力执行器。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..debate.models import build_llm
from ..debate.pipeline.common import extract_usage, response_to_text


def build_conversation_runtime(prompt: str, participants: list[dict]) -> dict[str, Any]:
    return {
        "phase": "running",
        "prompt": prompt,
        "participant_index": 0,
        "participant_count": len(participants),
        "participants": deepcopy(participants),
        "last_output": "",
        "usage_timeline": [],
        "debate_title": prompt[:20].strip() or "模型自由对话",
    }


def build_turn_messages(prompt: str, previous_output: str, previous_label: str) -> list[dict[str, str]]:
    if not previous_output:
        return [
            {"role": "system", "content": "你正在参加一场模型自由对话。请直接、自然地回答用户的初始提示词，不调用工具，不讨论辩论规则。"},
            {"role": "user", "content": prompt},
        ]
    return [
        {"role": "system", "content": "你正在参加一场模型自由对话。请在上一位模型输出的基础上继续、补充、修正或推进内容。不调用工具，不进行裁判评分。"},
        {"role": "user", "content": f"用户最初提示词：\n{prompt}\n\n上一位模型（{previous_label}）的输出：\n{previous_output}\n\n请给出你的回复。"},
    ]


async def run_conversation_turn(model_settings: dict[str, Any], prompt: str, previous_output: str, previous_label: str):
    llm = build_llm(model_settings)
    messages = build_turn_messages(prompt, previous_output, previous_label)
    response = await llm.ainvoke(messages)
    text = response_to_text(response).strip()
    if not text:
        raise ValueError("模型返回了空内容。")
    usage, estimated, _ = extract_usage(response, llm, messages)
    return text, usage, estimated

