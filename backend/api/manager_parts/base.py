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
    SUBSCRIBER_QUEUE_SIZE = 128

    def __init__(self, store: SessionStore | None = None) -> None:
        self.store = store or SessionStore()
        self.tasks: dict[str, asyncio.Task] = {}
        self.subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self.task_commands: dict[str, dict[str, str]] = {}
        self._phase_event_buffers: dict[str, list[dict[str, Any]]] = {}
        self._task_lock = asyncio.Lock()

    def _prune_finished_tasks(self) -> None:
        """把已经结束的 asyncio 任务从任务表里移除。"""

        for session_id, task in list(self.tasks.items()):
            if task.done():
                self.tasks.pop(session_id, None)
                self.task_commands.pop(session_id, None)

    def running_count(self) -> int:
        """返回当前仍在运行的辩论数量。"""

        self._prune_finished_tasks()
        return sum(1 for task in self.tasks.values() if not task.done())

    def is_running(self, session_id: str) -> bool:
        """判断某个 session 当前是否仍有活跃任务。"""

        task = self.tasks.get(session_id)
        return task is not None and not task.done()

    def recover_interrupted_sessions(self) -> int:
        """Turn process-local orphaned runs into resumable paused sessions."""

        recovered = 0
        for archived in (False, True):
            for summary in self.store.list_sessions(archived=archived):
                session_id = str(summary.get("id") or "")
                if not session_id or self.is_running(session_id):
                    continue
                session = self.store.load_session(session_id)
                if session is None or str(session.get("status") or "") not in {"queued", "running"}:
                    continue
                self.store.set_status(session_id, "paused")
                self.store.append_detail_note(session_id, "服务恢复", "后端进程曾中断，本场辩论已自动转为暂停状态，可手动继续。")
                recovered += 1
        return recovered

    async def shutdown(self) -> None:
        """Pause active debates before the application event loop exits."""

        async with self._task_lock:
            active_tasks = [
                (session_id, task)
                for session_id, task in self.tasks.items()
                if not task.done()
            ]
            for session_id, task in active_tasks:
                self.task_commands[session_id] = {"action": "pause", "reason": "后端服务关闭，辩论已自动暂停。"}
                task.cancel()

        if active_tasks:
            await asyncio.gather(*(task for _, task in active_tasks), return_exceptions=True)
