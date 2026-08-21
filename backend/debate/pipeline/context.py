"""运行期上下文构建。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..models import build_llm
from ..tools import create_manual_tool_map, create_search_tools
from .common import coerce_int
from .history import resolve_context_window_size


MAX_TOOL_ROUNDS = 8


def create_runtime_context(settings: dict[str, Any]) -> dict[str, Any]:
    """把 settings 转换成 pipeline 可以直接消费的上下文对象。"""

    pro_search_settings = deepcopy(settings.get("pro", {}).get("search", {}))
    con_search_settings = deepcopy(settings.get("con", {}).get("search", {}))
    return {
        "judge_llm": build_llm(settings["judge"]),
        "pro_llm": build_llm(settings["pro"]),
        "con_llm": build_llm(settings["con"]),
        "pro_tools": create_search_tools(pro_search_settings),
        "con_tools": create_search_tools(con_search_settings),
        "pro_manual_tools": create_manual_tool_map(settings["pro"], settings.get("tool_configs") or []),
        "con_manual_tools": create_manual_tool_map(settings["con"], settings.get("tool_configs") or []),
        "pro_response_flow": deepcopy(settings["pro"].get("response_flow") or {}),
        "con_response_flow": deepcopy(settings["con"].get("response_flow") or {}),
        "pro_tool_mode": str(pro_search_settings.get("mode") or "bind_tools"),
        "con_tool_mode": str(con_search_settings.get("mode") or "bind_tools"),
        "pro_tool_fallback_enabled": bool(pro_search_settings.get("fallback_enabled")),
        "con_tool_fallback_enabled": bool(con_search_settings.get("fallback_enabled")),
        "pro_max_tool_rounds": min(MAX_TOOL_ROUNDS, max(1, coerce_int(pro_search_settings.get("max_tool_rounds")) or 2)),
        "con_max_tool_rounds": min(MAX_TOOL_ROUNDS, max(1, coerce_int(con_search_settings.get("max_tool_rounds")) or 2)),
        "history_window_size": resolve_context_window_size(settings),
    }
