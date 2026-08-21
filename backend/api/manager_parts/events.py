"""事件广播与 SSE 输出。

这个模块负责把后端运行中的状态变化实时推给前端。
它做的事可以概括成三层：

1. 把内部事件补齐公共字段。
2. 根据事件类型更新 session 的 `live_status` / `messages`。
3. 把事件编码成标准 SSE 文本块，送进浏览器的 EventSource。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any


class EventManagerMixin:
    """负责事件标准化、广播以及 SSE 输出。"""

    def _begin_phase_event_buffer(self, session_id: str) -> None:
        """Start buffering persistent events until the current phase commits."""

        self._phase_event_buffers[session_id] = []

    def _take_phase_event_buffer(self, session_id: str) -> list[dict[str, Any]]:
        """Return and clear the persistent events buffered for one phase."""

        return self._phase_event_buffers.pop(session_id, [])

    def _discard_phase_event_buffer(self, session_id: str) -> None:
        """Drop events from a phase that did not complete successfully."""

        self._phase_event_buffers.pop(session_id, None)

    def _broadcast_committed_phase_events(self, session_id: str, events: list[dict[str, Any]]) -> None:
        """Broadcast phase events only after their session transaction is durable."""

        for event in events:
            self._push_event(session_id, {**event, "persist": False})

    SSE_HEARTBEAT_SECONDS = 15

    def _enqueue_event(self, queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
        """Keep slow subscribers bounded while preserving the newest state."""

        try:
            queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # A concurrent producer won the slot; a later session snapshot will resync the UI.
            pass

    def _enrich_event(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """补齐前端事件依赖的公共字段。"""

        event = dict(payload)
        event.setdefault("id", uuid.uuid4().hex)
        event.setdefault("timestamp", datetime.now().astimezone().isoformat(timespec="seconds"))
        event.setdefault("session_id", session_id)
        return event

    def _push_event(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """只推送，不落盘。

        适合 `session` / `history` 这类同步型事件：
        它们只是把当前快照重新发给前端，不代表要新增一条业务消息。
        """

        event = self._enrich_event(session_id, payload)
        for queue in list(self.subscribers.get(session_id, [])):
            self._enqueue_event(queue, event)
        return event

    def _publish(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发布事件，并按事件类型同步更新 store。"""

        event = self._enrich_event(session_id, payload)
        event_type = str(event.get("type") or "")

        # status 代表“有人正在说话/思考”，应该进入 live_status。
        if event_type == "status":
            self.store.set_live_status(session_id, event)
        # 一旦真正落了一条消息、总结、报错或 done，live_status 就该清空。
        elif event_type in {"message", "summary", "error", "done"}:
            self.store.set_live_status(session_id, None)

        # 只有 persist 事件才应写入 session.messages。
        if event.get("persist"):
            phase_buffer = self._phase_event_buffers.get(session_id)
            if phase_buffer is not None:
                phase_buffer.append(event)
                return event
            else:
                self.store.append_message(session_id, event)

        for queue in list(self.subscribers.get(session_id, [])):
            self._enqueue_event(queue, event)
        return event

    def _publish_session_state(self, session_id: str) -> dict[str, Any] | None:
        """把当前完整 session 快照推给订阅端。"""

        session = self.store.load_session(session_id)
        if session is None:
            return None
        self._push_event(
            session_id,
            {
                "type": "session",
                "session": session,
                "persist": False,
            },
        )
        return session

    async def event_stream(self, session_id: str):
        """SSE 事件流入口。"""

        session = self.store.load_session(session_id)
        if session is None:
            raise KeyError(session_id)

        # 新订阅者先收到一份完整历史，这样前端不需要额外再手动补一轮初始状态。
        history_event = {
            "type": "history",
            "session": session,
            "messages": session.get("messages", []),
            "persist": False,
        }
        yield self._format_sse(history_event)

        # 如果会话已经结束，给完 history 后直接补一条 done，让前端关闭连接。
        if session.get("status") in {"completed", "error", "terminated"} and not self.is_running(session_id):
            yield self._format_sse(
                {
                    "type": "done",
                    "role": "system",
                    "label": "系统",
                    "content": "辩论已结束。",
                    "persist": False,
                }
            )
            return

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.SUBSCRIBER_QUEUE_SIZE)
        self.subscribers.setdefault(session_id, []).append(queue)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=self.SSE_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    # SSE comments keep idle connections alive without creating frontend events.
                    yield ": keep-alive\n\n"
                    continue
                yield self._format_sse(event)
                if event.get("type") == "done":
                    break
        finally:
            subscribers = self.subscribers.get(session_id, [])
            if queue in subscribers:
                subscribers.remove(queue)
            if not subscribers:
                self.subscribers.pop(session_id, None)

    def _format_sse(self, payload: dict[str, Any]) -> str:
        """把事件对象编码成标准 SSE 文本块。"""

        # 这里必须是真正的换行，而不是字面量 "\\n"。
        # EventSource 依赖空行来判断一个事件块结束。
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
