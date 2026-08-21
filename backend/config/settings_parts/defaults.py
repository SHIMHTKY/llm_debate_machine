from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from .constants import DEFAULT_CONTEXT_ROUNDS
from .helpers import _create_preset_id, _create_supplier_id, _text


def _default_search() -> dict[str, Any]:
    return {
        "enabled": False,
        "mode": "bind_tools",
        "api_key": _text(os.getenv("TAVILY_API_KEY")),
        "timeout": 60,
        "max_results": 5,
        "search_depth": "advanced",
        "output_truncate_chars": 2500,
        "max_tool_rounds": 2,
        "fallback_enabled": False,
    }


def _default_tool_config() -> dict[str, Any]:
    search = _default_search()
    return {
        "id": "tool_tavily_search",
        "name": "Tavily Search",
        "template_id": "tavily_search",
        "type": "tavily_search",
        "enabled": False,
        "api_key": search["api_key"],
        "timeout": search["timeout"],
        "max_results": search["max_results"],
        "search_depth": search["search_depth"],
        "output_truncate_chars": search["output_truncate_chars"],
    }


def _default_tool_selection() -> dict[str, Any]:
    return {
        "enabled_tool_ids": [],
        "mode": "bind_tools",
        "max_tool_rounds": 2,
        "fallback_enabled": False,
    }


def _default_response_flow() -> dict[str, Any]:
    return {
        "mode": "autonomous",
        "blocks": [
            {"id": "flow_start", "type": "start"},
            {"id": "flow_final", "type": "final_response"},
        ],
    }


def _default_model(role: str) -> dict[str, Any]:
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


def _supplier_from_model(name: str, model_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _create_supplier_id(),
        "name": name,
        "provider": _text(model_config.get("provider"), "chatopenai").lower(),
        "api_key": _text(model_config.get("api_key")),
        "base_url": _text(model_config.get("base_url")),
        "api_version": _text(model_config.get("api_version")),
        "timeout": int(model_config.get("timeout") or 300),
        "max_retries": int(model_config.get("max_retries") or 2),
    }


def _preset_from_model(name: str, model_config: dict[str, Any], supplier_id: str) -> dict[str, Any]:
    return {
        "id": _create_preset_id(),
        "name": name,
        "supplier_id": supplier_id,
        "model": _text(model_config.get("model")),
        "azure_deployment": _text(model_config.get("azure_deployment")),
        "max_tokens": int(model_config.get("max_tokens") or 8000),
        "extra_body": deepcopy(model_config.get("extra_body")) if isinstance(model_config.get("extra_body"), dict) else {},
        "tool_selection": _default_tool_selection(),
        "response_flow": _default_response_flow(),
    }


def _judge_from_model(model_config: dict[str, Any], supplier_id: str) -> dict[str, Any]:
    return {
        "supplier_id": supplier_id,
        "model": _text(model_config.get("model")),
        "azure_deployment": _text(model_config.get("azure_deployment")),
        "max_tokens": int(model_config.get("max_tokens") or 4096),
        "extra_body": deepcopy(model_config.get("extra_body")) if isinstance(model_config.get("extra_body"), dict) else {},
    }


def default_settings() -> dict[str, Any]:
    judge_defaults = deepcopy(_default_model("judge"))
    pro_model = deepcopy(_default_model("pro"))
    con_model = deepcopy(_default_model("con"))
    judge_supplier = _supplier_from_model("Default Judge Supplier", judge_defaults)
    azure_supplier = _supplier_from_model("Default Azure Supplier", pro_model)
    chatopenai_supplier = _supplier_from_model("Default ChatOpenAI Supplier", con_model)
    suppliers = [judge_supplier, azure_supplier, chatopenai_supplier]
    presets = [
        _preset_from_model("Pro Preset", pro_model, azure_supplier["id"]),
        _preset_from_model("Con Preset", con_model, chatopenai_supplier["id"]),
    ]
    return {
        "judge": _judge_from_model(judge_defaults, judge_supplier["id"]),
        "translator": _judge_from_model(judge_defaults, judge_supplier["id"]),
        "summarizer": _judge_from_model(judge_defaults, judge_supplier["id"]),
        "model_suppliers": suppliers,
        "tool_configs": [_default_tool_config()],
        "debater_presets": presets,
        "pro_preset_id": presets[0]["id"],
        "con_preset_id": presets[1]["id"],
        "context_rounds": DEFAULT_CONTEXT_ROUNDS,
        "usage_tracking_enabled": False,
    }
