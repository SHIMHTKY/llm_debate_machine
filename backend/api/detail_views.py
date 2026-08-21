from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from ..config.settings import load_settings
from ..debate.models import build_llm
from ..debate.pipeline.common import parse_json_response, response_to_text
from ..storage.sessions import SessionStore
from .schemas import MessageDetailViewRequest


MAX_DETAIL_VIEW_INPUT_CHARS = 50000
SIMPLIFIED_CHINESE_LABELS = {"简体中文", "中文", "zh-cn", "zh_hans", "chinese"}


TRANSLATION_SYSTEM_PROMPT = """你是一个严谨的翻译引擎。
请判断用户输入文本的源语言，并只返回一个 JSON 对象，不要输出 Markdown 或解释。
JSON 必须包含且仅包含两个字段：
{
  "翻译内容": "翻译为简体中文后的文本",
  "源语言": "源语言名称"
}
如果源语言本身就是简体中文，则 "翻译内容" 必须返回空字符串，"源语言" 返回 "简体中文"。
"""

REASONING_SUMMARY_SYSTEM_PROMPT = """你是辩论系统的内部分析摘要助手。
请用简体中文总结这段模型思考内容，保留关键判断、推理路径和最终决策依据。
要求：
1. 不要扩写原文没有的信息。
2. 不要输出“以下是总结”之类的套话。
3. 使用 3-6 条要点或一段紧凑摘要。
"""

TOOL_RESULT_SUMMARY_SYSTEM_PROMPT = """你是辩论系统的工具结果摘要助手。
请用简体中文总结这段工具返回结果，重点提炼事实、数据、来源线索和对辩论有用的信息。
要求：
1. 忽略重复、广告、格式噪声和无关片段。
2. 如果结果包含多个条目，按主题合并。
3. 使用 3-8 条要点或一段紧凑摘要。
"""


def _now(store: SessionStore) -> str:
    now = getattr(store, "_now", None)
    return now() if callable(now) else ""


def _message_by_id(session: dict[str, Any], message_id: str) -> dict[str, Any] | None:
    for message in session.get("messages") or []:
        if str(message.get("id") or "") == message_id:
            return message if isinstance(message, dict) else None
    return None


def _detail_by_index(message: dict[str, Any], detail_index: int) -> dict[str, Any] | None:
    details = message.get("details")
    if not isinstance(details, list) or detail_index >= len(details):
        return None
    detail = details[detail_index]
    return detail if isinstance(detail, dict) else None


def _reasoning_entry(detail: dict[str, Any], entry_index: int | None) -> dict[str, Any] | None:
    entries = detail.get("entries")
    if not isinstance(entries, list) or entry_index is None or entry_index >= len(entries):
        return None
    entry = entries[entry_index]
    if isinstance(entry, dict):
        return entry
    if entry is None:
        return None
    entries[entry_index] = {"content": str(entry)}
    return entries[entry_index]


def _target_container(
    session: dict[str, Any],
    payload: MessageDetailViewRequest,
) -> tuple[dict[str, Any], str]:
    message = _message_by_id(session, payload.message_id)
    if message is None or str(message.get("role") or "") not in {"pro", "con"}:
        raise HTTPException(status_code=404, detail="未找到可处理的辩手消息。")

    detail = _detail_by_index(message, payload.detail_index)
    if detail is None:
        raise HTTPException(status_code=404, detail="未找到对应的调用细节。")

    if payload.content_kind == "reasoning":
        if str(detail.get("kind") or "") != "reasoning":
            raise HTTPException(status_code=400, detail="该细节不是思考内容。")
        entry = _reasoning_entry(detail, payload.entry_index)
        if entry is None:
            raise HTTPException(status_code=404, detail="未找到对应的思考内容。")
        text = str(entry.get("content") or "").strip()
        return entry, text

    if str(detail.get("kind") or "") != "tool_result":
        raise HTTPException(status_code=400, detail="该细节不是工具返回结果。")
    text = str(detail.get("result") or "").strip()
    return detail, text


def _cached_view(container: dict[str, Any], view: str) -> dict[str, Any] | None:
    views = container.get("views")
    if not isinstance(views, dict):
        return None
    cached = views.get(view)
    return deepcopy(cached) if isinstance(cached, dict) else None


async def _invoke_model(model_role: str, system_prompt: str, text: str) -> str:
    settings = load_settings()
    model_settings = settings.get(model_role)
    if not isinstance(model_settings, dict):
        raise HTTPException(status_code=400, detail=f"请先在设置中配置{model_role}模型。")
    llm = build_llm(model_settings)
    response = await llm.ainvoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
    )
    return response_to_text(response).strip()


async def _translate_text(text: str) -> dict[str, Any]:
    raw = await _invoke_model("translator", TRANSLATION_SYSTEM_PROMPT, text)
    parsed = parse_json_response(raw)
    if not parsed:
        raise HTTPException(status_code=502, detail="翻译模型未返回可解析的 JSON。")
    translated_content = str(
        parsed.get("翻译内容")
        or parsed.get("translated_content")
        or parsed.get("translation")
        or ""
    ).strip()
    source_language = str(
        parsed.get("源语言")
        or parsed.get("source_language")
        or parsed.get("language")
        or ""
    ).strip()
    if not source_language:
        raise HTTPException(status_code=502, detail="翻译模型未返回源语言。")
    normalized_source = source_language.strip().lower()
    source_is_simplified_chinese = normalized_source in SIMPLIFIED_CHINESE_LABELS or "简体中文" in source_language
    if not translated_content and not source_is_simplified_chinese:
        raise HTTPException(status_code=502, detail="翻译模型返回了空翻译内容。")
    return {
        "view": "translation",
        "source_language": source_language,
        "translated_content": translated_content,
    }


async def _summarize_text(text: str, content_kind: str) -> dict[str, Any]:
    prompt = REASONING_SUMMARY_SYSTEM_PROMPT if content_kind == "reasoning" else TOOL_RESULT_SUMMARY_SYSTEM_PROMPT
    summary = await _invoke_model("summarizer", prompt, text)
    if not summary:
        raise HTTPException(status_code=502, detail="总结模型返回了空内容。")
    return {
        "view": "summary",
        "summary_content": summary,
    }


async def build_message_detail_view(
    store: SessionStore,
    session_id: str,
    payload: MessageDetailViewRequest,
) -> dict[str, Any]:
    session = store.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="未找到该辩论记录。")

    container, text = _target_container(session, payload)
    if not text:
        raise HTTPException(status_code=400, detail="该文本为空，无法处理。")
    if len(text) > MAX_DETAIL_VIEW_INPUT_CHARS:
        raise HTTPException(status_code=413, detail=f"待处理文本超过 {MAX_DETAIL_VIEW_INPUT_CHARS} 字符限制。")

    cached = _cached_view(container, payload.view)
    if cached is not None:
        return {"view": cached, "cached": True, "session": session}

    if payload.view == "translation":
        view_payload = await _translate_text(text)
    else:
        view_payload = await _summarize_text(text, payload.content_kind)

    view_payload.update(
        {
            "content_kind": payload.content_kind,
            "created_at": _now(store),
        }
    )

    def updater(current: dict[str, Any]) -> dict[str, Any]:
        target_container, current_text = _target_container(current, payload)
        if current_text != text:
            raise HTTPException(status_code=409, detail="调用细节内容已变化，请重新打开窗口。")
        views = target_container.get("views")
        if not isinstance(views, dict):
            views = {}
            target_container["views"] = views
        views[payload.view] = deepcopy(view_payload)
        return current

    updated_session = store.update_session(session_id, updater)
    if updated_session is None:
        raise HTTPException(status_code=404, detail="未找到该辩论记录。")
    return {"view": view_payload, "cached": False, "session": updated_session}
