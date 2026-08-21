"""辩论流水线里的底层通用函数。

这里放的都是和具体角色无关的基础能力：

- 把模型响应转成纯文本；
- 解析 JSON 响应；
- 清洗工具调用残留；
- 估算或提取 token 使用量；
- 规范化辩手输出。

之所以集中放在这里，是为了避免这些细碎但关键的规则
散落到各个阶段函数里，导致维护时难以确认真正的标准化入口。
"""

from __future__ import annotations

import ast
import json
import math
import re
from typing import Any


def coerce_int(value: Any) -> int:
    """把任意输入尽量转成非负整数。"""

    try:
        # 这里统一裁到 >= 0，是因为本项目里这个工具函数主要被用在：
        # - token
        # - 轮数
        # - 最大工具调用次数
        # 这些值一旦出现负数，通常都说明输入已经无效。
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def response_to_text(response: Any) -> str:
    """把 LangChain / OpenAI 风格响应统一抽成文本。"""

    # 不同模型 SDK 的 response.content 形态并不一致：
    # - 有的直接是字符串
    # - 有的是分块数组
    # - 有的甚至是自定义对象
    # 所以这里要做一次统一抽取，后面其它模块才能假定“拿到的一定是字符串”。
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                # 某些 SDK 的分块对象里正文放在 `text` 字段。
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content or "")


REASONING_KEY_PARTS = ("reasoning", "thinking", "thought")
REASONING_TAGS = ("think", "thinking", "reasoning")
REASONING_SKIP_KEY_PARTS = ("token", "usage")
REASONING_SKIP_EXACT_KEYS = {"reasoning_tokens", "cached_tokens", "total_tokens", "prompt_tokens", "completion_tokens"}


def _is_reasoning_metric_path(source: str) -> bool:
    """过滤 reasoning_tokens 这类 usage 指标，避免把数字当作思考内容展示。"""

    normalized = str(source or "").lower()
    leaf = re.split(r"[.\[\]]+", normalized)[-1]
    if leaf in REASONING_SKIP_EXACT_KEYS or leaf.endswith("_tokens"):
        return True
    return any(part in normalized for part in ("token_usage", "usage_metadata", "completion_tokens_details", "prompt_tokens_details"))


def _reasoning_value_to_text(value: Any) -> str:
    """把供应商返回的思考字段转成适合写入 Markdown 的文本。"""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:
            pass
    elif hasattr(value, "dict"):
        try:
            value = value.dict()
        except Exception:
            pass
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2, default=str).strip()
        except TypeError:
            return str(value).strip()
    return str(value).strip()


def extract_reasoning_details(response: Any) -> list[dict[str, str]]:
    """提取模型响应中供应商实际返回的思考信息。

    注意：这里不能读取供应商没有返回的隐藏推理，只记录响应对象里已经暴露的
    reasoning / thinking / thought 字段，以及正文中显式出现的 <think> 块。
    """

    entries: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_entry(source: str, value: Any) -> None:
        if _is_reasoning_metric_path(source):
            return
        text = _reasoning_value_to_text(value)
        if not text:
            return
        key = f"{source}\n{text}"
        if key in seen:
            return
        seen.add(key)
        entries.append({"source": source, "content": text})

    def collect_from_mapping(value: Any, source: str) -> None:
        if isinstance(value, dict):
            for raw_key, item in value.items():
                key = str(raw_key)
                key_lower = key.lower()
                nested_source = f"{source}.{key}"
                if key_lower in REASONING_SKIP_EXACT_KEYS or any(part in key_lower for part in REASONING_SKIP_KEY_PARTS):
                    continue
                if any(part in key_lower for part in REASONING_KEY_PARTS):
                    add_entry(nested_source, item)
                elif isinstance(item, (dict, list, tuple)):
                    collect_from_mapping(item, nested_source)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                nested_source = f"{source}[{index}]"
                if isinstance(item, dict):
                    item_type = str(item.get("type") or "").lower()
                    if any(part in item_type for part in REASONING_KEY_PARTS):
                        add_entry(nested_source, item)
                    collect_from_mapping(item, nested_source)
                elif isinstance(item, (list, tuple)):
                    collect_from_mapping(item, nested_source)

    for attr_name in (
        "reasoning",
        "reasoning_content",
        "reasoning_details",
        "reasoning_summary",
        "thinking",
        "thinking_content",
        "thought",
        "thoughts",
    ):
        if hasattr(response, attr_name):
            add_entry(f"response.{attr_name}", getattr(response, attr_name))

    additional_kwargs = getattr(response, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        collect_from_mapping(additional_kwargs, "additional_kwargs")

    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, dict):
        collect_from_mapping(response_metadata, "response_metadata")

    content = getattr(response, "content", None)
    if isinstance(content, (list, tuple)):
        collect_from_mapping(content, "content")

    visible_text = response_to_text(response)
    for tag in REASONING_TAGS:
        pattern = rf"<{tag}\b[^>]*>(.*?)</{tag}>"
        for index, match in enumerate(re.finditer(pattern, visible_text, flags=re.IGNORECASE | re.DOTALL), start=1):
            add_entry(f"content.<{tag}>[{index}]", match.group(1))

    return entries


def normalize_debate_title(value: Any, fallback_topic: str) -> str:
    """把裁判生成的标题收敛到稳定、适合前端展示的形式。"""

    # 先把所有连续空白折叠成单空格，避免模型输出里带多余换行。
    title = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n-—:：")
    if not title:
        # 如果裁判根本没给出标题，就回退到用户原始辩题。
        title = re.sub(r"\s+", " ", str(fallback_topic or "")).strip()
    if len(title) > 20:
        # 标题在 UI 顶部和侧栏里都要展示，过长会挤布局，所以这里硬裁到 20 字以内。
        title = title[:20].rstrip("，。；：、,.!?！？:：-— ")
    return title or "本场辩论"


def usage_payload_to_dict(payload: Any) -> dict[str, int] | None:
    """把不同 SDK 风格的 usage 对象统一成同一结构。"""

    if payload is None:
        return None

    if isinstance(payload, dict):
        data = payload
    elif hasattr(payload, "model_dump"):
        # Pydantic v2 风格对象。
        data = payload.model_dump()
    elif hasattr(payload, "dict"):
        # Pydantic v1 风格对象。
        data = payload.dict()
    else:
        # 最后一层兜底：把常见属性手工摘出来。
        data = {
            "input_tokens": getattr(payload, "input_tokens", None),
            "output_tokens": getattr(payload, "output_tokens", None),
            "total_tokens": getattr(payload, "total_tokens", None),
            "prompt_tokens": getattr(payload, "prompt_tokens", None),
            "completion_tokens": getattr(payload, "completion_tokens", None),
        }

    input_tokens = coerce_int(data.get("input_tokens") or data.get("prompt_tokens"))
    output_tokens = coerce_int(data.get("output_tokens") or data.get("completion_tokens"))
    # total_tokens 有的 SDK 会直接给，有的不会给；没有就用输入+输出补出来。
    total_tokens = coerce_int(data.get("total_tokens") or (input_tokens + output_tokens))
    if input_tokens or output_tokens or total_tokens:
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
    return None


def message_text(messages: list[Any]) -> str:
    """把消息数组压平成文本，供 token 估算使用。"""

    blocks: list[str] = []
    for message in messages:
        if isinstance(message, dict):
            role = str(message.get("role") or "user")
            content = message.get("content", "")
        else:
            role = str(getattr(message, "type", None) or getattr(message, "role", None) or "user")
            content = getattr(message, "content", "")
        if isinstance(content, list):
            # 如果 content 本身是多段块结构，先拼成一个普通字符串。
            content = "\n".join(str(item) for item in content if item is not None)
        blocks.append(f"{role}: {content}")
    return "\n\n".join(blocks)


def estimate_text_tokens(llm: Any, text: str) -> int:
    """在 SDK 没给 usage 时，用近似方法估算 token。"""

    cleaned = str(text or "").strip()
    if not cleaned:
        return 0

    get_num_tokens = getattr(llm, "get_num_tokens", None)
    if callable(get_num_tokens):
        try:
            estimated = int(get_num_tokens(cleaned))
            if estimated >= 0:
                return estimated
        except Exception:
            # 有些模型对象虽然有这个方法，但内部依赖并不完整，所以这里不能让异常往外炸。
            pass

    # 最后一层兜底是按字符长度估一个粗略值。
    # 这里不追求绝对准确，只追求在“没有官方 usage”的情况下还能有可比较的统计量。
    return max(1, math.ceil(len(cleaned) * 0.8))


def estimate_usage(llm: Any, messages: list[Any], response_text: str) -> dict[str, int]:
    """估算一次模型调用的 usage。"""

    input_tokens = estimate_text_tokens(llm, message_text(messages))
    output_tokens = estimate_text_tokens(llm, response_text)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def extract_usage(response: Any, llm: Any, messages: list[Any]) -> tuple[dict[str, int], bool, str]:
    """从模型响应中提取 usage；若取不到则回退估算。"""

    response_text = response_to_text(response)
    # 不同提供商把 usage 放在不同位置，所以要把候选来源都扫一遍。
    candidates = [getattr(response, "usage_metadata", None)]

    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, dict):
        candidates.extend(
            [
                response_metadata.get("token_usage"),
                response_metadata.get("usage"),
                response_metadata.get("usage_metadata"),
            ]
        )

    additional_kwargs = getattr(response, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        candidates.extend(
            [
                additional_kwargs.get("usage"),
                additional_kwargs.get("token_usage"),
            ]
        )

    for candidate in candidates:
        usage = usage_payload_to_dict(candidate)
        if usage is not None:
            # False 表示这次拿到的是“真实 usage”，不是估算值。
            return usage, False, response_text

    # True 表示这次只能估算，调用方后续可以在统计界面做标记。
    return estimate_usage(llm, messages, response_text), True, response_text


def parse_json_response(response: str) -> dict[str, Any]:
    """尽量宽容地从模型输出里提取 JSON 对象。"""

    if not isinstance(response, str):
        return {}

    stripped = response.strip()
    # candidates 按“最可信 -> 最宽松”的顺序堆叠。
    candidates: list[str] = [stripped] if stripped else []

    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response)
    if code_block_match:
        candidates.append(code_block_match.group(1).strip())

    brace_match = re.search(r"\{[\s\S]*\}", response)
    if brace_match:
        candidates.append(brace_match.group(0).strip())

    for candidate in candidates:
        if not candidate:
            continue
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(candidate)
            except (json.JSONDecodeError, SyntaxError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed

    # 到这一步说明标准 JSON 解析都失败了。
    # 但有些模型会输出半残缺 JSON，我们仍尽量从中抽 `speech` / `concede` 片段。
    speech_match = re.search(r'"speech"\s*:\s*"((?:\\.|[^"\\])*)"', response, flags=re.DOTALL)
    concede_match = re.search(r'"concede"\s*:\s*(true|false)', response, flags=re.IGNORECASE)
    if speech_match:
        payload: dict[str, Any] = {}
        fragment = speech_match.group(1)
        try:
            payload["speech"] = json.loads(f'"{fragment}"')
        except json.JSONDecodeError:
            # 如果片段里的转义仍不合法，就退一步做最常见转义替换。
            payload["speech"] = fragment.replace('\\"', '"').replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
        if concede_match:
            payload["concede"] = concede_match.group(1).lower() == "true"
        return payload

    return {}


def clean_tool_artifacts(text: str) -> str:
    """去掉模型在工具调用模式下可能残留的中间标记。"""

    # 这两种标记是部分工具链在中间过程里插入的协议字段，
    # 如果不清洗，前端会把它们直接显示给用户。
    cleaned = re.sub(r"<\|tool_calls_section_begin\|>.*?<\|tool_calls_section_end\|>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<\|tool_call_begin\|>.*?<\|tool_call_end\|>", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def sanitize_debater_speech(text: str) -> str:
    """把辩手输出清洗成可直接展示的自然正文。"""

    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned_lines: list[str] = []

    for raw_line in lines:
        # 先尽量把 Markdown 痕迹剥掉，只保留自然语言正文。
        stripped = raw_line.strip()
        plain_line = re.sub(r"[*_`]+", "", stripped)
        plain_line = re.sub(r"^[#>\s]+", "", plain_line).strip()

        if not plain_line:
            # 连续空行只保留一层，避免模型输出把气泡拉得太松。
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        if re.fullmatch(r"-{3,}", plain_line):
            # 过滤掉 Markdown 分隔线。
            continue

        for label in ("回应观众", "本轮发言正文"):
            for prefix in (label, f"{label}：", f"{label}:"):
                if plain_line == prefix:
                    plain_line = ""
                    break
                if plain_line.startswith(f"{label}："):
                    plain_line = plain_line[len(f"{label}："):].strip()
                    break
                if plain_line.startswith(f"{label}:"):
                    plain_line = plain_line[len(f"{label}:"):].strip()
                    break
            else:
                continue
            break

        if plain_line:
            cleaned_lines.append(plain_line)

    cleaned = "\n".join(cleaned_lines)
    # 三个及以上空行压成两个，进一步收紧排版。
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def normalize_debater_response(response_text: str, *, allow_concede: bool) -> tuple[str, bool]:
    """标准化辩手输出，兼容纯正文与 JSON 包裹正文。"""

    cleaned_response = clean_tool_artifacts(str(response_text or ""))
    parsed = parse_json_response(cleaned_response)
    if not parsed:
        # 不是 JSON 风格时，直接当纯正文清洗。
        return sanitize_debater_speech(cleaned_response), False

    speech_value = parsed.get("speech")
    if isinstance(speech_value, str):
        speech_text = clean_tool_artifacts(speech_value).strip()
    elif speech_value is None:
        speech_text = ""
    else:
        speech_text = clean_tool_artifacts(str(speech_value)).strip()

    if not speech_text:
        # 如果 JSON 里没抽到有效 speech，就用原文兜底，避免整条发言丢失。
        speech_text = cleaned_response

    speech_text = sanitize_debater_speech(speech_text)
    # 只有允许认输的轮次，`concede` 才会真正生效。
    conceded = bool(parsed.get("concede")) if allow_concede else False
    return speech_text, conceded
