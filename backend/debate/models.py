from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from langchain_openai import AzureChatOpenAI, ChatOpenAI


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _optional_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value:
        return deepcopy(value)
    return None


def _compact_kwargs(raw_kwargs: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in raw_kwargs.items():
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        if isinstance(value, dict) and not value:
            continue
        compacted[key] = value
    return compacted


def _normalize_chat_response_payload(response: Any) -> Any:
    if isinstance(response, (bytes, bytearray)):
        response = response.decode("utf-8", errors="ignore")

    if isinstance(response, str):
        text = response.strip()
        if not text:
            raise ValueError("模型返回了空字符串，无法解析为结构化聊天响应。")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            preview = text[:400]
            suffix = "..." if len(text) > 400 else ""
            raise ValueError(f"模型返回了非 JSON 字符串响应，无法解析：{preview}{suffix}") from exc

    return response


class CompatibleChatOpenAI(ChatOpenAI):
    def _create_chat_result(self, response: Any, generation_info: dict | None = None):
        return super()._create_chat_result(_normalize_chat_response_payload(response), generation_info)


class CompatibleAzureChatOpenAI(AzureChatOpenAI):
    def _create_chat_result(self, response: Any, generation_info: dict | None = None):
        return super()._create_chat_result(_normalize_chat_response_payload(response), generation_info)


def build_llm(model_settings: dict[str, Any]):
    provider = _clean_text(model_settings.get("provider")).lower() or "chatopenai"
    common_kwargs = {
        "max_tokens": _optional_positive_int(model_settings.get("max_tokens")),
        "timeout": _optional_positive_int(model_settings.get("timeout")),
        "max_retries": _optional_positive_int(model_settings.get("max_retries")) or 2,
    }

    if provider == "azure":
        kwargs = _compact_kwargs(
            {
                "model": _clean_text(model_settings.get("model")),
                "api_key": _clean_text(model_settings.get("api_key")),
                "azure_endpoint": _clean_text(model_settings.get("base_url")),
                "azure_deployment": _clean_text(model_settings.get("azure_deployment")),
                "api_version": _clean_text(model_settings.get("api_version")),
                **common_kwargs,
            }
        )
        return CompatibleAzureChatOpenAI(**kwargs)

    kwargs = _compact_kwargs(
        {
            "model": _clean_text(model_settings.get("model")) or "gpt-4o-mini",
            "api_key": _clean_text(model_settings.get("api_key")),
            "base_url": _clean_text(model_settings.get("base_url")),
            "extra_body": _optional_mapping(model_settings.get("extra_body")),
            **common_kwargs,
        }
    )
    return CompatibleChatOpenAI(**kwargs)
