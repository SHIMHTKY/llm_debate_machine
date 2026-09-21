"""模型自由对话运行生命周期与 SSE 管理。"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import re
import traceback
from typing import Any

from ..config.settings import load_settings
from ..config.settings_parts.helpers import _is_sensitive_key
from ..conversation.engine import build_conversation_runtime, run_conversation_turn
from ..storage.conversations import ConversationStore
from .manager_parts.base import BaseDebateRunManager, DebateCapacityError, DebateStateError
from .manager_parts.events import EventManagerMixin
from .manager_support_parts.session_view import find_preset


def _redact_text(value: str, settings: dict) -> str:
    secrets: set[str] = set()

    def visit(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for child_key, child_value in item.items():
                visit(child_value, str(child_key).lower())
        elif isinstance(item, list):
            for child_value in item:
                visit(child_value, key)
        elif _is_sensitive_key(key) and len(str(item or "")) >= 4:
            secrets.add(str(item))

    visit(settings)
    output = str(value or "")
    for secret in sorted(secrets, key=len, reverse=True):
        output = output.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+", r"\1[REDACTED]", output)


class ConversationRunManager(EventManagerMixin, BaseDebateRunManager):
    MAX_CONCURRENT_CONVERSATIONS = 3

    def __init__(self, store: ConversationStore | None = None) -> None:
        super().__init__(store or ConversationStore())

    def recover_interrupted_sessions(self) -> int:
        recovered = 0
        for archived in (False, True):
            for summary in self.store.list_sessions(archived=archived):
                session_id = str(summary.get("id") or "")
                session = self.store.load_session(session_id)
                if session is None or session.get("status") not in {"queued", "running"}:
                    continue
                self.store.set_status(session_id, "error", "服务中断，对话未完成。", "服务进程在模型接力期间退出。")
                recovered += 1
        return recovered

    async def start_conversation(self, prompt: str, participant_preset_ids: list[str]) -> dict:
        async with self._task_lock:
            self._prune_finished_tasks()
            if self.running_count() >= self.MAX_CONCURRENT_CONVERSATIONS:
                raise DebateCapacityError("已到当前进程上限。")
            settings = load_settings()
            participants: list[dict] = []
            runtime_models: list[dict] = []
            for index, preset_id in enumerate(participant_preset_ids):
                model_settings = find_preset(settings, preset_id=preset_id, preset_name="")
                if not model_settings:
                    raise DebateStateError(f"未找到第 {index + 1} 个模型配置。")
                label = str(model_settings.get("preset_name") or model_settings.get("model") or f"模型 {index + 1}")
                participants.append({
                    "index": index,
                    "preset_id": str(model_settings.get("preset_id") or preset_id),
                    "name": label,
                    "model": str(model_settings.get("model") or model_settings.get("azure_deployment") or ""),
                    "provider": str(model_settings.get("provider") or ""),
                })
                runtime_models.append(deepcopy(model_settings))
            config_summary = {
                "kind": "conversation",
                "participants": deepcopy(participants),
                "usage_tracking_enabled": bool(settings.get("usage_tracking_enabled")),
            }
            runtime_settings = {
                "participants": runtime_models,
                "usage_tracking_enabled": bool(settings.get("usage_tracking_enabled")),
            }
            session = self.store.create_conversation(prompt, participants, config_summary, runtime_settings)
            runtime = build_conversation_runtime(prompt, participants)
            self.store.set_runtime_state(session["id"], runtime)
            task = asyncio.create_task(self._run_session(session["id"], prompt, runtime_models), name=f"conversation:{session['id']}")
            self.tasks[session["id"]] = task
        return self.store.load_session(session["id"]) or session

    async def stop_conversation(self, session_id: str, reason: str = "用户手动终止") -> dict | None:
        session = self.store.load_session(session_id)
        if session is None:
            return None
        async with self._task_lock:
            self._prune_finished_tasks()
            task = self.tasks.get(session_id)
            if task is None or task.done():
                return self.store.load_session(session_id)
            self.task_commands[session_id] = {"action": "terminate", "reason": reason}
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return self.store.load_session(session_id)

    async def _run_session(self, session_id: str, prompt: str, runtime_models: list[dict]) -> None:
        settings = {"participants": runtime_models}
        self.store.set_status(session_id, "running")
        runtime = (self.store.load_session(session_id) or {}).get("runtime_state") or build_conversation_runtime(prompt, [])
        usage_enabled = bool((self.store.load_runtime_settings(session_id) or {}).get("usage_tracking_enabled"))
        usage_stats = self._empty_usage(runtime.get("participants") or [], enabled=usage_enabled)
        previous_output = str(runtime.get("last_output") or "")
        try:
            while int(runtime.get("participant_index") or 0) < len(runtime_models):
                index = int(runtime.get("participant_index") or 0)
                participant = runtime.get("participants", [])[index]
                label = str(participant.get("name") or f"模型 {index + 1}")
                self._publish(session_id, {"type": "status", "role": "participant", "speaker_index": index, "label": label, "content": f"{label} 正在回复...", "persist": False})
                text, usage, estimated = await run_conversation_turn(runtime_models[index], prompt, previous_output, str(runtime.get("participants", [])[index - 1].get("name") if index else "上一位模型"))
                message_id = f"message_{session_id}_{index}"
                message = {"id": message_id, "type": "message", "role": "participant", "speaker_index": index, "speaker_id": participant.get("preset_id"), "label": label, "content": text, "timestamp": self.store._now(), "persist": True}
                runtime["last_output"] = text
                runtime["participant_index"] = index + 1
                runtime["usage_timeline"].append({"participant_index": index, "message_id": message_id, "usage": usage, "estimated": estimated})
                if usage_enabled:
                    self._add_usage(usage_stats, index, usage, estimated)
                runtime["phase"] = "completed" if runtime["participant_index"] >= len(runtime_models) else "running"
                self._begin_phase_event_buffer(session_id)
                self._publish(session_id, message)
                events = self._take_phase_event_buffer(session_id)
                self.store.commit_runtime_phase(session_id, runtime, events)
                self._broadcast_committed_phase_events(session_id, events)
                self._publish_session_state(session_id)
                previous_output = text
            self.store.set_usage_stats(session_id, usage_stats)
            self.store.set_status(session_id, "completed")
            self._publish(session_id, {"type": "done", "role": "system", "label": "系统", "content": "模型自由对话已完成。", "persist": False})
        except asyncio.CancelledError:
            self._discard_phase_event_buffer(session_id)
            command = self.task_commands.get(session_id, {})
            reason = str(command.get("reason") or "用户手动终止")
            self.store.set_usage_stats(session_id, usage_stats)
            self.store.set_status(session_id, "terminated", termination_message=reason)
            self._publish(session_id, {"type": "done", "role": "system", "label": "系统", "content": "模型自由对话已终止。", "persist": False})
        except Exception as exc:
            self._discard_phase_event_buffer(session_id)
            error_message = _redact_text(f"{type(exc).__name__}: {exc}", settings)
            traceback_text = _redact_text(traceback.format_exc(), settings)
            self.store.set_usage_stats(session_id, usage_stats)
            self.store.set_status(session_id, "error", error_message, traceback_text)
            self._publish(session_id, {"type": "error", "role": "system", "label": "错误", "content": error_message, "persist": True})
            self._publish(session_id, {"type": "done", "role": "system", "label": "系统", "content": "模型自由对话已中断。", "persist": False})
        finally:
            self._discard_phase_event_buffer(session_id)
            async with self._task_lock:
                if self.tasks.get(session_id) is asyncio.current_task():
                    self.tasks.pop(session_id, None)
                    self.task_commands.pop(session_id, None)

    @staticmethod
    def _empty_usage(participants: list[dict], *, enabled: bool) -> dict:
        return {"enabled": enabled, "participants": [{"label": item.get("name"), "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "call_count": 0, "estimated": False} for item in participants], "totals": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "call_count": 0}}

    @staticmethod
    def _add_usage(summary: dict, index: int, usage: dict, estimated: bool) -> None:
        row = summary["participants"][index]
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            row[key] += int(usage.get(key) or 0)
            summary["totals"][key] += int(usage.get(key) or 0)
        row["call_count"] += 1
        summary["totals"]["call_count"] += 1
        row["estimated"] = bool(row["estimated"] or estimated)
