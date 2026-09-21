"""usage 统计的合并、求差与截断回算。

这层代码的核心任务是：
让“整场累计 usage”和“单阶段增量 usage”都能被精确维护，
从而支持下面这些能力：

1. 正常运行时实时累计 token / 搜索次数。
2. 截断撤回后，只保留撤回前真正发生过的那部分消耗。
3. 从已完成记录恢复辩论时，副本的 usage 也能正确回算。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...debate.logger import TRACKED_ROLES
from .messages import build_runtime_from_session


def empty_usage_stage_stats() -> dict[str, Any]:
    """创建“阶段级” usage 统计桶。"""

    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "call_count": 0,
        "estimated": False,
    }


def empty_usage_role_stats() -> dict[str, Any]:
    """创建“角色级” usage 统计桶。"""

    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "call_count": 0,
        "search_calls": 0,
        "estimated": False,
        "stages": {},
    }


def empty_usage_summary(*, enabled: bool) -> dict[str, Any]:
    """创建标准 usage 汇总结构。"""

    if not enabled:
        return {"enabled": False}
    return {
        "enabled": True,
        "has_estimates": False,
        "roles": {role: empty_usage_role_stats() for role in TRACKED_ROLES},
        "totals": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "call_count": 0,
            "search_calls": 0,
        },
    }


def combine_usage_summaries(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any] | None:
    """合并两份累计 usage 汇总。

    这个函数用于“把多段增量累加成一份总账”。
    典型场景：
    - 把 usage_timeline 里多条阶段增量重新汇总成当前会话总 usage。
    """

    if not isinstance(existing, dict) or not existing.get("enabled"):
        return deepcopy(incoming) if isinstance(incoming, dict) else None
    if not isinstance(incoming, dict) or not incoming.get("enabled"):
        return deepcopy(existing)

    merged = deepcopy(existing)
    merged["enabled"] = True
    merged["has_estimates"] = bool(existing.get("has_estimates") or incoming.get("has_estimates"))

    roles = merged.setdefault("roles", {})
    incoming_roles = incoming.get("roles") if isinstance(incoming.get("roles"), dict) else {}
    for role, incoming_role_stats in incoming_roles.items():
        role_stats = roles.setdefault(role, empty_usage_role_stats())

        # 先累加角色总账。
        for key in ("input_tokens", "output_tokens", "total_tokens", "call_count", "search_calls"):
            role_stats[key] = int(role_stats.get(key) or 0) + int(incoming_role_stats.get(key) or 0)
        role_stats["estimated"] = bool(role_stats.get("estimated") or incoming_role_stats.get("estimated"))

        # 再累加该角色下每个阶段的小账本。
        merged_stages = role_stats.setdefault("stages", {})
        incoming_stages = incoming_role_stats.get("stages") if isinstance(incoming_role_stats.get("stages"), dict) else {}
        for stage_name, incoming_stage_stats in incoming_stages.items():
            stage_stats = merged_stages.setdefault(stage_name, empty_usage_stage_stats())
            for key in ("input_tokens", "output_tokens", "total_tokens", "call_count"):
                stage_stats[key] = int(stage_stats.get(key) or 0) + int(incoming_stage_stats.get(key) or 0)
            stage_stats["estimated"] = bool(stage_stats.get("estimated") or incoming_stage_stats.get("estimated"))

    totals = merged.setdefault("totals", {})
    incoming_totals = incoming.get("totals") if isinstance(incoming.get("totals"), dict) else {}
    for key in ("input_tokens", "output_tokens", "total_tokens", "call_count", "search_calls"):
        totals[key] = int(totals.get(key) or 0) + int(incoming_totals.get(key) or 0)

    return merged


def diff_usage_summaries(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any] | None:
    """计算两次 usage 快照之间的增量。"""

    if not isinstance(current, dict) or not current.get("enabled"):
        return None

    baseline = previous if isinstance(previous, dict) and previous.get("enabled") else empty_usage_summary(enabled=True)
    delta = empty_usage_summary(enabled=True)

    current_roles = current.get("roles") if isinstance(current.get("roles"), dict) else {}
    baseline_roles = baseline.get("roles") if isinstance(baseline.get("roles"), dict) else {}

    for role in TRACKED_ROLES:
        current_role = current_roles.get(role) if isinstance(current_roles.get(role), dict) else {}
        baseline_role = baseline_roles.get(role) if isinstance(baseline_roles.get(role), dict) else {}
        role_delta = delta["roles"][role]

        # 角色总账用“当前累计 - 上次累计”求出本阶段增量。
        for key in ("input_tokens", "output_tokens", "total_tokens", "call_count", "search_calls"):
            role_delta[key] = max(0, int(current_role.get(key) or 0) - int(baseline_role.get(key) or 0))
        role_delta["estimated"] = bool(current_role.get("estimated") and role_delta["call_count"] > 0)

        current_stages = current_role.get("stages") if isinstance(current_role.get("stages"), dict) else {}
        baseline_stages = baseline_role.get("stages") if isinstance(baseline_role.get("stages"), dict) else {}
        for stage_name in sorted(set(current_stages) | set(baseline_stages)):
            current_stage = current_stages.get(stage_name) if isinstance(current_stages.get(stage_name), dict) else {}
            baseline_stage = baseline_stages.get(stage_name) if isinstance(baseline_stages.get(stage_name), dict) else {}
            stage_delta = empty_usage_stage_stats()
            for key in ("input_tokens", "output_tokens", "total_tokens", "call_count"):
                stage_delta[key] = max(0, int(current_stage.get(key) or 0) - int(baseline_stage.get(key) or 0))
            stage_delta["estimated"] = bool(current_stage.get("estimated") and stage_delta["call_count"] > 0)
            if any(stage_delta[key] for key in ("input_tokens", "output_tokens", "total_tokens", "call_count")) or stage_delta["estimated"]:
                role_delta.setdefault("stages", {})[stage_name] = stage_delta

    current_totals = current.get("totals") if isinstance(current.get("totals"), dict) else {}
    baseline_totals = baseline.get("totals") if isinstance(baseline.get("totals"), dict) else {}
    for key in ("input_tokens", "output_tokens", "total_tokens", "call_count", "search_calls"):
        delta["totals"][key] = max(0, int(current_totals.get(key) or 0) - int(baseline_totals.get(key) or 0))

    delta["has_estimates"] = bool(current.get("has_estimates") and delta["totals"]["call_count"] > 0)
    if not any(delta["totals"][key] for key in ("input_tokens", "output_tokens", "total_tokens", "call_count", "search_calls")):
        return None
    return delta


def append_usage_timeline_entry(
    runtime: dict[str, Any],
    *,
    phase: str,
    usage_delta: dict[str, Any] | None,
    message_id: str | None = None,
) -> None:
    """向 runtime 追加一条可回算的 usage 时间线记录。"""

    if not isinstance(usage_delta, dict) or not usage_delta.get("enabled"):
        return
    # 除了 judge_initialize 之外，其余阶段都应该能够关联到一条具体消息。
    if phase != "judge_initialize" and not str(message_id or "").strip():
        return
    runtime.setdefault("usage_timeline", []).append(
        {
            "phase": phase,
            "message_id": str(message_id or "").strip() or None,
            "usage_delta": deepcopy(usage_delta),
        }
    )


def rebuild_usage_tracking(
    session: dict[str, Any],
    kept_messages: list[dict[str, Any]],
    rebuilt_runtime: dict[str, Any],
) -> dict[str, Any] | None:
    """在截断恢复后，按保留消息重新计算累计 usage。"""

    current_usage = deepcopy(session.get("usage_stats")) if isinstance(session.get("usage_stats"), dict) else None
    if isinstance(current_usage, dict) and not current_usage.get("enabled"):
        rebuilt_runtime["usage_timeline"] = []
        return current_usage

    runtime_source = build_runtime_from_session(session)
    raw_timeline = runtime_source.get("usage_timeline")
    if not isinstance(raw_timeline, list) or not raw_timeline:
        # 老记录没有 timeline 时，当前只能回退到旧行为。
        rebuilt_runtime["usage_timeline"] = []
        return None

    kept_ids = {str(message.get("id") or "").strip() for message in kept_messages if str(message.get("id") or "").strip()}
    current_phase = str(rebuilt_runtime.get("phase") or "judge_initialize")
    filtered_timeline: list[dict[str, Any]] = []
    all_timeline_usage: dict[str, Any] | None = None

    for entry in raw_timeline:
        if not isinstance(entry, dict):
            continue
        phase = str(entry.get("phase") or "").strip()
        message_id = str(entry.get("message_id") or "").strip()
        usage_delta = entry.get("usage_delta")
        if not isinstance(usage_delta, dict) or not usage_delta.get("enabled"):
            continue
        all_timeline_usage = combine_usage_summaries(all_timeline_usage, usage_delta)

        include = False
        if message_id:
            # 有消息 ID 的阶段，只要那条消息还在，就说明这段消耗也应该保留。
            include = message_id in kept_ids
        elif phase == "judge_initialize":
            # 拆题阶段没有普通消息，但只要当前不是重新回到 judge_initialize，
            # 就说明这一步在恢复后的会话里仍然算“已经发生过”。
            include = current_phase != "judge_initialize"

        if include:
            filtered_timeline.append(
                {
                    "phase": phase,
                    "message_id": message_id or None,
                    "usage_delta": deepcopy(usage_delta),
                }
            )

    rebuilt_runtime["usage_timeline"] = filtered_timeline

    merged_usage: dict[str, Any] | None = None
    for entry in filtered_timeline:
        merged_usage = combine_usage_summaries(merged_usage, entry.get("usage_delta"))

    # A pause can happen after the model/tool has consumed tokens but before the
    # phase emits its durable message and timeline entry. Keep that real cost in
    # the rebuilt record without falsely attaching it to a removed message.
    interrupted_usage = diff_usage_summaries(all_timeline_usage, current_usage) if all_timeline_usage is not None else None
    merged_usage = combine_usage_summaries(merged_usage, interrupted_usage)
    return merged_usage
