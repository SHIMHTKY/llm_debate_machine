"""用户消息与 runtime 初始恢复相关辅助函数。

这个模块处理的是“会话 JSON”和“运行时状态”之间最容易混淆的一层：

1. 用户插话在 session 里应该长什么样。
2. 用户插话在 runtime 的 `debate_history` 里应该长什么样。
3. 定向发送给正方 / 反方时，后端内部应该如何表示。
4. 当运行任务中断、恢复、重新加载会话时，如何从 session 重建基础 runtime。

这里故意把这些函数集中放在一起，是因为它们都围绕同一个主题：
“一条用户消息在不同层里的等价表示”。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from ...debate.engine import create_runtime_state


def normalize_target_role(target_role: Any) -> str | None:
    """把发送对象规整成内部统一使用的 `pro` / `con`。

    前端、旧记录、手工改 JSON 时，目标角色字段可能写成：
    - `pro`
    - `con`
    - 空字符串
    - `None`
    - 大小写混合文本

    这里统一折叠后，后续其它函数都只需要处理：
    - `"pro"`
    - `"con"`
    - `None`
    这三种情况。
    """

    role = str(target_role or "").strip().lower()
    return role if role in {"pro", "con"} else None


def required_response_roles(target_role: str | None) -> list[str]:
    """把发送对象扩展成“必须正式回应的角色集合”。

    设计规则是：
    - 如果用户没有指定发送对象，则双方都应该看到，也都需要正式回应一次。
    - 如果用户指定了正方或反方，则只有那一方需要正式回应。
    """

    normalized = normalize_target_role(target_role)
    return [normalized] if normalized else ["pro", "con"]


def user_target_badge(target_role: str | None) -> str:
    """生成前端、日志和导出记录共用的“发送对象标签文案”。"""

    normalized = normalize_target_role(target_role)
    if normalized == "pro":
        return "发送正方"
    if normalized == "con":
        return "发送反方"
    return ""


def format_user_detail_message(content: str, target_role: str | None) -> str:
    """生成写入 detail 日志时使用的正文。

    如果这条用户消息是定向发送的，就在正文前补一行标签；
    如果不是定向发送，则直接写正文本身。
    """

    badge = user_target_badge(target_role)
    body = str(content or "").strip()
    return f"{badge}\n\n{body}" if badge else body


def create_user_message_payload(
    message_id: str,
    content: str,
    *,
    locked: bool,
    target_role: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """构造要写入 session JSON 的用户消息对象。

    session 层的消息对象是“面向存储和前端展示”的：
    - `role` / `label` 主要给前端渲染用。
    - `locked` 用来判断这条消息还能不能撤回修改。
    - `timestamp` 用于界面显示时间和导出记录。
    """

    payload = {
        "id": message_id,
        "type": "user_message",
        "role": "user",
        # 界面标题已经统一改成“用户发言”，这里也保持一致。
        "label": "用户发言",
        "content": content,
        "locked": locked,
        "timestamp": timestamp or datetime.now().astimezone().isoformat(timespec="seconds"),
        "persist": True,
    }

    normalized_target_role = normalize_target_role(target_role)
    if normalized_target_role:
        payload["target_role"] = normalized_target_role
    return payload


def create_user_history_item(
    message_id: str,
    content: str,
    *,
    locked: bool,
    target_role: str | None = None,
) -> dict[str, Any]:
    """构造运行时 `debate_history` 使用的用户消息对象。

    注意：runtime 层比 session 层多两组关键字段：
    - `required_response_roles`
    - `responded_roles`

    这是因为模型提示词需要知道：
    - 哪一方还欠这条用户消息一个正式回应。
    - 哪一方已经回应过，后续只需要继续纳入论证考量。
    """

    history_item = {
        "id": message_id,
        "kind": "user",
        "role": "user",
        "content": content,
        # 用户消息不占正式轮次，所以 round 始终是 None。
        "round": None,
        "locked": locked,
        "required_response_roles": required_response_roles(target_role),
        "responded_roles": [],
    }

    normalized_target_role = normalize_target_role(target_role)
    if normalized_target_role:
        history_item["target_role"] = normalized_target_role
    return history_item


def build_runtime_from_session(session: dict[str, Any]) -> dict[str, Any]:
    """从 session 恢复 runtime_state，并补齐后续代码依赖的字段。

    恢复逻辑分两种：
    1. 如果 session 里已经有 `runtime_state`，优先复用。
    2. 如果没有，就按会话元数据重新创建最初 runtime。

    第一种适用于正常运行中断、暂停、恢复；
    第二种适用于老记录兼容、损坏会话兜底等情况。
    """

    runtime = deepcopy(session.get("runtime_state"))
    if isinstance(runtime, dict):
        # 老记录里可能缺少后来新增的字段，所以这里做一次补齐。
        runtime.setdefault("phase", "judge_initialize")
        runtime.setdefault("debate_history", [])
        runtime.setdefault("usage_timeline", [])
        return runtime

    return create_runtime_state(
        topic=str(session.get("topic") or ""),
        min_rounds=int(session.get("min_rounds") or 1),
        max_rounds=int(session.get("max_rounds") or 1),
    )
