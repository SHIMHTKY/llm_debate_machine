from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api.manager import DebateRunManager
from backend.api import app as app_module
from backend.api.detail_views import _DETAIL_TASKS
from backend.api.manager_parts import runtime as runtime_module
from backend.api.manager_parts.runtime import _redact_sensitive_text
from backend.api.manager_support_parts.usage import empty_usage_summary, rebuild_usage_tracking
from backend.api.manager_support_parts.session_view import find_preset
from backend.api.schemas import DebateStartRequest, MessageDetailViewRequest
from backend.config.settings import public_settings_summary, settings_for_frontend
from backend.config.settings_parts.constants import MASKED_SECRET
from backend.config.settings_parts import storage as settings_storage
from backend.config.settings_parts.defaults import default_settings
from backend.config.settings_parts.normalize import (
    MAX_DEEP_THINKING_TOKENS,
    MAX_MODEL_RETRIES,
    MAX_MODEL_TIMEOUT_SECONDS,
    MAX_MODEL_TOKENS,
    MAX_TOOL_ROUNDS,
    MAX_TOOL_TIMEOUT_SECONDS,
    MAX_RESPONSE_FLOW_BLOCKS,
    normalize_settings,
)
from backend.debate.pipeline.agent import find_tool, normalize_tool_args, run_bind_tools_mode, run_manual_flow
from backend.conversation.engine import build_conversation_runtime, build_turn_messages
from backend.storage.conversations import ConversationStore
from backend.debate.pipeline.common import message_text
from backend.debate.pipeline.phases_judge import _evaluation, _score, _winner
from backend.storage.sessions import SessionStore


class StubLogger:
    metrics_enabled = False

    def log_llm_reasoning(self, *_args, **_kwargs) -> None:
        return None

    def record_llm_usage(self, *_args, **_kwargs) -> None:
        return None

    def log_tool_call(self, *_args, **_kwargs) -> None:
        return None

    def log_manual_thinking(self, *_args, **_kwargs) -> None:
        return None


class BackendRegressionTests(unittest.TestCase):
    def tearDown(self) -> None:
        for task in list(_DETAIL_TASKS.values()):
            task.cancel()
        _DETAIL_TASKS.clear()

    def test_whitespace_topic_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DebateStartRequest(topic="   ", min_rounds=2, max_rounds=3)

    def test_settings_values_have_runtime_safety_caps(self) -> None:
        payload = deepcopy(default_settings())
        payload["model_suppliers"][0].update({"timeout": 999999, "max_retries": 999999})
        payload["tool_configs"][0].update({"timeout": 999999, "search_depth": "invalid"})
        payload["debater_presets"][0]["max_tokens"] = 999999999
        payload["debater_presets"][0]["tool_selection"]["max_tool_rounds"] = 999999
        payload["debater_presets"][0]["response_flow"] = {
            "mode": "manual",
            "blocks": [
                {"id": f"think_{index}", "type": "deep_thinking", "max_tokens": 999999}
                for index in range(20)
            ],
        }

        normalized = normalize_settings(payload)

        self.assertEqual(normalized["model_suppliers"][0]["timeout"], MAX_MODEL_TIMEOUT_SECONDS)
        self.assertEqual(normalized["model_suppliers"][0]["max_retries"], MAX_MODEL_RETRIES)
        self.assertEqual(normalized["tool_configs"][0]["timeout"], MAX_TOOL_TIMEOUT_SECONDS)
        self.assertEqual(normalized["tool_configs"][0]["search_depth"], "advanced")
        self.assertEqual(normalized["debater_presets"][0]["max_tokens"], MAX_MODEL_TOKENS)
        self.assertEqual(normalized["debater_presets"][0]["tool_selection"]["max_tool_rounds"], MAX_TOOL_ROUNDS)
        response_flow = normalized["debater_presets"][0]["response_flow"]
        self.assertEqual(response_flow["mode"], "manual")
        self.assertEqual(len(response_flow["blocks"]), MAX_RESPONSE_FLOW_BLOCKS)
        self.assertEqual(response_flow["blocks"][0]["type"], "start")
        self.assertEqual(response_flow["blocks"][-1]["type"], "final_response")
        self.assertEqual(response_flow["blocks"][1]["max_tokens"], MAX_DEEP_THINKING_TOKENS)

    def test_legacy_presets_default_to_autonomous_response_flow(self) -> None:
        payload = deepcopy(default_settings())
        payload["debater_presets"][0].pop("response_flow", None)

        normalized = normalize_settings(payload)

        flow = normalized["debater_presets"][0]["response_flow"]
        self.assertEqual(flow["mode"], "autonomous")
        self.assertEqual([block["type"] for block in flow["blocks"]], ["start", "final_response"])

    def test_corrupt_settings_are_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            settings_file = data_dir / "settings.json"
            settings_file.write_text("{broken", encoding="utf-8")
            with patch.object(settings_storage, "DATA_DIR", data_dir), patch.object(
                settings_storage, "SETTINGS_FILE", settings_file
            ):
                recovered = settings_storage._load_raw_settings()

            self.assertIsInstance(recovered, dict)
            self.assertTrue(settings_file.exists())
            self.assertIsInstance(json.loads(settings_file.read_text(encoding="utf-8")), dict)
            self.assertEqual(len(list(data_dir.glob("settings.json.corrupt-*"))), 1)

    def test_session_store_rejects_unsafe_ids_and_round_trips_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(base_dir=Path(temp_dir))
            session = store.create_session("topic", 2, 3, {})
            store.set_status(session["id"], "paused")
            self.assertEqual(store.load_session(session["id"])["status"], "paused")
            self.assertEqual(list(store.session_dir.glob("*.tmp")), [])
            with self.assertRaises(ValueError):
                store.load_session("../outside")

    def test_conversation_turn_carries_prompt_and_previous_output(self) -> None:
        first = build_turn_messages("讨论 AI", "", "")
        next_turn = build_turn_messages("讨论 AI", "上一位的回答", "模型 A")
        self.assertIn("讨论 AI", first[-1]["content"])
        self.assertIn("讨论 AI", next_turn[-1]["content"])
        self.assertIn("上一位的回答", next_turn[-1]["content"])
        self.assertIn("模型 A", next_turn[-1]["content"])

    def test_conversation_runtime_starts_at_first_participant(self) -> None:
        runtime = build_conversation_runtime("topic", [{"name": "A"}, {"name": "B"}])
        self.assertEqual(runtime["phase"], "running")
        self.assertEqual(runtime["participant_index"], 0)
        self.assertEqual(runtime["participant_count"], 2)

    def test_conversation_store_uses_isolated_directory_and_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ConversationStore(base_dir=Path(temp_dir))
            session = store.create_conversation(
                "topic",
                [{"name": "A"}, {"name": "B"}],
                {"participants": [{"name": "A"}, {"name": "B"}]},
                {"participants": []},
            )
            self.assertEqual(session["kind"], "conversation")
            self.assertTrue(session["id"].startswith("conversation_"))
            self.assertTrue(store.session_dir.name == "conversations")
            self.assertEqual(store.list_sessions()[0]["kind"], "conversation")

    def test_interrupted_running_session_becomes_paused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(base_dir=Path(temp_dir))
            session = store.create_session("topic", 2, 3, {})
            store.set_status(session["id"], "running")
            manager = DebateRunManager(store)

            self.assertEqual(manager.recover_interrupted_sessions(), 1)
            self.assertEqual(store.load_session(session["id"])["status"], "paused")
            self.assertEqual(manager.recover_interrupted_sessions(), 0)

    def test_slow_subscriber_queue_keeps_latest_event(self) -> None:
        manager = DebateRunManager()
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1)
        manager._enqueue_event(queue, {"id": "old"})
        manager._enqueue_event(queue, {"id": "new"})
        self.assertEqual(queue.get_nowait()["id"], "new")

    def test_unknown_tool_does_not_fall_back_to_first_tool(self) -> None:
        @tool
        def web_search(query: str) -> str:
            """Search test data."""

            return query

        self.assertIsNone(find_tool([web_search], "delete_everything"))
        self.assertEqual(normalize_tool_args({"query": "x", "danger": True}, "fallback"), {"query": "x"})

    def test_judge_payload_is_normalized(self) -> None:
        self.assertEqual(_winner("正方获胜"), "正方")
        self.assertEqual(_winner({"bad": "shape"}), "平局")
        self.assertEqual(_score("999"), 100)
        self.assertEqual(_score("bad"), 50)
        self.assertEqual(_evaluation(["bad"])["pro_strengths"], [])
        self.assertEqual(_evaluation({"pro_strengths": "clear"})["pro_strengths"], ["clear"])

    def test_error_text_redacts_configured_secrets(self) -> None:
        secret = "sk-test-private-value"
        redacted = _redact_sensitive_text(
            f"Authorization: Bearer {secret}\nrequest api_key={secret}",
            {"judge": {"api_key": secret}},
        )
        self.assertNotIn(secret, redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_public_summary_recursively_masks_extra_body_secrets(self) -> None:
        settings = {
            "judge": {
                "model": "judge-model",
                "extra_body": {
                    "enable_thinking": True,
                    "Authorization": "Bearer private-token",
                    "nested": {"api_key": "nested-private-key"},
                },
            },
            "translator": {},
            "summarizer": {},
            "pro": {},
            "con": {},
        }

        summary = public_settings_summary(settings)
        serialized = json.dumps(summary, ensure_ascii=False)

        self.assertNotIn("private-token", serialized)
        self.assertNotIn("nested-private-key", serialized)
        self.assertEqual(summary["judge"]["extra_body"]["Authorization"], MASKED_SECRET)
        self.assertEqual(summary["judge"]["extra_body"]["nested"]["api_key"], MASKED_SECRET)
        self.assertTrue(summary["judge"]["extra_body"]["enable_thinking"])

    def test_masked_extra_body_secret_survives_settings_round_trip(self) -> None:
        raw = deepcopy(default_settings())
        raw["debater_presets"][0]["extra_body"] = {
            "enable_thinking": True,
            "Authorization": "Bearer persistent-secret",
        }

        frontend_settings = settings_for_frontend(raw)
        normalized = normalize_settings(frontend_settings, base_settings=raw, strict_extra_body=True)

        self.assertEqual(frontend_settings["debater_presets"][0]["extra_body"]["Authorization"], MASKED_SECRET)
        self.assertEqual(
            normalized["debater_presets"][0]["extra_body"]["Authorization"],
            "Bearer persistent-secret",
        )

    def test_runtime_settings_snapshot_is_private_and_immutable_for_resume(self) -> None:
        secret = "sk-original-session-secret"
        runtime_settings = {
            "judge": {"model": "original-judge", "api_key": secret},
            "pro": {"model": "original-pro", "api_key": secret},
            "con": {"model": "original-con", "api_key": secret},
            "tool_configs": [],
            "debater_presets": [],
            "context_rounds": 4,
            "usage_tracking_enabled": True,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(base_dir=Path(temp_dir))
            session = store.create_session(
                "topic",
                2,
                3,
                {"judge": {"extra_body": {"api_key": secret}}},
                runtime_settings=runtime_settings,
            )
            loaded = store.load_session(session["id"])
            manager = DebateRunManager(store)

            self.assertNotIn(secret, json.dumps(loaded, ensure_ascii=False))
            self.assertEqual(store.load_runtime_settings(session["id"]), runtime_settings)
            self.assertEqual(manager._build_resume_settings(loaded), runtime_settings)

            runtime_path = store._runtime_config_path(session["id"])
            self.assertTrue(runtime_path.exists())
            self.assertTrue(store.delete_session(session["id"]))
            self.assertFalse(runtime_path.exists())

    def test_resume_preset_prefers_stable_id_over_duplicate_name(self) -> None:
        payload = deepcopy(default_settings())
        first = deepcopy(payload["debater_presets"][0])
        second = deepcopy(payload["debater_presets"][min(1, len(payload["debater_presets"]) - 1)])
        first.update({"id": "preset_first", "name": "duplicate", "model": "first-model"})
        second.update({"id": "preset_second", "name": "duplicate", "model": "second-model"})
        payload["debater_presets"] = [first, second]
        normalized = normalize_settings(payload)

        resolved = find_preset(normalized, preset_id="preset_second", preset_name="duplicate")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["preset_id"], "preset_second")
        self.assertEqual(resolved["model"], "second-model")

    def test_message_text_supports_langchain_messages(self) -> None:
        flattened = message_text([ToolMessage(content="result", tool_call_id="call_1")])
        self.assertIn("tool: result", flattened)

    def test_rebuild_usage_keeps_uncommitted_pause_cost(self) -> None:
        committed = self._usage_summary(60)
        removed = self._usage_summary(40)
        current = self._usage_summary(140, call_count=3)
        session = {
            "usage_stats": current,
            "runtime_state": {
                "phase": "con_argument",
                "debate_history": [],
                "usage_timeline": [
                    {"phase": "pro_argument", "message_id": "keep", "usage_delta": committed},
                    {"phase": "con_argument", "message_id": "remove", "usage_delta": removed},
                ],
            },
        }
        rebuilt_runtime = {"phase": "con_argument"}

        rebuilt = rebuild_usage_tracking(session, [{"id": "keep"}], rebuilt_runtime)

        self.assertEqual(rebuilt["totals"]["total_tokens"], 100)
        self.assertEqual(rebuilt["totals"]["call_count"], 2)
        self.assertEqual(rebuilt["roles"]["pro"]["total_tokens"], 100)
        self.assertEqual([entry["message_id"] for entry in rebuilt_runtime["usage_timeline"]], ["keep"])

    def test_rebuild_usage_does_not_duplicate_committed_cost(self) -> None:
        committed = self._usage_summary(60)
        removed = self._usage_summary(40)
        session = {
            "usage_stats": self._usage_summary(100, call_count=2),
            "runtime_state": {
                "phase": "con_argument",
                "debate_history": [],
                "usage_timeline": [
                    {"phase": "pro_argument", "message_id": "keep", "usage_delta": committed},
                    {"phase": "con_argument", "message_id": "remove", "usage_delta": removed},
                ],
            },
        }

        rebuilt = rebuild_usage_tracking(session, [{"id": "keep"}], {"phase": "con_argument"})

        self.assertEqual(rebuilt["totals"]["total_tokens"], 60)
        self.assertEqual(rebuilt["totals"]["call_count"], 1)

    @staticmethod
    def _usage_summary(total_tokens: int, *, call_count: int = 1) -> dict:
        summary = empty_usage_summary(enabled=True)
        summary["roles"]["pro"].update(
            {
                "input_tokens": total_tokens,
                "total_tokens": total_tokens,
                "call_count": call_count,
                "stages": {
                    "argument": {
                        "input_tokens": total_tokens,
                        "output_tokens": 0,
                        "total_tokens": total_tokens,
                        "call_count": call_count,
                        "estimated": False,
                    }
                },
            }
        )
        summary["totals"].update({"input_tokens": total_tokens, "total_tokens": total_tokens, "call_count": call_count})
        return summary


class DetailTaskCancellationTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        for task in list(_DETAIL_TASKS.values()):
            task.cancel()
        _DETAIL_TASKS.clear()

    @staticmethod
    def _endpoint(application, path: str):
        return next(route.endpoint for route in application.routes if getattr(route, "path", "") == path)

    async def test_detail_task_cancel_reaches_model_coroutine_and_skips_write(self) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()
        wrote_cache = False

        async def fake_build(*_args, **_kwargs):
            nonlocal wrote_cache
            started.set()
            try:
                await asyncio.Event().wait()
                wrote_cache = True
            except asyncio.CancelledError:
                cancelled.set()
                raise

        application = app_module.create_app()
        create_endpoint = self._endpoint(application, "/api/debates/{session_id}/message-detail-view")
        cancel_endpoint = self._endpoint(application, "/api/detail-tasks/{task_id}/cancel")
        payload = MessageDetailViewRequest(
            message_id="message-1",
            detail_index=0,
            content_kind="reasoning",
            entry_index=0,
            view="summary",
            task_id="cancel-test",
        )

        with patch.object(app_module, "build_message_detail_view", side_effect=fake_build):
            request_task = asyncio.create_task(create_endpoint("session-1", payload))
            await asyncio.wait_for(started.wait(), timeout=1)
            cancel_result = await cancel_endpoint("cancel-test")
            response = await asyncio.wait_for(request_task, timeout=1)

        self.assertTrue(cancel_result["cancelled"])
        self.assertTrue(response["cancelled"])
        self.assertTrue(cancelled.is_set())
        self.assertFalse(wrote_cache)
        self.assertEqual(_DETAIL_TASKS, {})

    async def test_detail_task_rejects_concurrency_and_cleans_up(self) -> None:
        release = asyncio.Event()
        started = asyncio.Event()

        async def fake_build(*_args, **_kwargs):
            started.set()
            await release.wait()
            return {"view": {}, "cached": False}

        application = app_module.create_app()
        create_endpoint = self._endpoint(application, "/api/debates/{session_id}/message-detail-view")
        first_payload = MessageDetailViewRequest(
            message_id="message-1",
            detail_index=0,
            content_kind="tool_result",
            view="summary",
            task_id="first-task",
        )
        second_payload = first_payload.model_copy(update={"task_id": "second-task"})

        with patch.object(app_module, "build_message_detail_view", side_effect=fake_build):
            first_request = asyncio.create_task(create_endpoint("session-1", first_payload))
            await asyncio.wait_for(started.wait(), timeout=1)
            with self.assertRaises(HTTPException) as raised:
                await create_endpoint("session-1", second_payload)
            self.assertEqual(raised.exception.status_code, 409)
            release.set()
            await asyncio.wait_for(first_request, timeout=1)

        self.assertEqual(_DETAIL_TASKS, {})

    async def test_detail_task_exception_releases_registry(self) -> None:
        async def fake_build(*_args, **_kwargs):
            raise RuntimeError("model failed")

        application = app_module.create_app()
        create_endpoint = self._endpoint(application, "/api/debates/{session_id}/message-detail-view")
        payload = MessageDetailViewRequest(
            message_id="message-1",
            detail_index=0,
            content_kind="tool_result",
            view="summary",
            task_id="failed-task",
        )

        with patch.object(app_module, "build_message_detail_view", side_effect=fake_build):
            with self.assertRaisesRegex(RuntimeError, "model failed"):
                await create_endpoint("session-1", payload)

        self.assertEqual(_DETAIL_TASKS, {})

    async def test_client_disconnect_does_not_cancel_detail_model_task(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        model_cancelled = False

        async def fake_build(*_args, **_kwargs):
            nonlocal model_cancelled
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                model_cancelled = True
                raise
            return {"view": {}, "cached": False}

        application = app_module.create_app()
        create_endpoint = self._endpoint(application, "/api/debates/{session_id}/message-detail-view")
        payload = MessageDetailViewRequest(
            message_id="message-1",
            detail_index=0,
            content_kind="tool_result",
            view="summary",
            task_id="detached-task",
        )

        with patch.object(app_module, "build_message_detail_view", side_effect=fake_build):
            request_task = asyncio.create_task(create_endpoint("session-1", payload))
            await asyncio.wait_for(started.wait(), timeout=1)
            request_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await request_task
            self.assertIn("detached-task", _DETAIL_TASKS)
            self.assertFalse(model_cancelled)
            release.set()
            for _ in range(10):
                if not _DETAIL_TASKS:
                    break
                await asyncio.sleep(0)

        self.assertFalse(model_cancelled)
        self.assertEqual(_DETAIL_TASKS, {})


class BindToolsProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_phase_buffers_message_until_state_commit(self) -> None:
        observed_messages: list[list[dict]] = []

        class FakeLogger:
            def __init__(self, **kwargs) -> None:
                self.on_event = kwargs.get("on_event")
                self.detail_log_file = Path("detail.md")
                self.error_log_file = None

            def log_debate_start(self, *_args, **_kwargs) -> None:
                return None

            def begin_detail_transaction(self) -> None:
                return None

            def commit_detail_transaction(self) -> None:
                return None

            def discard_detail_transaction(self) -> None:
                return None

            def build_usage_summary(self):
                return {"enabled": False}

            def log_usage_summary(self) -> None:
                return None

            def log_error(self, *_args, **_kwargs) -> None:
                raise AssertionError("The fake phase should not fail.")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(base_dir=Path(temp_dir))
            session = store.create_session("topic", 2, 3, {})
            store.set_runtime_state(session["id"], {"phase": "judge_initialize"})
            manager = DebateRunManager(store)

            async def fake_phase(_runtime, _context, logger):
                logger.on_event(
                    {
                        "type": "message",
                        "role": "pro",
                        "label": "正方",
                        "content": "atomic speech",
                        "persist": True,
                    }
                )
                observed_messages.append(list(store.load_session(session["id"])["messages"]))
                return {"phase_marker": "committed"}

            with patch.object(runtime_module, "DebateLogger", FakeLogger), patch.object(
                runtime_module, "prepare_runtime_context", return_value={}
            ), patch.object(runtime_module, "run_runtime_phase", side_effect=fake_phase), patch.object(
                runtime_module, "determine_next_phase", return_value="completed"
            ), patch.object(runtime_module, "build_runtime_result", return_value={"winner": "正方"}), patch.object(
                store, "commit_runtime_phase", wraps=store.commit_runtime_phase
            ) as commit_phase:
                await manager._run_session(
                    session["id"],
                    "topic",
                    2,
                    3,
                    {"usage_tracking_enabled": False},
                    resumed=False,
                )

            completed = store.load_session(session["id"])
            self.assertEqual(observed_messages, [[]])
            self.assertEqual(commit_phase.call_count, 1)
            self.assertEqual([message["content"] for message in completed["messages"]], ["atomic speech"])
            self.assertEqual(completed["runtime_state"]["phase"], "completed")
            self.assertEqual(completed["runtime_state"]["phase_marker"], "committed")

    async def test_context_build_failure_sets_error_and_redacts_secret(self) -> None:
        secret = "sk-context-private"

        class FakeLogger:
            def __init__(self, **_kwargs) -> None:
                self.detail_log_file = Path("detail.md")
                self.error_log_file = None

            def build_usage_summary(self):
                return {"enabled": False}

            def log_error(self, _message, _traceback) -> None:
                self.error_log_file = Path("error.md")

            def log_usage_summary(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(base_dir=Path(temp_dir))
            session = store.create_session("topic", 2, 3, {})
            manager = DebateRunManager(store)
            with patch.object(runtime_module, "DebateLogger", FakeLogger), patch.object(
                runtime_module,
                "prepare_runtime_context",
                side_effect=RuntimeError(f"bad model config {secret}"),
            ):
                await manager._run_session(
                    session["id"],
                    "topic",
                    2,
                    3,
                    {"usage_tracking_enabled": False, "judge": {"api_key": secret}},
                    resumed=False,
                )

            failed = store.load_session(session["id"])
            self.assertEqual(failed["status"], "error")
            self.assertNotIn(secret, failed["error_message"])
            self.assertNotIn(secret, failed["error_traceback"])

    async def test_bind_tools_sends_matching_tool_message(self) -> None:
        @tool
        def web_search(query: str) -> str:
            """Search test data."""

            return f"result:{query}"

        class BoundModel:
            def __init__(self) -> None:
                self.calls: list[list] = []

            async def ainvoke(self, messages):
                self.calls.append(list(messages))
                if len(self.calls) == 1:
                    return AIMessage(
                        content="",
                        tool_calls=[{"name": "web_search", "args": {"query": "fact"}, "id": "call_1", "type": "tool_call"}],
                    )
                return AIMessage(content="final answer")

        class Model:
            def __init__(self) -> None:
                self.bound = BoundModel()

            def bind_tools(self, _tools):
                return self.bound

        model = Model()
        result = await run_bind_tools_mode(
            model,
            [web_search],
            "system",
            "user",
            StubLogger(),
            "pro",
            "正方",
            "stage",
            2,
        )

        self.assertEqual(result, "final answer")
        tool_messages = [item for item in model.bound.calls[1] if isinstance(item, ToolMessage)]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0].tool_call_id, "call_1")

    async def test_manual_flow_keeps_internal_steps_private_and_forces_tool(self) -> None:
        @tool
        def web_search(query: str) -> str:
            """Search test data."""

            return f"search-result:{query}"

        class Model:
            def __init__(self) -> None:
                self.calls: list[list[dict]] = []

            def bind(self, **_kwargs):
                return self

            async def ainvoke(self, messages):
                self.calls.append(list(messages))
                if len(self.calls) == 1:
                    return AIMessage(content="private analysis")
                if len(self.calls) == 2:
                    return AIMessage(content='{"query":"verified fact"}')
                return AIMessage(content="public final speech")

        class Logger(StubLogger):
            def __init__(self) -> None:
                self.tool_calls: list[tuple] = []
                self.thinking: list[str] = []

            def log_tool_call(self, *args, **kwargs) -> None:
                self.tool_calls.append((args, kwargs))

            def log_manual_thinking(self, _role, _step, content, _max_tokens) -> None:
                self.thinking.append(content)

        model = Model()
        logger = Logger()
        result = await run_manual_flow(
            model,
            {"tool_search": web_search},
            {
                "mode": "manual",
                "blocks": [
                    {"id": "flow_start", "type": "start"},
                    {"id": "think", "type": "deep_thinking", "max_tokens": 512},
                    {"id": "search", "type": "tool_call", "tool_id": "tool_search"},
                    {"id": "flow_final", "type": "final_response"},
                ],
            },
            "system",
            "debate context",
            logger,
            "pro",
            "正方",
            "round 1",
        )

        self.assertEqual(result, "public final speech")
        self.assertEqual(logger.thinking, ["private analysis"])
        self.assertEqual(len(logger.tool_calls), 1)
        final_prompt = model.calls[-1][-1]["content"]
        self.assertIn("private analysis", final_prompt)
        self.assertIn("search-result:verified fact", final_prompt)


if __name__ == "__main__":
    unittest.main()
