from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from .constants import DEFAULT_CONTEXT_ROUNDS, MAX_DEBATER_PRESETS, VALID_PROVIDERS, VALID_TOOL_MODES
from .defaults import _default_model, _default_search, _default_tool_config, _default_tool_selection, default_settings
from .helpers import (
    _coerce_bool,
    _create_preset_id,
    _create_supplier_id,
    _create_tool_id,
    _normalize_context_rounds,
    _normalize_extra_body,
    _normalize_secret,
    _positive_int,
    _text,
)


MAX_MODEL_SUPPLIERS = 24
MAX_TOOL_CONFIGS = 12
VALID_TOOL_TYPES = {"tavily_search"}
DEFAULT_TAVILY_TOOL_ID = "tool_tavily_search"


def _normalize_search_settings(
    raw_search: Any,
    defaults: dict[str, Any],
    existing_search: dict[str, Any] | None = None,
) -> dict[str, Any]:
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


def _normalize_supplier_settings(
    raw_supplier: Any,
    defaults: dict[str, Any],
    existing_supplier: dict[str, Any] | None = None,
) -> dict[str, Any]:
    supplier = raw_supplier if isinstance(raw_supplier, dict) else {}
    existing_supplier = existing_supplier if isinstance(existing_supplier, dict) else defaults
    provider = _text(supplier.get("provider"), defaults.get("provider", "chatopenai")).lower()
    if provider not in VALID_PROVIDERS:
        provider = defaults.get("provider", "chatopenai")

    return {
        "id": _text(supplier.get("id")) or _text(existing_supplier.get("id")) or _create_supplier_id(),
        "name": _text(supplier.get("name"), _text(existing_supplier.get("name"), defaults.get("name", "Model Supplier"))),
        "provider": provider,
        "api_key": _normalize_secret(supplier.get("api_key"), _text(existing_supplier.get("api_key"), defaults.get("api_key", ""))),
        "base_url": _text(supplier.get("base_url"), defaults.get("base_url", "")),
        "api_version": _text(supplier.get("api_version"), defaults.get("api_version", "")),
        "timeout": _positive_int(supplier.get("timeout"), _positive_int(defaults.get("timeout"), 300)),
        "max_retries": _positive_int(supplier.get("max_retries"), _positive_int(defaults.get("max_retries"), 2)),
    }


def _normalize_model_suppliers(
    raw_suppliers: Any,
    base_suppliers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    default_suppliers = default_settings()["model_suppliers"]
    source_suppliers = raw_suppliers if isinstance(raw_suppliers, list) else base_suppliers
    existing_by_id = {
        _text(supplier.get("id")): supplier
        for supplier in base_suppliers
        if isinstance(supplier, dict) and _text(supplier.get("id"))
    }
    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for index, raw_supplier in enumerate(source_suppliers[:MAX_MODEL_SUPPLIERS]):
        if not isinstance(raw_supplier, dict):
            continue
        requested_id = _text(raw_supplier.get("id"))
        existing_supplier = existing_by_id.get(requested_id)
        fallback_default = default_suppliers[index % len(default_suppliers)]
        normalized_supplier = _normalize_supplier_settings(raw_supplier, fallback_default, existing_supplier)
        if normalized_supplier["id"] in used_ids:
            normalized_supplier["id"] = _create_supplier_id()
        used_ids.add(normalized_supplier["id"])
        normalized.append(normalized_supplier)

    if normalized:
        return normalized
    return deepcopy(base_suppliers[:1] or default_suppliers[:1])


def _normalize_tool_config(
    raw_tool: Any,
    defaults: dict[str, Any],
    existing_tool: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tool = raw_tool if isinstance(raw_tool, dict) else {}
    existing_tool = existing_tool if isinstance(existing_tool, dict) else defaults
    template_id = _text(
        tool.get("template_id"),
        _text(tool.get("type"), _text(existing_tool.get("template_id"), defaults.get("template_id", "tavily_search"))),
    ).lower()
    if template_id not in VALID_TOOL_TYPES:
        template_id = "tavily_search"

    return {
        "id": _text(tool.get("id")) or _text(existing_tool.get("id")) or _create_tool_id(),
        "name": _text(tool.get("name"), _text(existing_tool.get("name"), defaults.get("name", "Tavily Search"))),
        "template_id": template_id,
        "type": template_id,
        "enabled": _coerce_bool(tool.get("enabled"), _coerce_bool(defaults.get("enabled"), False)),
        "api_key": _normalize_secret(tool.get("api_key"), _text(existing_tool.get("api_key"), defaults.get("api_key", ""))),
        "timeout": _positive_int(tool.get("timeout"), _positive_int(defaults.get("timeout"), 60)),
        "max_results": max(1, min(_positive_int(tool.get("max_results"), _positive_int(defaults.get("max_results"), 5)), 10)),
        "search_depth": _text(tool.get("search_depth"), defaults.get("search_depth", "advanced")) or "advanced",
    }


def _normalize_tool_configs(
    raw_tools: Any,
    base_tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    default_tools = default_settings()["tool_configs"]
    source_tools = raw_tools if isinstance(raw_tools, list) else base_tools
    existing_by_id = {
        _text(tool.get("id")): tool
        for tool in base_tools
        if isinstance(tool, dict) and _text(tool.get("id"))
    }
    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for index, raw_tool in enumerate(source_tools[:MAX_TOOL_CONFIGS]):
        if not isinstance(raw_tool, dict):
            continue
        requested_id = _text(raw_tool.get("id"))
        existing_tool = existing_by_id.get(requested_id)
        fallback_default = default_tools[index % len(default_tools)]
        normalized_tool = _normalize_tool_config(raw_tool, fallback_default, existing_tool)
        if normalized_tool["id"] in used_ids:
            normalized_tool["id"] = _create_tool_id()
        used_ids.add(normalized_tool["id"])
        normalized.append(normalized_tool)

    if normalized:
        return normalized
    return deepcopy(base_tools[:1] or default_tools[:1])


def _normalize_tool_selection(
    raw_selection: Any,
    existing_selection: dict[str, Any] | None,
    available_tool_ids: list[str],
    *,
    legacy_search: dict[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = _default_tool_selection()
    selection = raw_selection if isinstance(raw_selection, dict) else {}
    existing_selection = existing_selection if isinstance(existing_selection, dict) else defaults
    legacy = legacy_search if isinstance(legacy_search, dict) else None

    mode = _text(selection.get("mode"), _text(existing_selection.get("mode"), defaults["mode"])).lower()
    if legacy and not selection:
        mode = _text(legacy.get("mode"), mode).lower()
    if mode not in VALID_TOOL_MODES:
        mode = defaults["mode"]

    max_tool_rounds = _positive_int(
        selection.get("max_tool_rounds"),
        _positive_int(existing_selection.get("max_tool_rounds"), defaults["max_tool_rounds"]),
    )
    if legacy and not selection:
        max_tool_rounds = _positive_int(legacy.get("max_tool_rounds"), max_tool_rounds)

    enabled_ids_source = selection.get("enabled_tool_ids", existing_selection.get("enabled_tool_ids", []))
    if not isinstance(enabled_ids_source, list):
        enabled_ids_source = []
    enabled_tool_ids = []
    for tool_id in enabled_ids_source:
        clean_id = _text(tool_id)
        if clean_id in available_tool_ids and clean_id not in enabled_tool_ids:
            enabled_tool_ids.append(clean_id)

    if legacy and not selection and _coerce_bool(legacy.get("enabled"), False):
        legacy_tool_id = _text(legacy.get("tool_id")) or DEFAULT_TAVILY_TOOL_ID
        if legacy_tool_id in available_tool_ids:
            enabled_tool_ids = [legacy_tool_id]

    return {
        "enabled_tool_ids": enabled_tool_ids,
        "mode": mode,
        "max_tool_rounds": max_tool_rounds,
    }


def _supplier_label_from_model(model: dict[str, Any]) -> str:
    provider = _text(model.get("provider"), "chatopenai").lower()
    base_url = _text(model.get("base_url"))
    host = urlparse(base_url).netloc or base_url
    if host:
        return f"{'Azure' if provider == 'azure' else 'ChatOpenAI'} - {host}"
    return "Azure Supplier" if provider == "azure" else "ChatOpenAI Supplier"


def _supplier_key_from_model(model: dict[str, Any]) -> tuple[Any, ...]:
    provider = _text(model.get("provider"), "chatopenai").lower()
    if provider not in VALID_PROVIDERS:
        provider = "chatopenai"
    return (
        provider,
        _text(model.get("api_key")),
        _text(model.get("base_url")),
        _text(model.get("api_version")),
        _positive_int(model.get("timeout"), 300),
        _positive_int(model.get("max_retries"), 2),
    )


def _supplier_from_full_model(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _create_supplier_id(),
        "name": _supplier_label_from_model(model),
        "provider": _text(model.get("provider"), "chatopenai").lower(),
        "api_key": _text(model.get("api_key")),
        "base_url": _text(model.get("base_url")),
        "api_version": _text(model.get("api_version")),
        "timeout": _positive_int(model.get("timeout"), 300),
        "max_retries": _positive_int(model.get("max_retries"), 2),
    }


def _light_preset_from_full_model(model: dict[str, Any], supplier_id: str, fallback_name: str) -> dict[str, Any]:
    return {
        "id": _text(model.get("id")) or _create_preset_id(),
        "name": _text(model.get("name"), fallback_name) or fallback_name,
        "supplier_id": supplier_id,
        "model": _text(model.get("model")),
        "azure_deployment": _text(model.get("azure_deployment")),
        "max_tokens": _positive_int(model.get("max_tokens"), 8000),
        "extra_body": deepcopy(model.get("extra_body")) if isinstance(model.get("extra_body"), dict) else {},
        "search": deepcopy(model.get("search")) if isinstance(model.get("search"), dict) else _default_model("pro")["search"],
    }


def _light_judge_from_full_model(model: dict[str, Any], supplier_id: str) -> dict[str, Any]:
    return {
        "supplier_id": supplier_id,
        "model": _text(model.get("model")),
        "azure_deployment": _text(model.get("azure_deployment")),
        "max_tokens": _positive_int(model.get("max_tokens"), 4096),
        "extra_body": deepcopy(model.get("extra_body")) if isinstance(model.get("extra_body"), dict) else {},
    }


def _split_full_presets(raw_presets: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    suppliers: list[dict[str, Any]] = []
    supplier_by_key: dict[tuple[Any, ...], str] = {}
    presets: list[dict[str, Any]] = []

    for index, raw_preset in enumerate(raw_presets):
        if not isinstance(raw_preset, dict):
            continue
        key = _supplier_key_from_model(raw_preset)
        supplier_id = supplier_by_key.get(key)
        if not supplier_id:
            supplier = _supplier_from_full_model(raw_preset)
            supplier_id = supplier["id"]
            supplier_by_key[key] = supplier_id
            suppliers.append(supplier)
        fallback_name = f"Debater Preset {index + 1}"
        presets.append(_light_preset_from_full_model(raw_preset, supplier_id, fallback_name))

    return suppliers, presets


def _migrate_judge_to_supplier(payload: dict[str, Any]) -> dict[str, Any]:
    judge = payload.get("judge")
    if not isinstance(judge, dict) or _text(judge.get("supplier_id")):
        return payload
    if not any(key in judge for key in ("provider", "api_key", "base_url", "api_version", "timeout", "max_retries")):
        return payload

    migrated = dict(payload)
    suppliers = [
        deepcopy(supplier)
        for supplier in payload.get("model_suppliers", [])
        if isinstance(supplier, dict)
    ]
    supplier_by_key = {
        _supplier_key_from_model(supplier): _text(supplier.get("id"))
        for supplier in suppliers
        if _text(supplier.get("id"))
    }
    key = _supplier_key_from_model(judge)
    supplier_id = supplier_by_key.get(key)
    if not supplier_id:
        supplier = _supplier_from_full_model(judge)
        supplier["name"] = f"Judge - {supplier['name']}"
        supplier_id = supplier["id"]
        suppliers.insert(0, supplier)

    migrated["model_suppliers"] = suppliers
    migrated["judge"] = _light_judge_from_full_model(judge, supplier_id)
    return migrated


def _tool_key_from_search(search: dict[str, Any]) -> tuple[Any, ...]:
    normalized = _normalize_search_settings(search, _default_search(), search)
    return (
        _text(normalized.get("api_key")),
        _positive_int(normalized.get("timeout"), 60),
        _positive_int(normalized.get("max_results"), 5),
        _text(normalized.get("search_depth"), "advanced"),
    )


def _search_has_tool_config(search: Any) -> bool:
    if not isinstance(search, dict):
        return False
    return any(
        [
            _coerce_bool(search.get("enabled"), False),
            bool(_text(search.get("api_key"))),
            "timeout" in search,
            "max_results" in search,
            "search_depth" in search,
        ]
    )


def _tool_from_search(search: dict[str, Any], index: int) -> dict[str, Any]:
    normalized = _normalize_search_settings(search, _default_search(), search)
    return {
        "id": DEFAULT_TAVILY_TOOL_ID if index == 1 else _create_tool_id(),
        "name": "Tavily Search" if index == 1 else f"Tavily Search {index}",
        "template_id": "tavily_search",
        "type": "tavily_search",
        "enabled": _coerce_bool(normalized.get("enabled"), False),
        "api_key": _text(normalized.get("api_key")),
        "timeout": _positive_int(normalized.get("timeout"), 60),
        "max_results": max(1, min(_positive_int(normalized.get("max_results"), 5), 10)),
        "search_depth": _text(normalized.get("search_depth"), "advanced") or "advanced",
    }


def _migrate_preset_searches_to_tools(payload: dict[str, Any]) -> dict[str, Any]:
    presets = payload.get("debater_presets")
    if not isinstance(presets, list):
        return payload

    migrated = dict(payload)
    migrated_presets: list[dict[str, Any]] = []
    tool_configs: list[dict[str, Any]] = []
    tool_id_by_key: dict[tuple[Any, ...], str] = {}

    existing_tools = payload.get("tool_configs")
    if isinstance(existing_tools, list):
        tool_configs = [deepcopy(tool) for tool in existing_tools if isinstance(tool, dict)]
        for tool in tool_configs:
            if _text(tool.get("template_id"), _text(tool.get("type"), "tavily_search")) == "tavily_search":
                key = (
                    _text(tool.get("api_key")),
                    _positive_int(tool.get("timeout"), 60),
                    _positive_int(tool.get("max_results"), 5),
                    _text(tool.get("search_depth"), "advanced"),
                )
                tool_id_by_key[key] = _text(tool.get("id"))

    for raw_preset in presets:
        preset = deepcopy(raw_preset) if isinstance(raw_preset, dict) else {}
        search = preset.get("search") if isinstance(preset.get("search"), dict) else None
        if "tool_selection" not in preset and search:
            selected_tool_ids: list[str] = []
            if _search_has_tool_config(search):
                key = _tool_key_from_search(search)
                tool_id = tool_id_by_key.get(key)
                if not tool_id:
                    tool = _tool_from_search(search, len(tool_configs) + 1)
                    tool_id = tool["id"]
                    tool_id_by_key[key] = tool_id
                    tool_configs.append(tool)
                if _coerce_bool(search.get("enabled"), False):
                    selected_tool_ids = [tool_id]
            preset["tool_selection"] = {
                "enabled_tool_ids": selected_tool_ids,
                "mode": _text(search.get("mode"), "bind_tools").lower(),
                "max_tool_rounds": _positive_int(search.get("max_tool_rounds"), 2),
            }
        migrated_presets.append(preset)

    if not tool_configs:
        tool_configs = [deepcopy(_default_tool_config())]
    migrated["tool_configs"] = tool_configs
    migrated["debater_presets"] = migrated_presets
    return migrated


def _looks_like_legacy_settings(payload: Any) -> bool:
    return isinstance(payload, dict) and "debater_presets" not in payload and any(key in payload for key in ("pro", "con"))


def _migrate_legacy_settings(raw_settings: Any) -> dict[str, Any]:
    payload = raw_settings if isinstance(raw_settings, dict) else {}
    judge_defaults = _default_model("judge")
    pro_defaults = _default_model("pro")
    con_defaults = _default_model("con")

    pro_source = payload.get("pro") if isinstance(payload.get("pro"), dict) else pro_defaults
    con_source = payload.get("con") if isinstance(payload.get("con"), dict) else con_defaults
    pro_config = _normalize_model_settings(pro_source, pro_defaults, pro_source, include_search=True)
    con_config = _normalize_model_settings(con_source, con_defaults, con_source, include_search=True)
    pro_config["name"] = f"Pro - {_text(pro_config.get('model')) or 'Preset'}"
    con_config["name"] = f"Con - {_text(con_config.get('model')) or 'Preset'}"
    suppliers, presets = _split_full_presets([pro_config, con_config])
    judge_source = payload.get("judge") if isinstance(payload.get("judge"), dict) else judge_defaults

    migrated = {
        "judge": _normalize_model_settings(judge_source, judge_defaults, judge_source, include_search=False),
        "model_suppliers": suppliers,
        "debater_presets": presets,
        "pro_preset_id": presets[0]["id"],
        "con_preset_id": presets[min(1, len(presets) - 1)]["id"],
        "context_rounds": DEFAULT_CONTEXT_ROUNDS,
        "usage_tracking_enabled": False,
    }
    migrated = _migrate_judge_to_supplier(migrated)
    return _migrate_preset_searches_to_tools(migrated)


def _prepare_payload(raw_settings: Any) -> dict[str, Any]:
    if _looks_like_legacy_settings(raw_settings):
        return _migrate_legacy_settings(raw_settings)
    payload = raw_settings if isinstance(raw_settings, dict) else {}
    if "model_suppliers" not in payload and isinstance(payload.get("debater_presets"), list):
        suppliers, presets = _split_full_presets(payload.get("debater_presets", []))
        if suppliers and presets:
            migrated = dict(payload)
            migrated["model_suppliers"] = suppliers
            migrated["debater_presets"] = presets
            payload = migrated
    payload = _migrate_judge_to_supplier(payload)
    if "tool_configs" not in payload and isinstance(payload.get("debater_presets"), list):
        payload = _migrate_preset_searches_to_tools(payload)
    return payload


def _normalize_debater_presets(
    raw_presets: Any,
    base_presets: list[dict[str, Any]],
    suppliers: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    strict_extra_body: bool = False,
) -> list[dict[str, Any]]:
    default_candidates = default_settings()["debater_presets"]
    source_presets = raw_presets if isinstance(raw_presets, list) else base_presets
    existing_by_id = {
        _text(preset.get("id")): preset
        for preset in base_presets
        if isinstance(preset, dict) and _text(preset.get("id"))
    }
    supplier_ids = [_text(supplier.get("id")) for supplier in suppliers if _text(supplier.get("id"))]
    tool_ids = [_text(tool.get("id")) for tool in tools if _text(tool.get("id"))]
    fallback_supplier_id = supplier_ids[0] if supplier_ids else ""
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
        requested_supplier_id = _text(raw_preset.get("supplier_id"), _text(existing_preset.get("supplier_id")) if existing_preset else "")
        if requested_supplier_id not in supplier_ids:
            requested_supplier_id = fallback_supplier_id
        normalized_preset = {
            "id": requested_id or _text(existing_preset.get("id") if existing_preset else "") or _create_preset_id(),
            "name": fallback_name,
            "supplier_id": requested_supplier_id,
            "model": _text(raw_preset.get("model"), _text(existing_preset.get("model")) if existing_preset else fallback_default.get("model", "")),
            "azure_deployment": _text(
                raw_preset.get("azure_deployment"),
                _text(existing_preset.get("azure_deployment")) if existing_preset else fallback_default.get("azure_deployment", ""),
            ),
            "max_tokens": _positive_int(raw_preset.get("max_tokens"), _positive_int((existing_preset or {}).get("max_tokens"), fallback_default.get("max_tokens", 8000))),
            "extra_body": _normalize_extra_body(
                raw_preset.get("extra_body"),
                existing_preset.get("extra_body") if existing_preset and isinstance(existing_preset.get("extra_body"), dict) else fallback_default.get("extra_body"),
                strict=strict_extra_body,
            ),
            "tool_selection": _normalize_tool_selection(
                raw_preset.get("tool_selection"),
                existing_preset.get("tool_selection") if existing_preset and isinstance(existing_preset.get("tool_selection"), dict) else fallback_default.get("tool_selection"),
                tool_ids,
                legacy_search=raw_preset.get("search") if isinstance(raw_preset.get("search"), dict) else None,
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
        fallback[0]["supplier_id"] = fallback[0].get("supplier_id") if fallback[0].get("supplier_id") in supplier_ids else fallback_supplier_id
        fallback[0]["tool_selection"] = _normalize_tool_selection(fallback[0].get("tool_selection"), None, tool_ids)
        fallback[0].pop("search", None)
        if not _text(fallback[0].get("id")):
            fallback[0]["id"] = _create_preset_id()
        if not _text(fallback[0].get("name")):
            fallback[0]["name"] = "Debater Preset 1"
    return fallback


def _normalize_judge_settings(
    raw_judge: Any,
    base_judge: dict[str, Any],
    suppliers: list[dict[str, Any]],
    *,
    strict_extra_body: bool = False,
) -> dict[str, Any]:
    default_judge = default_settings()["judge"]
    judge = raw_judge if isinstance(raw_judge, dict) else {}
    base_judge = base_judge if isinstance(base_judge, dict) else default_judge
    supplier_ids = [_text(supplier.get("id")) for supplier in suppliers if _text(supplier.get("id"))]
    fallback_supplier_id = supplier_ids[0] if supplier_ids else ""
    requested_supplier_id = _text(judge.get("supplier_id"), _text(base_judge.get("supplier_id"), default_judge.get("supplier_id", "")))
    if requested_supplier_id not in supplier_ids:
        requested_supplier_id = fallback_supplier_id

    return {
        "supplier_id": requested_supplier_id,
        "model": _text(judge.get("model"), _text(base_judge.get("model"), default_judge.get("model", ""))),
        "azure_deployment": _text(
            judge.get("azure_deployment"),
            _text(base_judge.get("azure_deployment"), default_judge.get("azure_deployment", "")),
        ),
        "max_tokens": _positive_int(judge.get("max_tokens"), _positive_int(base_judge.get("max_tokens"), default_judge.get("max_tokens", 4096))),
        "extra_body": _normalize_extra_body(
            judge.get("extra_body"),
            base_judge.get("extra_body") if isinstance(base_judge.get("extra_body"), dict) else default_judge.get("extra_body"),
            strict=strict_extra_body,
        ),
    }


def _resolve_selected_preset_id(selected_id: Any, presets: list[dict[str, Any]], fallback_index: int = 0) -> str:
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
    defaults = default_settings()
    base = _prepare_payload(base_settings) if isinstance(base_settings, dict) else defaults
    payload = _prepare_payload(raw_settings)

    judge_source = payload["judge"] if isinstance(payload.get("judge"), dict) else base["judge"]
    suppliers_source = payload["model_suppliers"] if "model_suppliers" in payload else base.get("model_suppliers", defaults["model_suppliers"])
    normalized_suppliers = _normalize_model_suppliers(
        suppliers_source,
        base.get("model_suppliers", defaults["model_suppliers"]),
    )
    tools_source = payload["tool_configs"] if "tool_configs" in payload else base.get("tool_configs", defaults["tool_configs"])
    normalized_tools = _normalize_tool_configs(
        tools_source,
        base.get("tool_configs", defaults["tool_configs"]),
    )
    presets_source = payload["debater_presets"] if "debater_presets" in payload else base["debater_presets"]
    normalized_presets = _normalize_debater_presets(
        presets_source,
        base["debater_presets"],
        normalized_suppliers,
        normalized_tools,
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
        "judge": _normalize_judge_settings(
            judge_source,
            base.get("judge", defaults["judge"]),
            normalized_suppliers,
            strict_extra_body=strict_extra_body,
        ),
        "model_suppliers": normalized_suppliers,
        "tool_configs": normalized_tools,
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


def _resolve_search_from_tool_selection(
    selection: dict[str, Any],
    tools_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    default_search = _default_search()
    enabled_tool_ids = selection.get("enabled_tool_ids") if isinstance(selection.get("enabled_tool_ids"), list) else []
    selected_tool = None
    for tool_id in enabled_tool_ids:
        candidate = tools_by_id.get(_text(tool_id))
        template_id = _text(candidate.get("template_id"), _text(candidate.get("type"), "")) if candidate else ""
        if candidate and template_id == "tavily_search" and _coerce_bool(candidate.get("enabled"), False):
            selected_tool = candidate
            break

    mode = _text(selection.get("mode"), default_search["mode"]).lower()
    if mode not in VALID_TOOL_MODES:
        mode = default_search["mode"]
    max_tool_rounds = _positive_int(selection.get("max_tool_rounds"), default_search["max_tool_rounds"])

    if not selected_tool:
        return {
            **deepcopy(default_search),
            "enabled": False,
            "mode": mode,
            "api_key": "",
            "max_tool_rounds": max_tool_rounds,
            "tool_ids": [_text(tool_id) for tool_id in enabled_tool_ids if _text(tool_id)],
        }

    return {
        "enabled": True,
        "mode": mode,
        "api_key": _text(selected_tool.get("api_key")),
        "timeout": _positive_int(selected_tool.get("timeout"), default_search["timeout"]),
        "max_results": max(1, min(_positive_int(selected_tool.get("max_results"), default_search["max_results"]), 10)),
        "search_depth": _text(selected_tool.get("search_depth"), default_search["search_depth"]) or default_search["search_depth"],
        "max_tool_rounds": max_tool_rounds,
        "tool_id": selected_tool.get("id"),
        "tool_name": selected_tool.get("name"),
        "tool_template_id": selected_tool.get("template_id"),
        "tool_type": selected_tool.get("type"),
    }


def _merge_supplier_with_preset(
    preset: dict[str, Any],
    suppliers_by_id: dict[str, dict[str, Any]],
    fallback_supplier: dict[str, Any],
    tools_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    supplier = suppliers_by_id.get(_text(preset.get("supplier_id"))) or fallback_supplier
    provider = _text(supplier.get("provider"), "chatopenai").lower()
    azure_deployment = _text(preset.get("azure_deployment")) or (_text(preset.get("model")) if provider == "azure" else "")
    selection = preset.get("tool_selection") if isinstance(preset.get("tool_selection"), dict) else _default_tool_selection()
    return {
        "preset_id": preset.get("id"),
        "preset_name": _text(preset.get("name")),
        "supplier_id": supplier.get("id"),
        "supplier_name": _text(supplier.get("name")),
        "provider": provider,
        "model": _text(preset.get("model")),
        "api_key": _text(supplier.get("api_key")),
        "base_url": _text(supplier.get("base_url")),
        "extra_body": deepcopy(preset.get("extra_body")) if isinstance(preset.get("extra_body"), dict) else {},
        "azure_deployment": azure_deployment,
        "api_version": _text(supplier.get("api_version")),
        "max_tokens": _positive_int(preset.get("max_tokens"), 8000),
        "timeout": _positive_int(supplier.get("timeout"), 300),
        "max_retries": _positive_int(supplier.get("max_retries"), 2),
        "tool_selection": deepcopy(selection),
        "search": _resolve_search_from_tool_selection(selection, tools_by_id),
    }


def _merge_supplier_with_judge(
    judge: dict[str, Any],
    suppliers_by_id: dict[str, dict[str, Any]],
    fallback_supplier: dict[str, Any],
) -> dict[str, Any]:
    supplier = suppliers_by_id.get(_text(judge.get("supplier_id"))) or fallback_supplier
    provider = _text(supplier.get("provider"), "chatopenai").lower()
    azure_deployment = _text(judge.get("azure_deployment")) or (_text(judge.get("model")) if provider == "azure" else "")
    return {
        "supplier_id": supplier.get("id"),
        "supplier_name": _text(supplier.get("name")),
        "provider": provider,
        "model": _text(judge.get("model")),
        "api_key": _text(supplier.get("api_key")),
        "base_url": _text(supplier.get("base_url")),
        "extra_body": deepcopy(judge.get("extra_body")) if isinstance(judge.get("extra_body"), dict) else {},
        "azure_deployment": azure_deployment,
        "api_version": _text(supplier.get("api_version")),
        "max_tokens": _positive_int(judge.get("max_tokens"), 4096),
        "timeout": _positive_int(supplier.get("timeout"), 120),
        "max_retries": _positive_int(supplier.get("max_retries"), 2),
    }


def _resolve_runtime_settings(raw_settings: dict[str, Any]) -> dict[str, Any]:
    defaults = default_settings()
    normalized = normalize_settings(raw_settings)
    suppliers = normalized.get("model_suppliers") or defaults["model_suppliers"]
    tools = normalized.get("tool_configs") or defaults["tool_configs"]
    presets = normalized.get("debater_presets") or defaults["debater_presets"]
    suppliers_by_id = {
        _text(supplier.get("id")): supplier
        for supplier in suppliers
        if isinstance(supplier, dict) and _text(supplier.get("id"))
    }
    tools_by_id = {
        _text(tool.get("id")): tool
        for tool in tools
        if isinstance(tool, dict) and _text(tool.get("id"))
    }
    fallback_supplier = suppliers[0] if suppliers else defaults["model_suppliers"][0]

    pro_preset_id = _resolve_selected_preset_id(normalized.get("pro_preset_id"), presets)
    con_preset_id = _resolve_selected_preset_id(normalized.get("con_preset_id"), presets, fallback_index=1 if len(presets) > 1 else 0)
    presets_by_id = {
        _text(preset.get("id")): preset
        for preset in presets
        if isinstance(preset, dict) and _text(preset.get("id"))
    }
    pro_preset = deepcopy(presets_by_id.get(pro_preset_id) or presets[0])
    con_preset = deepcopy(presets_by_id.get(con_preset_id) or presets[min(1, len(presets) - 1)])

    return {
        "judge": _merge_supplier_with_judge(deepcopy(normalized.get("judge") or defaults["judge"]), suppliers_by_id, fallback_supplier),
        "pro": _merge_supplier_with_preset(pro_preset, suppliers_by_id, fallback_supplier, tools_by_id),
        "con": _merge_supplier_with_preset(con_preset, suppliers_by_id, fallback_supplier, tools_by_id),
        "model_suppliers": deepcopy(suppliers),
        "tool_configs": deepcopy(tools),
        "debater_presets": deepcopy(presets),
        "pro_preset_id": pro_preset_id,
        "con_preset_id": con_preset_id,
        "context_rounds": _normalize_context_rounds(normalized.get("context_rounds"), DEFAULT_CONTEXT_ROUNDS),
        "usage_tracking_enabled": _coerce_bool(normalized.get("usage_tracking_enabled"), False),
    }
