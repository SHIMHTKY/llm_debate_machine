"""默认设置构造器。"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from .constants import DEFAULT_CONTEXT_ROUNDS
from .helpers import _create_preset_id, _text


def _default_search() -> dict[str, Any]:
    """返回辩手默认搜索配置。"""

    return {
        "enabled": False,
        "mode": "bind_tools",
        "api_key": _text(os.getenv("TAVILY_API_KEY")),
        "timeout": 60,
        "max_results": 5,
        "search_depth": "advanced",
        "max_tool_rounds": 2,
    }


def _default_model(role: str) -> dict[str, Any]:
    """按角色生成默认模型配置。"""

    azure_api_key = _text(os.getenv("AZURE_OPENAI_API_KEY"))
    azure_base_url = _text(os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("AZURE_OPENAI_BASE_URL"))
    azure_deployment = _text(os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"))
    azure_version = _text(os.getenv("AZURE_OPENAI_API_VERSION"), "2025-04-01-preview")

    if role == "con":
        return {
            "provider": "chatopenai",
            "model": _text(os.getenv("OPENAI_MODEL") or "deepseek-chat"),
            "api_key": _text(os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")),
            "base_url": _text(os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com/v1"),
            "azure_deployment": "",
            "api_version": azure_version,
            "max_tokens": 8000,
            "timeout": 300,
            "max_retries": 2,
            "extra_body": {},
            "search": _default_search(),
        }

    return {
        "provider": "azure",
        "model": "gpt-5.2",
        "api_key": azure_api_key,
        "base_url": azure_base_url,
        "azure_deployment": azure_deployment,
        "api_version": azure_version,
        "max_tokens": 4096 if role == "judge" else 8000,
        "timeout": 120 if role == "judge" else 300,
        "max_retries": 2,
        "extra_body": {},
        **({"search": _default_search()} if role in {"pro", "con"} else {}),
    }


def _default_debater_preset(name: str, role: str) -> dict[str, Any]:
    """生成一份完整的默认辩手预设。"""

    defaults = deepcopy(_default_model(role))
    return {
        "id": _create_preset_id(),
        "name": name,
        **defaults,
    }


def default_settings() -> dict[str, Any]:
    """生成一份完整的默认 settings.json 结构。"""

    judge_defaults = deepcopy(_default_model("judge"))
    presets = [
        _default_debater_preset("Pro Preset", "pro"),
        _default_debater_preset("Con Preset", "con"),
    ]
    return {
        "judge": judge_defaults,
        "debater_presets": presets,
        "pro_preset_id": presets[0]["id"],
        "con_preset_id": presets[1]["id"],
        "context_rounds": DEFAULT_CONTEXT_ROUNDS,
        "usage_tracking_enabled": False,
    }
