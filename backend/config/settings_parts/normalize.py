"""设置归一化逻辑。

这是整个 settings 子系统里最核心的一层：
它负责把“环境变量默认值 / 旧版配置 / 前端回传表单 / 手工编辑的 JSON”
统一整理成稳定的内部结构。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .constants import DEFAULT_CONTEXT_ROUNDS, MAX_DEBATER_PRESETS, VALID_PROVIDERS, VALID_TOOL_MODES
from .defaults import _default_model, default_settings
from .helpers import (
    _coerce_bool,
    _create_preset_id,
    _normalize_context_rounds,
    _normalize_extra_body,
    _normalize_secret,
    _positive_int,
    _text,
)


def _normalize_search_settings(
    raw_search: Any,
    defaults: dict[str, Any],
    existing_search: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """清洗搜索配置。"""

    search = raw_search if isinstance(raw_search, dict) else {}
    existing_search = existing_search or defaults
    mode = _text(search.get("mode"), defaults["mode"]).lower()
    if mode not in VALID_TOOL_MODES:
        mode = defaults["mode"]
    return {
        "enabled": _coerce_bool(search.get("enabled"), _coerce_bool(defaults["enabled"])),
        "mode": mode,
        "api_key": _normalize_secret(search.get("api_key"), _text(existing_search.get("api_key"), defaults["api_key"])),
        "timeout": _positive_int(search.get("timeout"), defaults["timeout"]),
        "max_results": _positive_int(search.get("max_results"), defaults["max_results"]),
        "search_depth": _text(search.get("search_depth"), defaults["search_depth"]) or defaults["search_depth"],
        "max_tool_rounds": _positive_int(search.get("max_tool_rounds"), defaults.get("max_tool_rounds", 2)),
    }


def _normalize_model_settings(
    raw_model: Any,
    defaults: dict[str, Any],
    existing_model: dict[str, Any] | None = None,
    *,
    include_search: bool,
    strict_extra_body: bool = False,
) -> dict[str, Any]:
    """清洗单个模型配置。"""

    model = raw_model if isinstance(raw_model, dict) else {}
    existing_model = existing_model if isinstance(existing_model, dict) else defaults
    provider = _text(model.get("provider"), defaults["provider"]).lower()
    if provider not in VALID_PROVIDERS:
        provider = defaults["provider"]

    normalized = {
        "provider": provider,
        "model": _text(model.get("model"), defaults["model"]),
        "api_key": _normalize_secret(model.get("api_key"), _text(existing_model.get("api_key"), defaults["api_key"])),
        "base_url": _text(model.get("base_url"), defaults["base_url"]),
        "extra_body": _normalize_extra_body(
            model.get("extra_body"),
            existing_model.get("extra_body") if isinstance(existing_model.get("extra_body"), dict) else defaults.get("extra_body"),
            strict=strict_extra_body,
        ),
        "azure_deployment": _text(model.get("azure_deployment"), defaults["azure_deployment"]),
        "api_version": _text(model.get("api_version"), defaults["api_version"]),
        "max_tokens": _positive_int(model.get("max_tokens"), defaults["max_tokens"]),
        "timeout": _positive_int(model.get("timeout"), defaults["timeout"]),
        "max_retries": _positive_int(model.get("max_retries"), defaults["max_retries"]),
    }

    if include_search:
        normalized["search"] = _normalize_search_settings(
            model.get("search"),
            defaults["search"],
            existing_model.get("search") if isinstance(existing_model.get("search"), dict) else defaults["search"],
        )

    return normalized


def _looks_like_legacy_settings(payload: Any) -> bool:
    """判断是否还是旧版 `judge/pro/con` 平铺结构。"""

    return isinstance(payload, dict) and "debater_presets" not in payload and any(key in payload for key in ("pro", "con"))


def _migrate_legacy_settings(raw_settings: Any) -> dict[str, Any]:
    """把旧版设置迁移到当前 preset 结构。"""

    payload = raw_settings if isinstance(raw_settings, dict) else {}
    judge_defaults = _default_model("judge")
    pro_defaults = _default_model("pro")
    con_defaults = _default_model("con")

    pro_source = payload.get("pro") if isinstance(payload.get("pro"), dict) else pro_defaults
    con_source = payload.get("con") if isinstance(payload.get("con"), dict) else con_defaults

    pro_config = _normalize_model_settings(pro_source, pro_defaults, pro_source, include_search=True)
    con_config = _normalize_model_settings(con_source, con_defaults, con_source, include_search=True)

    pro_name = f"Pro · {_text(pro_config.get('model')) or 'Preset'}"
    con_name = f"Con · {_text(con_config.get('model')) or 'Preset'}"

    pro_preset = {"id": _create_preset_id(), "name": pro_name, **pro_config}
    con_preset = {"id": _create_preset_id(), "name": con_name, **con_config}

    judge_source = payload.get("judge") if isinstance(payload.get("judge"), dict) else judge_defaults
    return {
        "judge": _normalize_model_settings(judge_source, judge_defaults, judge_source, include_search=False),
        "debater_presets": [pro_preset, con_preset],
        "pro_preset_id": pro_preset["id"],
        "con_preset_id": con_preset["id"],
        "context_rounds": DEFAULT_CONTEXT_ROUNDS,
        "usage_tracking_enabled": False,
    }


def _prepare_payload(raw_settings: Any) -> dict[str, Any]:
    """把外部输入整理成当前版本的标准 payload。"""

    if _looks_like_legacy_settings(raw_settings):
        return _migrate_legacy_settings(raw_settings)
    return raw_settings if isinstance(raw_settings, dict) else {}


def _normalize_debater_presets(
    raw_presets: Any,
    base_presets: list[dict[str, Any]],
    *,
    strict_extra_body: bool = False,
) -> list[dict[str, Any]]:
    """清洗整个辩手预设列表。"""

    default_candidates = default_settings()["debater_presets"]
    source_presets = raw_presets if isinstance(raw_presets, list) else base_presets
    existing_by_id = {
        _text(preset.get("id")): preset
        for preset in base_presets
        if isinstance(preset, dict) and _text(preset.get("id"))
    }

    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for index, raw_preset in enumerate(source_presets[:MAX_DEBATER_PRESETS]):
        if not isinstance(raw_preset, dict):
            continue
        fallback_default = default_candidates[index % len(default_candidates)]
        requested_id = _text(raw_preset.get("id"))
        existing_preset = existing_by_id.get(requested_id)
        existing_name = _text(existing_preset.get("name")) if existing_preset else ""
        fallback_name = _text(raw_preset.get("name"), existing_name or fallback_default["name"]) or f"Debater Preset {index + 1}"
        normalized_preset = {
            "id": requested_id or _text(existing_preset.get("id") if existing_preset else "") or _create_preset_id(),
            "name": fallback_name,
            **_normalize_model_settings(
                raw_preset,
                fallback_default,
                existing_preset,
                include_search=True,
                strict_extra_body=strict_extra_body,
            ),
        }
        if normalized_preset["id"] in used_ids:
            normalized_preset["id"] = _create_preset_id()
        used_ids.add(normalized_preset["id"])
        normalized.append(normalized_preset)

    if normalized:
        return normalized

    fallback = deepcopy(base_presets[:1] or default_candidates[:1])
    if fallback:
        if not _text(fallback[0].get("id")):
            fallback[0]["id"] = _create_preset_id()
        if not _text(fallback[0].get("name")):
            fallback[0]["name"] = "Debater Preset 1"
    return fallback


def _resolve_selected_preset_id(selected_id: Any, presets: list[dict[str, Any]], fallback_index: int = 0) -> str:
    """从候选预设中解析出最终选中的 preset id。"""

    preset_ids = [_text(preset.get("id")) for preset in presets if _text(preset.get("id"))]
    preferred = _text(selected_id)
    if preferred in preset_ids:
        return preferred
    if not preset_ids:
        return ""
    safe_index = min(max(fallback_index, 0), len(preset_ids) - 1)
    return preset_ids[safe_index]


def normalize_settings(
    raw_settings: Any,
    base_settings: dict[str, Any] | None = None,
    *,
    strict_extra_body: bool = False,
) -> dict[str, Any]:
    """把任意输入整理成当前版本的 settings.json 结构。"""

    defaults = default_settings()
    base = _prepare_payload(base_settings) if isinstance(base_settings, dict) else defaults
    payload = _prepare_payload(raw_settings)

    judge_source = payload["judge"] if isinstance(payload.get("judge"), dict) else base["judge"]
    presets_source = payload["debater_presets"] if "debater_presets" in payload else base["debater_presets"]
    normalized_presets = _normalize_debater_presets(
        presets_source,
        base["debater_presets"],
        strict_extra_body=strict_extra_body,
    )

    pro_preset_id = _resolve_selected_preset_id(
        payload.get("pro_preset_id", base.get("pro_preset_id")),
        normalized_presets,
        fallback_index=0,
    )
    con_fallback_index = 1 if len(normalized_presets) > 1 else 0
    con_preset_id = _resolve_selected_preset_id(
        payload.get("con_preset_id", base.get("con_preset_id")),
        normalized_presets,
        fallback_index=con_fallback_index,
    )

    return {
        "judge": _normalize_model_settings(
            judge_source,
            defaults["judge"],
            base.get("judge"),
            include_search=False,
            strict_extra_body=strict_extra_body,
        ),
        "debater_presets": normalized_presets,
        "pro_preset_id": pro_preset_id,
        "con_preset_id": con_preset_id,
        "context_rounds": _normalize_context_rounds(
            payload.get("context_rounds", base.get("context_rounds")),
            _normalize_context_rounds(base.get("context_rounds"), DEFAULT_CONTEXT_ROUNDS),
            strict=strict_extra_body,
        ),
        "usage_tracking_enabled": _coerce_bool(payload.get("usage_tracking_enabled"), _coerce_bool(base.get("usage_tracking_enabled"), False)),
    }


def _resolve_runtime_settings(raw_settings: dict[str, Any]) -> dict[str, Any]:
    """把磁盘上的 raw settings 解析成运行时设置。"""

    defaults = default_settings()
    presets = raw_settings.get("debater_presets", []) if isinstance(raw_settings, dict) else []
    if not presets:
        presets = defaults["debater_presets"]
        raw_settings = {
            **raw_settings,
            "judge": defaults["judge"],
            "debater_presets": presets,
            "pro_preset_id": defaults["pro_preset_id"],
            "con_preset_id": defaults["con_preset_id"],
            "context_rounds": defaults["context_rounds"],
            "usage_tracking_enabled": defaults["usage_tracking_enabled"],
        }

    presets_by_id = {
        _text(preset.get("id")): preset
        for preset in presets
        if isinstance(preset, dict) and _text(preset.get("id"))
    }
    pro_preset_id = _resolve_selected_preset_id(raw_settings.get("pro_preset_id"), presets)
    con_preset_id = _resolve_selected_preset_id(raw_settings.get("con_preset_id"), presets, fallback_index=1 if len(presets) > 1 else 0)

    pro_preset = deepcopy(presets_by_id.get(pro_preset_id) or presets[0])
    con_preset = deepcopy(presets_by_id.get(con_preset_id) or presets[min(1, len(presets) - 1)])
    pro_preset["preset_id"] = pro_preset_id
    pro_preset["preset_name"] = _text(pro_preset.get("name"))
    con_preset["preset_id"] = con_preset_id
    con_preset["preset_name"] = _text(con_preset.get("name"))

    judge_settings = deepcopy(raw_settings.get("judge") or defaults["judge"])
    return {
        "judge": judge_settings,
        "pro": pro_preset,
        "con": con_preset,
        "debater_presets": deepcopy(presets),
        "pro_preset_id": pro_preset_id,
        "con_preset_id": con_preset_id,
        "context_rounds": _normalize_context_rounds(raw_settings.get("context_rounds"), DEFAULT_CONTEXT_ROUNDS),
        "usage_tracking_enabled": _coerce_bool(raw_settings.get("usage_tracking_enabled"), False),
    }
