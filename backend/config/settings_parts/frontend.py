"""面向前端的设置投影。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .constants import DEFAULT_CONTEXT_ROUNDS, MAX_DEBATER_PRESETS
from .helpers import _coerce_bool, _mask_secret, _mask_sensitive_values, _normalize_context_rounds, _text
from .normalize import MAX_MODEL_SUPPLIERS, MAX_TOOL_CONFIGS
from .storage import _load_raw_settings, _save_raw_settings


def _frontend_model(config: dict[str, Any], *, include_search: bool) -> dict[str, Any]:
    """把运行时配置转换成可安全返回前端的结构。"""

    masked = deepcopy(config)
    masked["api_key"] = _mask_secret(config.get("api_key"))
    masked["has_api_key"] = bool(_text(config.get("api_key")))
    if isinstance(config.get("extra_body"), dict):
        masked["extra_body"] = _mask_sensitive_values(config["extra_body"])
    if include_search:
        search = masked.get("search", {})
        real_search = config.get("search", {}) if isinstance(config.get("search"), dict) else {}
        search["api_key"] = _mask_secret(real_search.get("api_key"))
        search["has_api_key"] = bool(_text(real_search.get("api_key")))
        masked["search"] = search
    return masked


def _frontend_supplier(config: dict[str, Any]) -> dict[str, Any]:
    masked = deepcopy(config)
    masked["api_key"] = _mask_secret(config.get("api_key"))
    masked["has_api_key"] = bool(_text(config.get("api_key")))
    return masked


def _frontend_tool_config(config: dict[str, Any]) -> dict[str, Any]:
    masked = deepcopy(config)
    masked["api_key"] = _mask_secret(config.get("api_key"))
    masked["has_api_key"] = bool(_text(config.get("api_key")))
    return masked


def settings_for_frontend(raw_settings: dict[str, Any]) -> dict[str, Any]:
    """把 raw settings 投影成前端设置页使用的数据。"""

    return {
        "judge": _frontend_model(raw_settings["judge"], include_search=False),
        "translator": _frontend_model(raw_settings["translator"], include_search=False),
        "summarizer": _frontend_model(raw_settings["summarizer"], include_search=False),
        "model_suppliers": [
            _frontend_supplier(supplier)
            for supplier in raw_settings.get("model_suppliers", [])
        ],
        "tool_configs": [
            _frontend_tool_config(tool_config)
            for tool_config in raw_settings.get("tool_configs", [])
        ],
        "debater_presets": [
            {
                "id": preset["id"],
                "name": preset.get("name", ""),
                "supplier_id": preset.get("supplier_id", ""),
                "model": preset.get("model", ""),
                "azure_deployment": preset.get("azure_deployment", ""),
                "max_tokens": preset.get("max_tokens"),
                "extra_body": _mask_sensitive_values(preset.get("extra_body")) if isinstance(preset.get("extra_body"), dict) else {},
                "tool_selection": deepcopy(preset.get("tool_selection")) if isinstance(preset.get("tool_selection"), dict) else {},
                "response_flow": deepcopy(preset.get("response_flow")) if isinstance(preset.get("response_flow"), dict) else {},
            }
            for preset in raw_settings.get("debater_presets", [])
        ],
        "pro_preset_id": raw_settings.get("pro_preset_id", ""),
        "con_preset_id": raw_settings.get("con_preset_id", ""),
        "context_rounds": _normalize_context_rounds(raw_settings.get("context_rounds"), DEFAULT_CONTEXT_ROUNDS),
        "usage_tracking_enabled": _coerce_bool(raw_settings.get("usage_tracking_enabled"), False),
        "preset_limit": MAX_DEBATER_PRESETS,
        "supplier_limit": MAX_MODEL_SUPPLIERS,
        "tool_limit": MAX_TOOL_CONFIGS,
    }


def load_settings_for_frontend() -> dict[str, Any]:
    """读取并返回前端可直接消费的设置。"""

    return settings_for_frontend(_load_raw_settings())


def save_settings_for_frontend(raw_settings: Any) -> dict[str, Any]:
    """保存前端设置，并返回掩码后的最新结果。"""

    return settings_for_frontend(_save_raw_settings(raw_settings))


def public_settings_summary(settings: dict[str, Any]) -> dict[str, Any]:
    """生成适合写入 detail 日志的公开配置摘要。"""

    def summarize(role: str, config: dict[str, Any]) -> dict[str, Any]:
        summary = {
            "role": role,
            "provider": config.get("provider"),
            "model": config.get("model"),
            "supplier_id": config.get("supplier_id"),
            "supplier_name": config.get("supplier_name"),
            "base_url": config.get("base_url"),
            "azure_deployment": config.get("azure_deployment"),
            "api_version": config.get("api_version"),
            "max_tokens": config.get("max_tokens"),
            "timeout": config.get("timeout"),
            "max_retries": config.get("max_retries"),
            "extra_body": _mask_sensitive_values(config.get("extra_body")) if isinstance(config.get("extra_body"), dict) else {},
            "has_api_key": bool(_text(config.get("api_key"))),
        }
        if role in {"pro", "con"}:
            search = config.get("search", {})
            summary["preset_id"] = config.get("preset_id")
            summary["preset_name"] = config.get("preset_name")
            summary["search"] = {
                "enabled": bool(search.get("enabled")),
                "mode": search.get("mode"),
                "has_api_key": bool(_text(search.get("api_key"))),
                "max_results": search.get("max_results"),
                "search_depth": search.get("search_depth"),
                "output_truncate_chars": search.get("output_truncate_chars"),
                "max_tool_rounds": search.get("max_tool_rounds"),
                "fallback_enabled": bool(search.get("fallback_enabled")),
                "tool_id": search.get("tool_id"),
                "tool_name": search.get("tool_name"),
                "tool_template_id": search.get("tool_template_id"),
                "tool_type": search.get("tool_type"),
            }
            summary["tool_selection"] = _mask_sensitive_values(config.get("tool_selection")) if isinstance(config.get("tool_selection"), dict) else {}
            summary["response_flow"] = _mask_sensitive_values(config.get("response_flow")) if isinstance(config.get("response_flow"), dict) else {}
        return summary

    return {
        "context_rounds": _normalize_context_rounds(settings.get("context_rounds"), DEFAULT_CONTEXT_ROUNDS),
        "usage_tracking_enabled": _coerce_bool(settings.get("usage_tracking_enabled"), False),
        "judge": summarize("judge", settings.get("judge", {})),
        "translator": summarize("translator", settings.get("translator", {})),
        "summarizer": summarize("summarizer", settings.get("summarizer", {})),
        "pro": summarize("pro", settings.get("pro", {})),
        "con": summarize("con", settings.get("con", {})),
    }
