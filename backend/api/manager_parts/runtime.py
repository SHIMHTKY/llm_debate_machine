"""辩论任务的启动、暂停、恢复、终止与后台主循环。"""

from __future__ import annotations

import asyncio
import traceback

from ...config.settings import load_settings, public_settings_summary
from ...debate.engine import (
    build_runtime_result,
    create_runtime_state,
    determine_next_phase,
    merge_runtime_state,
    prepare_runtime_context,
    run_runtime_phase,
)
from ...debate.logger import DebateLogger
from .base import DebateCapacityError, DebateStateError


class RuntimeManagerMixin:
    """负责真正的异步运行生命周期。"""

    async def start_debate(self, topic: str, min_rounds: int, max_rounds: int) -> dict | None:
        """创建新会话并启动后台辩论任务。"""

        async with self._task_lock:
            # 先清掉已结束任务，保证并发数统计准确。
            self._prune_finished_tasks()
            if self.running_count() >= self.MAX_CONCURRENT_DEBATES:
                raise DebateCapacityError("已到当前进程上限。")
            if min_rounds > max_rounds:
                raise DebateStateError("最小轮数必须小于等于最大轮数。")

            settings = load_settings()
            session = self.store.create_session(
                topic=topic,
                min_rounds=min_rounds,
                max_rounds=max_rounds,
                config_summary=public_settings_summary(settings),
            )
            # 会话一创建出来，就立刻落一份最初 runtime_state，方便后续恢复和回放。
            self.store.set_runtime_state(session["id"], create_runtime_state(topic, min_rounds, max_rounds))
            task = asyncio.create_task(
                self._run_session(
                    session_id=session["id"],
                    topic=topic,
                    min_rounds=min_rounds,
                    max_rounds=max_rounds,
                    settings=settings,
                    resumed=False,
                )
            )
            self.tasks[session["id"]] = task
        return self.store.load_session(session["id"]) or session

    async def pause_debate(self, session_id: str, reason: str = "用户手动暂停") -> dict | None:
        """请求取消后台任务，并把会话转入 `paused`。"""

        session = self.store.load_session(session_id)
        if session is None:
            return None
        if session.get("status") == "paused":
            return session

        async with self._task_lock:
            self._prune_finished_tasks()
            task = self.tasks.get(session_id)
            # 如果任务已经结束，就直接返回当前会话快照。
            if task is None or task.done():
                return self.store.load_session(session_id)
            # 这里不直接修改状态，而是先记录命令，再 cancel 任务。
            # 真正如何收尾，由 `_run_session` 统一在 CancelledError 分支里处理。
            self.task_commands[session_id] = {"action": "pause", "reason": reason}
            task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass
        return self.store.load_session(session_id)

    async def resume_debate(self, session_id: str) -> dict | None:
        """从 `paused` 状态重新拉起后台任务。"""

        session = self.store.load_session(session_id)
        if session is None:
            return None
        if self.is_running(session_id):
            return session
        if session.get("status") != "paused":
            raise DebateStateError("当前辩论不处于暂停状态。")

        settings = self._build_resume_settings(session)
        # 暂停期间编辑完成但尚未继续的用户消息，在恢复前要先锁死。
        self._lock_draft_user_message(session_id)
        self.store.set_live_status(session_id, None)
        self.store.set_status(session_id, "running")
        self._publish_session_state(session_id)

        async with self._task_lock:
            self._prune_finished_tasks()
            if self.running_count() >= self.MAX_CONCURRENT_DEBATES:
                self.store.set_status(session_id, "paused")
                self._publish_session_state(session_id)
                raise DebateCapacityError("已到当前进程上限。")
            task = asyncio.create_task(
                self._run_session(
                    session_id=session_id,
                    topic=str(session.get("topic") or ""),
                    min_rounds=int(session.get("min_rounds") or 1),
                    max_rounds=int(session.get("max_rounds") or 1),
                    settings=settings,
                    resumed=True,
                )
            )
            self.tasks[session_id] = task
        return self.store.load_session(session_id)

    async def stop_debate(self, session_id: str, reason: str = "用户手动终止") -> dict | None:
        """终止一场运行中辩论；若已经暂停则直接落成 `terminated`。"""

        session = self.store.load_session(session_id)
        if session is None:
            return None

        async with self._task_lock:
            self._prune_finished_tasks()
            task = self.tasks.get(session_id)
            if task is None or task.done():
                if session.get("status") == "paused":
                    self._finalize_terminated(session_id, reason)
                return self.store.load_session(session_id)
            self.task_commands[session_id] = {"action": "terminate", "reason": reason}
            task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass
        return self.store.load_session(session_id)

    def _finalize_paused(
        self,
        session_id: str,
        reason: str,
        *,
        usage_stats: dict | None = None,
        detail_record_path: str | None = None,
        error_record_path: str | None = None,
    ) -> None:
        """把当前 session 收口成 `paused` 状态。"""

        if self.store.load_session(session_id) is None:
            return
        if detail_record_path is not None or error_record_path is not None:
            self.store.set_record_paths(session_id, detail_record_path=detail_record_path, error_record_path=error_record_path)
        if usage_stats is not None:
            self._merge_usage_stats(session_id, usage_stats)
        self.store.append_detail_note(session_id, "运行暂停", reason)
        self.store.sync_record_paths(session_id)
        self.store.set_live_status(session_id, None)
        self.store.set_status(session_id, "paused")
        self._publish_session_state(session_id)

    def _finalize_terminated(
        self,
        session_id: str,
        reason: str,
        *,
        usage_stats: dict | None = None,
        detail_record_path: str | None = None,
        error_record_path: str | None = None,
    ) -> None:
        """把当前 session 收口成 `terminated` 状态。"""

        if self.store.load_session(session_id) is None:
            return
        if detail_record_path is not None or error_record_path is not None:
            self.store.set_record_paths(session_id, detail_record_path=detail_record_path, error_record_path=error_record_path)
        if usage_stats is not None:
            self._merge_usage_stats(session_id, usage_stats)
        self.store.append_detail_note(session_id, "运行终止", reason)
        self.store.sync_record_paths(session_id)
        self.store.set_status(session_id, "terminated", termination_message=reason)
        self._publish(session_id, {"type": "message", "role": "system", "label": "系统", "content": reason, "persist": True})
        self._publish(session_id, {"type": "done", "role": "system", "label": "系统", "content": "辩论已终止。", "persist": False})

    async def _run_session(
        self,
        session_id: str,
        topic: str,
        min_rounds: int,
        max_rounds: int,
        settings: dict,
        *,
        resumed: bool,
    ) -> None:
        """真正执行整场辩论的后台循环。"""

        self.store.set_status(session_id, "running")
        session = self.store.load_session(session_id) or {}
        runtime = self._build_runtime_from_session(session)
        context = prepare_runtime_context(settings)
        logger = DebateLogger(
            session_id=session_id,
            topic=topic,
            on_event=lambda payload: self._publish(session_id, payload),
            metrics_enabled=bool(settings.get("usage_tracking_enabled")),
        )

        if not resumed and str(runtime.get("phase") or "judge_initialize") == "judge_initialize" and not (session.get("messages") or []):
            logger.log_debate_start(topic, min_rounds, max_rounds, public_settings_summary(settings))
        elif resumed:
            self.store.append_detail_note(session_id, "继续辩论", "已恢复辩论，继续按照原顺序发言。")

        try:
            # usage_cursor 表示“上一阶段结束后的累计用量快照”。
            # 每完成一阶段，都用新快照减旧快照，得到本阶段独有的增量。
            usage_cursor = logger.build_usage_summary()

            while str(runtime.get("phase") or "judge_initialize") != "completed":
                current_phase = str(runtime.get("phase") or "judge_initialize")

                before_messages = self.store.load_session(session_id) or {}
                previous_message_ids = {
                    str(message.get("id") or "").strip()
                    for message in (before_messages.get("messages") or [])
                    if str(message.get("id") or "").strip()
                }

                updates = await run_runtime_phase(runtime, context, logger)
                usage_summary = logger.build_usage_summary()
                usage_delta = self._diff_usage_summaries(usage_cursor, usage_summary)

                runtime = merge_runtime_state(runtime, updates)

                # 某些阶段会新落一条模型消息；这里把它和该阶段 usage 绑定起来，
                # 后续撤回 / 恢复辩论时才能精确重算 token。
                message_id = self._resolve_new_message_id(session_id, previous_message_ids)
                self._append_usage_timeline_entry(runtime, phase=current_phase, usage_delta=usage_delta, message_id=message_id)
                if message_id and usage_delta is not None:
                    self._attach_message_usage(session_id, message_id, usage_delta, current_phase)

                runtime["phase"] = determine_next_phase(runtime, current_phase)
                self.store.set_runtime_state(session_id, runtime)
                self._publish_session_state(session_id)

                # 如果运行中已有挂起用户消息，则在当前辩手说完后把它正式插入历史。
                runtime = self._materialize_active_user_message(session_id, runtime)
                usage_cursor = usage_summary

            logger.log_usage_summary()
            result = build_runtime_result(runtime)
            self.store.set_runtime_state(session_id, runtime)
            self.store.set_result(session_id, result)
            self.store.set_record_paths(
                session_id,
                detail_record_path=str(logger.detail_log_file),
                error_record_path=str(logger.error_log_file) if logger.error_log_file else None,
            )
            self._merge_usage_stats(session_id, logger.build_usage_summary())
            self.store.set_status(session_id, "completed")
            self._publish(session_id, {"type": "done", "role": "system", "label": "系统", "content": "辩论已完成。", "persist": False})
        except asyncio.CancelledError:
            logger.log_usage_summary()
            command = self.task_commands.get(session_id, {})
            action = str(command.get("action") or "terminate")
            reason = str(command.get("reason") or ("用户手动暂停" if action == "pause" else "用户手动终止"))
            if action == "pause":
                self._finalize_paused(
                    session_id,
                    reason,
                    usage_stats=logger.build_usage_summary(),
                    detail_record_path=str(logger.detail_log_file),
                    error_record_path=str(logger.error_log_file) if logger.error_log_file else None,
                )
            else:
                self._finalize_terminated(
                    session_id,
                    reason,
                    usage_stats=logger.build_usage_summary(),
                    detail_record_path=str(logger.detail_log_file),
                    error_record_path=str(logger.error_log_file) if logger.error_log_file else None,
                )
            return
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            traceback_text = traceback.format_exc()
            logger.log_error(error_message, traceback_text)
            logger.log_usage_summary()
            self.store.set_record_paths(
                session_id,
                detail_record_path=str(logger.detail_log_file),
                error_record_path=str(logger.error_log_file) if logger.error_log_file else None,
            )
            self._merge_usage_stats(session_id, logger.build_usage_summary())
            self.store.set_status(session_id, "error", error_message, traceback_text)
            self._publish(session_id, {"type": "done", "role": "system", "label": "系统", "content": "辩论已中断。", "persist": False})
            return
        finally:
            async with self._task_lock:
                self.tasks.pop(session_id, None)
                self.task_commands.pop(session_id, None)
