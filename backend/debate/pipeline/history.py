"""辩论历史相关规则。

这个模块专门处理“历史怎么看、怎么裁剪、谁能看到什么”这类问题。
这样做的目的，是把模型提示词构造里的上下文规则从阶段函数里剥离出来，
避免每个阶段都自己拼一套相似但不完全相同的历史逻辑。
"""

from __future__ import annotations

from typing import Literal

from ..state import DebateHistoryEntry, DebateState


def history_role_name(item: dict, perspective_role: str | None = None) -> str:
    """把历史项转换成面向某一方视角的可读角色名。"""

    role = str(item.get("role") or "")
    if role == "pro":
        return "正方"
    if role == "con":
        return "反方"
    if role == "user" and perspective_role in {"pro", "con"}:
        required_roles = item.get("required_response_roles") or ["pro", "con"]
        responded_roles = item.get("responded_roles") or []
        if perspective_role in required_roles and perspective_role not in responded_roles:
            return "观众/裁判要求（待你本轮正式回应）"
        if perspective_role in responded_roles:
            return "观众/裁判要求（你已正式回应，后续仅供参考）"
    return "观众/裁判要求"


def user_message_visible_to_role(item: dict, perspective_role: str | None = None) -> bool:
    """判断一条用户消息是否应进入当前角色的上下文。"""

    if str(item.get("role") or "") != "user":
        return True

    required_roles = item.get("required_response_roles") or ["pro", "con"]
    if perspective_role in {"pro", "con"}:
        return perspective_role in required_roles

    # 没有特定视角时，只展示广播给双方的用户消息。
    return set(required_roles) == {"pro", "con"}


def history_text(history: list[dict], perspective_role: str | None = None) -> str:
    """把结构化历史转成提示词里使用的纯文本。"""

    blocks: list[str] = []
    for item in history:
        if not user_message_visible_to_role(item, perspective_role):
            continue
        role_name = history_role_name(item, perspective_role)
        round_num = item.get("round")
        if round_num:
            blocks.append(f"{role_name}（第 {round_num} 轮）：{item.get('content', '')}")
        else:
            blocks.append(f"{role_name}：{item.get('content', '')}")
    return "\n\n".join(blocks)


def pending_user_requirements(history: list[DebateHistoryEntry], role: str) -> list[DebateHistoryEntry]:
    """找出某一方此刻仍未正式回应的用户要求。"""

    pending: list[DebateHistoryEntry] = []
    for item in history:
        if str(item.get("role") or "") != "user":
            continue
        required_roles = item.get("required_response_roles") or ["pro", "con"]
        responded_roles = item.get("responded_roles") or []
        if role in required_roles and role not in responded_roles:
            pending.append(item)
    return pending


def render_pending_user_requirement_notice(history: list[DebateHistoryEntry], role: str) -> str:
    """渲染插入到提示词最前面的“待回应观众要求”提醒。"""

    pending_items = pending_user_requirements(history, role)
    if not pending_items:
        return ""

    heading = (
        "注意：以下观众/裁判要求尚未被你直接回应。你本轮发言必须先正式回应观众，再进入本轮正文："
        if len(pending_items) == 1
        else "注意：以下观众/裁判要求尚未被你直接回应。你本轮发言必须先正式回应观众，并逐条回应后再进入本轮正文："
    )
    details = "\n\n".join(
        f"{index}. {str(item.get('content') or '').strip()}"
        for index, item in enumerate(pending_items, start=1)
    )
    return (
        f"{heading}\n"
        "请先在发言开头加入一段自然、正式的回应观众内容，把这些要求当作观众席的现场提问或要求来回答；"
        "这段回应必须属于你的发言正文，不能写成备注、提纲、系统说明或 JSON；也不要使用 Markdown 加粗、标题、分隔线，"
        "不要写“回应观众：”或“本轮发言正文：”这类标签。只有这里明确列出的要求需要你本轮正式回应；"
        "你已经正式回应过的历史观众要求，后续轮次不要再次正式回应，只需继续纳入论证考量。\n"
        f"{details}"
    )


def mark_user_requirements_responded(history: list[DebateHistoryEntry], role: str) -> list[DebateHistoryEntry]:
    """把当前角色应答过的用户消息标记为已回应。"""

    updated_history: list[DebateHistoryEntry] = []
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


def build_context_history(history: list[DebateHistoryEntry], history_window_size: int) -> list[DebateHistoryEntry]:
    """按模型发言窗口裁剪上下文，同时尽量保留夹在中间的用户消息。"""

    model_indices = [index for index, item in enumerate(history) if str(item.get("role") or "") in {"pro", "con"}]
    if not model_indices:
        return list(history)

    # history_window_size 以“模型发言条数”为单位，而不是总消息数。
    selected_model_indices = set(model_indices[-max(1, history_window_size):])
    context: list[DebateHistoryEntry] = []

    for index, item in enumerate(history):
        role = str(item.get("role") or "")
        if role in {"pro", "con"}:
            if index in selected_model_indices:
                context.append(item)
            continue

        if role != "user":
            continue

        # 用户消息虽然不占轮次，但只要它夹在选中的模型发言附近，
        # 就应该一并进入上下文，否则模型会失去对这条插话的记忆。
        previous_model_index = next((candidate for candidate in range(index - 1, -1, -1) if candidate in model_indices), None)
        next_model_index = next((candidate for candidate in range(index + 1, len(history)) if candidate in model_indices), None)
        if previous_model_index in selected_model_indices or next_model_index in selected_model_indices:
            context.append(item)

    return context


def resolve_context_window_size(settings: dict) -> int:
    """把“上下文轮数”转换成实际保留的模型发言条数。"""

    try:
        context_rounds = int(settings.get("context_rounds", 3))
    except (TypeError, ValueError):
        context_rounds = 3
    context_rounds = max(2, min(6, context_rounds))
    return context_rounds * 2


def check_continue(state: DebateState) -> Literal["continue", "end"]:
    """反方发言后，判断是否还需要继续下一轮。"""

    if state["debate_ended"] or state["current_round"] >= state["max_rounds"]:
        return "end"
    return "continue"


def check_after_pro(state: DebateState) -> Literal["continue", "end"]:
    """正方发言后，判断是否应立即进入裁判总结。"""

    if state["debate_ended"]:
        return "end"
    return "continue"
