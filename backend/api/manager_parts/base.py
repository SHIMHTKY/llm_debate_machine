"""manager 基础能力：异常定义、初始化、任务计数。"""

from __future__ import annotations

import asyncio
from typing import Any

from ...storage.sessions import SessionStore


class DebateCapacityError(RuntimeError):
    """并发辩论数量超过当前进程上限。"""


class DebateStateError(RuntimeError):
    """会话状态不满足当前操作要求。"""


class DebateResumeError(RuntimeError):
    """恢复辩论时，当前设置已无法满足原会话快照要求。"""


class BaseDebateRunManager:
    """提供所有 mixin 共享的基础字段与轻量方法。"""

    MAX_CONCURRENT_DEBATES = 3

    def __init__(self, store: SessionStore | None = None) -> None:
        self.store = store or SessionStore()
        self.tasks: dict[str, asyncio.Task] = {}
        self.subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self.task_commands: dict[str, dict[str, str]] = {}
        self._task_lock = asyncio.Lock()

    def _prune_finished_tasks(self) -> None:
        """把已经结束的 asyncio 任务从任务表里移除。"""

        for session_id, task in list(self.tasks.items()):
            if task.done():
                self.tasks.pop(session_id, None)

    def running_count(self) -> int:
        """返回当前仍在运行的辩论数量。"""

        self._prune_finished_tasks()
        return sum(1 for task in self.tasks.values() if not task.done())

    def is_running(self, session_id: str) -> bool:
        """判断某个 session 当前是否仍有活跃任务。"""

        task = self.tasks.get(session_id)
        return task is not None and not task.done()
