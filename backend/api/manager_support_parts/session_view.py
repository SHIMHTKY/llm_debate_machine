"""与会话展示和配置恢复相关的轻量辅助函数。"""

from __future__ import annotations

from copy import deepcopy

from ...config.settings import load_settings
from .messages import build_runtime_from_session


def find_preset_by_name(settings: dict, preset_name: str) -> dict | None:
    """按照会话快照里的名称，在当前设置中回查辩手配置。"""

    target = str(preset_name or "").strip()
    if not target:
        return None
    for preset in settings.get("debater_presets", []):
        if str(preset.get("name") or "").strip() == target:
            return deepcopy(preset)
    return None


def is_judge_phase(session: dict) -> bool:
    """判断当前会话是否处于裁判控制的阶段。"""

    runtime = build_runtime_from_session(session)
    phase = str(runtime.get("phase") or "")
    return phase in {"judge_initialize", "judge_summary"}


def session_display_title(session: dict) -> str:
    """解析一场辩论当前最适合展示给前端的标题。"""

    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    return str(runtime.get("debate_title") or session.get("topic") or "").strip()
