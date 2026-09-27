"""截断撤回与从记录恢复相关辅助函数。

这里负责回答三个问题：
1. 如果把某条辩手消息之后的内容全部删掉，runtime 应该怎样重建。
2. 如果保留下来的尾部刚好是一条用户消息，它是否应该恢复成可编辑草稿。
3. 给定一个“目标消息 ID”，系统应该回到哪一个 phase 继续运行。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
import uuid

from .messages import build_runtime_from_session, create_user_history_item, normalize_target_role


def mark_pending_user_requirements_responded(history: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    """把当前角色已经回应过的用户要求标记为“已回应”。

    这一步在重建历史时非常关键：
    如果只把辩手消息简单塞回历史，而不顺手更新 `responded_roles`，
    后续模型会误以为这些旧用户消息还没有被回应，从而重复正式回应。
    """

    updated_history: list[dict[str, Any]] = []
    for item in history:
        if str(item.get("role") or "") != "user":
            updated_history.append(item)
            continue

        required_roles = list(item.get("required_response_roles") or ["pro", "con"])
        responded_roles = list(item.get("responded_roles") or [])
        if role in required_roles and role not in responded_roles:
            responded_roles.append(role)
            updated_history.append(
                {
                    **item,
                    "required_response_roles": required_roles,
                    "responded_roles": responded_roles,
                }
            )
        else:
            updated_history.append(item)
    return updated_history


def rebuild_runtime_from_messages(
    session: dict[str, Any],
    kept_messages: list[dict[str, Any]],
    next_phase: str,
    *,
    title_override: str | None = None,
) -> dict[str, Any]:
    """根据保留消息前缀重建 runtime_state。

    这里的思路不是“从旧 runtime 上做局部修补”，而是：
    1. 重新创建一份最初 runtime。
    2. 再把保留下来的消息按顺序重新回放进去。

    这种方式虽然看起来更笨，但优点是状态更干净、更可预期，
    不容易留下旧阶段、旧评分、旧总结之类的残留字段。
    """

    from ...debate.engine import create_runtime_state

    topic = str(session.get("topic") or "")
    runtime_source = build_runtime_from_session(session)

    rebuilt = create_runtime_state(
        topic,
        int(session.get("min_rounds") or 1),
        int(session.get("max_rounds") or 1),
    )

    # 这些字段属于“裁判拆题阶段得到的长期上下文”，截断后仍应保留。
    rebuilt["debate_title"] = str(title_override or runtime_source.get("debate_title") or topic).strip()
    rebuilt["topic_analysis"] = str(runtime_source.get("topic_analysis") or f"围绕“{topic}”的价值、事实和现实影响展开。").strip()
    rebuilt["pro_task"] = str(runtime_source.get("pro_task") or f"作为正方，请论证为什么“{topic}”成立。").strip()
    rebuilt["con_task"] = str(runtime_source.get("con_task") or f"作为反方，请论证为什么“{topic}”不成立。").strip()

    history: list[dict[str, Any]] = []
    current_round = 0

    for message in kept_messages:
        role = str(message.get("role") or "")

        # 用户消息要先变回 runtime 的 user history item 结构。
        if role == "user":
            history.append(
                create_user_history_item(
                    str(message.get("id") or uuid.uuid4().hex),
                    str(message.get("content") or ""),
                    locked=bool(message.get("locked", True)),
                    target_role=normalize_target_role(message.get("target_role")),
                )
            )
            continue

        # 非辩手消息不会参与历史重建。
        if role not in {"pro", "con"}:
            continue

        round_num = int(message.get("round") or current_round or 0)

        # 辩手发言入历史前，要先把“他欠着的用户回应”标记掉。
        history = mark_pending_user_requirements_responded(history, role)
        history.append(
            {
                "id": str(message.get("id") or uuid.uuid4().hex),
                "kind": "speech",
                "role": role,
                "content": str(message.get("content") or ""),
                "round": round_num,
            }
        )
        current_round = max(current_round, round_num)

        # 如果保留区间里已经有人认输，那么新的 runtime 也必须保留这个事实。
        if role == "pro" and bool(message.get("conceded")):
            rebuilt["pro_conceded"] = True
            rebuilt["debate_ended"] = True
        if role == "con" and bool(message.get("conceded")):
            rebuilt["con_conceded"] = True
            rebuilt["debate_ended"] = True

    rebuilt["debate_history"] = history
    rebuilt["current_round"] = current_round
    rebuilt["phase"] = next_phase

    # 截断后所有“结局型字段”都必须清空，因为这是一场重新继续的辩论。
    rebuilt["winner"] = None
    rebuilt["pro_score"] = None
    rebuilt["con_score"] = None
    rebuilt["evaluation"] = None
    rebuilt["conclusion"] = None
    return rebuilt


def resolve_rewind_phase(message: dict[str, Any]) -> str:
    """把目标辩手发言反推成恢复后下一步要执行的 phase。"""

    role = str(message.get("role") or "")
    round_num = int(message.get("round") or 0)
    if role == "pro":
        # 如果撤回的是第一轮正方，就需要重新开篇立论。
        return "pro_first_speech" if round_num <= 1 else "pro_speech"
    if role == "con":
        return "con_first_speech" if round_num <= 1 else "con_speech"
    raise RuntimeError("只有辩手发言支持截断恢复。")


def restore_trailing_user_message(kept_messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """若保留区间最后一条是用户消息，则把它恢复成可编辑草稿。

    这一步是为了覆盖这样一种体验：
    - 你把后面的辩手发言撤掉了；
    - 结果现在最后一条变成了用户消息；
    - 这条消息应该重新允许“撤回修改”，并禁止再发第二条新消息。
    """

    normalized_messages = deepcopy(kept_messages)
    if not normalized_messages:
        return normalized_messages, None

    last_message = normalized_messages[-1]
    if str(last_message.get("role") or "") != "user":
        return normalized_messages, None

    message_id = str(last_message.get("id") or "").strip()
    content = str(last_message.get("content") or "").strip()
    if not message_id or not content:
        return normalized_messages, None

    # 关键点：不仅要恢复 active_user_message，还要把尾部消息本身解锁。
    last_message["locked"] = False
    active_user_message = {
        "id": message_id,
        "content": content,
        "target_role": normalize_target_role(last_message.get("target_role")),
        "created_at": str(last_message.get("timestamp") or "").strip() or None,
        "stage": "draft",
    }
    return normalized_messages, active_user_message


def resolve_rewind_target(
    session: dict[str, Any],
    message_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    """解析一次截断请求要删掉哪条发言，以及删后应该恢复成什么状态。"""

    messages = list(session.get("messages") or [])
    target_index = next((index for index, item in enumerate(messages) if str(item.get("id") or "") == message_id), -1)
    if target_index < 0:
        raise RuntimeError("未找到要恢复的发言。")

    target_message = messages[target_index]
    if str(target_message.get("role") or "") not in {"pro", "con"}:
        raise RuntimeError("只有辩手发言支持截断恢复。")

    # 恢复副本 / 截断撤回都只保留目标消息之前的消息。
    kept_messages, restored_active_user_message = restore_trailing_user_message(messages[:target_index])
    next_phase = resolve_rewind_phase(target_message)
    rebuilt_runtime = rebuild_runtime_from_messages(session, kept_messages, next_phase)
    return target_message, kept_messages, rebuilt_runtime, restored_active_user_message
