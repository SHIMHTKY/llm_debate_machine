"""辩论运行管理器的公共入口。

真正实现已经按职责拆入 `backend.api.manager_parts`：
- `base.py`：异常类型、基础初始化、容量控制。
- `events.py`：SSE 事件与广播。
- `support.py`：纯辅助方法、配置恢复、会话视图拼装。
- `session_messages.py`：用户插话、撤回修改、改标题。
- `rewind.py`：截断撤回与从记录恢复。
- `runtime.py`：启动、暂停、恢复、终止与后台主循环。

这里保留一个很薄的兼容入口，原因是外部模块仍然通过：
`from backend.api.manager import DebateRunManager`
来拿运行管理器。
"""

from __future__ import annotations

from .manager_parts.base import BaseDebateRunManager, DebateCapacityError, DebateResumeError, DebateStateError
from .manager_parts.events import EventManagerMixin
from .manager_parts.rewind import RewindManagerMixin
from .manager_parts.runtime import RuntimeManagerMixin
from .manager_parts.session_messages import SessionMessageManagerMixin
from .manager_parts.support import SupportManagerMixin


class DebateRunManager(
    RuntimeManagerMixin,
    RewindManagerMixin,
    SessionMessageManagerMixin,
    SupportManagerMixin,
    EventManagerMixin,
    BaseDebateRunManager,
):
    """组合所有职责模块后的最终管理器。

    Mixin 的顺序不是随便排的：
    - 越上层的 mixin，越可能覆盖或扩展更基础的方法。
    - `BaseDebateRunManager` 放在最后，提供真正的底座能力。
    """


__all__ = [
    "DebateCapacityError",
    "DebateResumeError",
    "DebateRunManager",
    "DebateStateError",
]
