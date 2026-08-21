"""与会话展示和配置恢复相关的轻量辅助函数。"""

from __future__ import annotations

from copy import deepcopy

from ...config.settings_parts.normalize import _resolve_runtime_settings
from .messages import build_runtime_from_session


def find_preset(settings: dict, preset_id: str = "", preset_name: str = "") -> dict | None:
    """Resolve a saved preset by stable ID, with name fallback for old sessions."""

    target_id = str(preset_id or "").strip()
    target_name = str(preset_name or "").strip()
    if not target_id and not target_name:
        return None
    presets = [preset for preset in settings.get("debater_presets", []) if isinstance(preset, dict)]
    matched = next(
        (preset for preset in presets if target_id and str(preset.get("id") or "").strip() == target_id),
        None,
    )
    if matched is None:
        matched = next(
            (preset for preset in presets if target_name and str(preset.get("name") or "").strip() == target_name),
            None,
        )
    if matched is not None:
        preset = matched
        resolved = _resolve_runtime_settings(
            {
                "judge": deepcopy(settings.get("judge") or {}),
                "model_suppliers": deepcopy(settings.get("model_suppliers") or []),
                "tool_configs": deepcopy(settings.get("tool_configs") or []),
                "debater_presets": deepcopy(settings.get("debater_presets") or []),
                "pro_preset_id": str(preset.get("id") or ""),
                "con_preset_id": str(preset.get("id") or ""),
                "context_rounds": settings.get("context_rounds", 3),
                "usage_tracking_enabled": bool(settings.get("usage_tracking_enabled")),
            }
        )
        return deepcopy(resolved.get("pro") or {})
    return None


def find_preset_by_name(settings: dict, preset_name: str) -> dict | None:
    """Backward-compatible name-only lookup."""

    return find_preset(settings, preset_name=preset_name)


def is_judge_phase(session: dict) -> bool:
    """判断当前会话是否处于裁判控制的阶段。"""

    runtime = build_runtime_from_session(session)
    phase = str(runtime.get("phase") or "")
    return phase in {"judge_initialize", "judge_summary"}


def session_display_title(session: dict) -> str:
    """解析一场辩论当前最适合展示给前端的标题。"""

    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    return str(runtime.get("debate_title") or session.get("topic") or "").strip()
