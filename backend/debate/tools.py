from __future__ import annotations

import os
import threading
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import tool

DEFAULT_SEARCH_DEPTH = "advanced"
DEFAULT_TIMEOUT = 60


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())


def _run_callable_with_timeout(func, timeout: int) -> dict[str, Any]:
    result_box: dict[str, Any] = {}
    error_box: dict[str, Exception] = {}

    def runner() -> None:
        try:
            result_box["value"] = func()
        except Exception as exc:
            error_box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout=max(1, int(timeout)))

    if thread.is_alive():
        return {"success": False, "error": "搜索请求超时。"}
    if "error" in error_box:
        return {"success": False, "error": f"搜索工具异常：{error_box['error']}"}
    return {"success": True, "data": result_box.get("value")}


def _normalize_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("results") or payload.get("items") or payload.get("data") or []
    if not isinstance(candidates, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(candidates, start=1):
        if not isinstance(item, dict):
            text = _clean_text(item)
            if text:
                normalized.append({"rank": index, "title": text[:80], "url": "", "snippet": text})
            continue

        normalized.append(
            {
                "rank": index,
                "title": _clean_text(item.get("title") or item.get("name")),
                "url": _clean_text(item.get("url") or item.get("link")),
                "snippet": _clean_text(
                    item.get("snippet")
                    or item.get("content")
                    or item.get("description")
                    or item.get("text")
                ),
            }
        )

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in normalized:
        key = item["url"] or item["title"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def tavily_api_search(
    query: str,
    *,
    api_key: str = "",
    timeout: int = DEFAULT_TIMEOUT,
    max_results: int = 5,
    search_depth: str = DEFAULT_SEARCH_DEPTH,
) -> dict[str, Any]:
    cleaned_query = _clean_text(query)
    if not cleaned_query:
        return {"success": False, "error": "搜索词不能为空。"}
    if len(cleaned_query) > 120:
        cleaned_query = cleaned_query[:120]

    load_dotenv()
    tavily_key = _clean_text(api_key or os.getenv("TAVILY_API_KEY"))
    if not tavily_key:
        return {"success": False, "error": "未配置 Tavily API Key。"}

    depth = _clean_text(search_depth) or DEFAULT_SEARCH_DEPTH
    result_limit = max(1, min(int(max_results or 5), 10))

    def search_call():
        from tavily import TavilyClient

        client = TavilyClient(tavily_key)
        return client.search(query=cleaned_query, search_depth=depth, max_results=result_limit)

    response = _run_callable_with_timeout(search_call, timeout=timeout)
    if not response.get("success"):
        return {"success": False, "error": response.get("error", "未知错误。")}

    payload = response.get("data") if isinstance(response.get("data"), dict) else {}
    items = _normalize_items(payload)
    return {
        "success": True,
        "query": cleaned_query,
        "items": items,
        "answer": payload.get("answer"),
        "response_time": payload.get("response_time"),
        "request_id": payload.get("request_id"),
    }


def create_search_tools(search_settings: dict[str, Any]) -> list[Any]:
    if not search_settings.get("enabled"):
        return []

    @tool
    def web_search(query: str) -> str:
        """搜索网页资料，用于补充辩论事实、数据与案例。"""

        cleaned_query = _clean_text(query)
        if not cleaned_query:
            return "搜索词不能为空。"
        if len(cleaned_query.split()) > 20 or len(cleaned_query) > 120:
            return "搜索词过长，请改成简短关键词。"

        result = tavily_api_search(
            cleaned_query,
            api_key=_clean_text(search_settings.get("api_key")),
            timeout=int(search_settings.get("timeout", DEFAULT_TIMEOUT)),
            max_results=int(search_settings.get("max_results", 5)),
            search_depth=_clean_text(search_settings.get("search_depth")) or DEFAULT_SEARCH_DEPTH,
        )

        if not result.get("success"):
            return f"搜索失败：{result.get('error', '未知错误')}"

        items = result.get("items") or []
        if not items:
            return "没有找到可用搜索结果。"

        blocks: list[str] = []
        answer = _clean_text(result.get("answer"))
        if answer:
            blocks.append(f"搜索总结：{answer}")
            blocks.append("")

        for item in items[:5]:
            blocks.append(f"{item['rank']}. {item['title'] or '未命名结果'}")
            if item.get("url"):
                blocks.append(f"链接：{item['url']}")
            if item.get("snippet"):
                blocks.append(f"摘要：{item['snippet']}")
            blocks.append("")

        return "\n".join(blocks).strip()

    return [web_search]

