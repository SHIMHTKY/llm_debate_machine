"""运行期上下文构建。

这里负责把设置快照转换成真正给流水线执行器使用的上下文对象，
包括模型实例、搜索工具、工具模式和历史窗口大小。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..models import build_llm
from ..tools import create_search_tools
from .common import coerce_int
from .history import resolve_context_window_size


def create_runtime_context(settings: dict[str, Any]) -> dict[str, Any]:
    """把 settings 转换成一份可直接供 pipeline 执行的上下文。"""

    pro_search_settings = deepcopy(settings.get("pro", {}).get("search", {}))
    con_search_settings = deepcopy(settings.get("con", {}).get("search", {}))
    return {
        "judge_llm": build_llm(settings["judge"]),
        "pro_llm": build_llm(settings["pro"]),
        "con_llm": build_llm(settings["con"]),
        "pro_tools": create_search_tools(pro_search_settings),
        "con_tools": create_search_tools(con_search_settings),
        "pro_tool_mode": str(pro_search_settings.get("mode") or "bind_tools"),
        "con_tool_mode": str(con_search_settings.get("mode") or "bind_tools"),
        # 这里统一做整数兜底，避免配置里出现空串或非法值时直接抛异常。
        "pro_max_tool_rounds": max(1, coerce_int(pro_search_settings.get("max_tool_rounds")) or 2),
        "con_max_tool_rounds": max(1, coerce_int(con_search_settings.get("max_tool_rounds")) or 2),
        "history_window_size": resolve_context_window_size(settings),
    }
