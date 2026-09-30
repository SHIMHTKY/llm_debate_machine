"""Local, isolated preview server for the native frontend.

This server deliberately does not import the application backend. It serves the
real ``frontend`` directory and implements the browser-facing API with in-memory
fixtures only, so it never reads project configuration, data, or logs and never
invokes a model.
"""

from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
DETAIL_DELAY_SECONDS = 0.35


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def deep_copy(value: Any) -> Any:
    return copy.deepcopy(value)


def make_settings() -> dict[str, Any]:
    supplier_id = "supplier-preview"
    tool_id = "tool-tavily-preview"
    shared_model = {
        "supplier_id": supplier_id,
        "model": "preview-utility-model",
        "azure_deployment": "",
        "max_tokens": 4096,
        "extra_body": {"preview_fixture": True},
    }
    return {
        "judge": {**shared_model, "model": "preview-judge"},
        "translator": {**shared_model, "model": "preview-translator"},
        "summarizer": {**shared_model, "model": "preview-summarizer"},
        "model_suppliers": [
            {
                "id": supplier_id,
                "name": "本地预览供应商（虚构）",
                "provider": "chatopenai",
                "api_key": "preview-only-not-a-secret",
                "base_url": "http://127.0.0.1.invalid/v1",
                "api_version": "",
                "timeout": 30,
                "max_retries": 1,
            }
        ],
        "tool_configs": [
            {
                "id": tool_id,
                "name": "Tavily Search（预览）",
                "template_id": "tavily_search",
                "type": "tavily_search",
                "enabled": True,
                "api_key": "preview-tavily-not-a-secret",
                "timeout": 10,
                "max_results": 5,
                "search_depth": "advanced",
                "output_truncate_chars": 2500,
            }
        ],
        "pro_preset_id": "preset-pro-preview",
        "con_preset_id": "preset-con-preview",
        "context_rounds": 3,
        "usage_tracking_enabled": True,
        "debater_presets": [
            {
                "id": "preset-pro-preview",
                "name": "证据驱动正方",
                "supplier_id": supplier_id,
                "model": "preview-pro-model",
                "azure_deployment": "",
                "max_tokens": 8000,
                "extra_body": {"temperature": 0.4},
                "tool_selection": {
                    "enabled_tool_ids": [tool_id],
                    "mode": "bind_tools",
                    "max_tool_rounds": 2,
                    "fallback_enabled": True,
                },
                "response_flow": {"mode": "autonomous", "blocks": []},
            },
            {
                "id": "preset-con-preview",
                "name": "审慎分析反方",
                "supplier_id": supplier_id,
                "model": "preview-con-model",
                "azure_deployment": "",
                "max_tokens": 8000,
                "extra_body": {"temperature": 0.2},
                "tool_selection": {
                    "enabled_tool_ids": [tool_id],
                    "mode": "bind_tools",
                    "max_tool_rounds": 2,
                    "fallback_enabled": False,
                },
                "response_flow": {
                    "mode": "manual",
                    "blocks": [
                        {"id": "flow-think-preview", "type": "deep_thinking", "max_tokens": 2048},
                        {"id": "flow-tool-preview", "type": "tool_call", "tool_id": tool_id},
                    ],
                },
            },
        ],
        "preset_limit": 24,
        "supplier_limit": 24,
        "tool_limit": 12,
    }


def message_details(side: str) -> list[dict[str, Any]]:
    return [
        {
            "kind": "reasoning",
            "title": "模型思考",
            "entries": [
                {
                    "source": "reasoning_content",
                    "content": (
                        f"先明确{side}的核心主张，再区分短期效率与长期制度成本。"
                        "为了测试长文本滚动，这里补充一段结构化思考：需要核对定义、证据质量、"
                        "反例覆盖与结论外推边界，避免只凭单一指标下结论。"
                    ),
                    "views": {},
                },
                {"source": "usage_metadata.reasoning_tokens", "content": "512"},
            ],
        },
        {
            "kind": "tool_call",
            "title": "工具调用 · Tavily Search",
            "tool_name": "tavily_search",
            "args": {
                "query": "生成式 AI 中小企业生产率 实证研究 2025",
                "search_depth": "advanced",
                "max_results": 5,
            },
        },
        {
            "kind": "tool_result",
            "title": "工具返回 · Tavily Search",
            "tool_name": "tavily_search",
            "result": "\n".join(
                [
                    "1. Preview Research — controlled deployment improved drafting throughput.",
                    "2. Preview Survey — gains varied by workflow maturity and staff training.",
                    "3. Preview Risk Note — verification cost rose for high-stakes outputs.",
                    "4. 本地 fixture：以上均为虚构内容，不代表真实研究结论。",
                    "5. Long-line check: " + "evidence-boundary " * 18,
                ]
            ),
            "views": {},
        },
        {
            "kind": "output",
            "title": "正式输出 · 第 1 轮",
            "content": f"{side}正式陈词：效率收益必须与验证成本、组织能力和风险等级一起衡量。",
        },
    ]


def completed_session() -> dict[str, Any]:
    created = "2026-09-27T08:15:00Z"
    messages = [
        {
            "id": "completed-pro-1",
            "role": "pro",
            "label": "正方",
            "round": 1,
            "timestamp": "2026-09-27T08:15:12Z",
            "content": "**本轮发言正文：**\n采用生成式 AI 能先从重复性文书和检索任务释放时间，并形成可复用流程。",
            "details": message_details("正方"),
        },
        {
            "id": "completed-con-1",
            "role": "con",
            "label": "反方",
            "round": 1,
            "timestamp": "2026-09-27T08:16:03Z",
            "content": "**本轮发言正文：**\n若缺少数据治理和复核机制，表面效率可能被错误传播与返工抵消。",
            "details": message_details("反方"),
        },
        {
            "id": "completed-user-1",
            "role": "user",
            "label": "用户发言",
            "target_role": "pro",
            "locked": True,
            "timestamp": "2026-09-27T08:16:40Z",
            "content": "请双方都说明结论的适用边界，并给出一个失败案例。",
        },
        {
            "id": "completed-pro-2",
            "role": "pro",
            "label": "正方",
            "round": 2,
            "timestamp": "2026-09-27T08:17:21Z",
            "content": "适用边界是低风险、可复核、输入质量稳定的任务；失败案例是未经审核直接发布。",
            "details": message_details("正方第二轮"),
        },
        {
            "id": "completed-judge",
            "role": "judge",
            "label": "裁判",
            "timestamp": "2026-09-27T08:19:00Z",
            "content": "双方都识别了条件约束；正方在落地路径上略具体，反方在风险边界上更完整。",
        },
    ]
    return {
        "id": "completed-detail",
        "topic": "这是一个用于验证极长标题省略、换行、历史列表操作区以及窄屏布局稳定性的本地完成态辩论标题",
        "status": "completed",
        "created_at": created,
        "updated_at": "2026-09-27T08:19:00Z",
        "finished_at": "2026-09-27T08:19:00Z",
        "archived": False,
        "archived_at": None,
        "messages": messages,
        "runtime_state": {
            "phase": "completed",
            "debate_title": "极长标题与详情回放回归样例：中小企业采用生成式AI后的真实净收益是否为正",
            "original_topic": "中小企业采用生成式 AI 后的真实净收益是否为正？",
        },
        "config_summary": {
            "pro": {"model": "preview-pro-model"},
            "con": {"model": "preview-con-model"},
        },
        "result": {
            "winner": "正方（微弱优势）",
            "pro_score": 8.4,
            "con_score": 8.1,
            "conclusion": "效率收益存在，但只在任务可复核、流程成熟且责任边界清楚时稳定出现。",
            "evaluation": {
                "pro_strengths": ["落地路径具体", "主动限定适用范围"],
                "pro_weaknesses": ["长期成本量化不足"],
                "con_strengths": ["风险分类完整", "强调治理前提"],
                "con_weaknesses": ["对低风险场景收益估计偏保守"],
            },
        },
        "usage_stats": {
            "enabled": True,
            "roles": {
                "pro": {"total_tokens": 12840, "input_tokens": 7210, "output_tokens": 5630, "search_calls": 2},
                "con": {"total_tokens": 11920, "input_tokens": 6860, "output_tokens": 5060, "search_calls": 1},
            },
        },
    }


def live_session(session_id: str, status: str) -> dict[str, Any]:
    is_paused = status == "paused"
    messages = [
        {
            "id": f"{session_id}-pro-1",
            "role": "pro",
            "label": "正方",
            "round": 1,
            "timestamp": "2026-09-28T01:02:00Z",
            "content": "实时状态样例：这是第一条正方消息，用于检查消息流和操作按钮。",
            "details": message_details("实时正方"),
        },
        {
            "id": f"{session_id}-con-1",
            "role": "con",
            "label": "反方",
            "round": 1,
            "timestamp": "2026-09-28T01:03:00Z",
            "content": "实时状态样例：这是第一条反方消息，用于检查左右布局。",
            "details": message_details("实时反方"),
        },
    ]
    active_user_message = None
    if is_paused:
        draft = {
            "id": f"{session_id}-user-draft",
            "role": "user",
            "label": "用户发言",
            "content": "暂停态中的可撤回草稿，用来验证输入锁定与恢复编辑。",
            "target_role": "con",
            "stage": "draft",
            "locked": False,
            "timestamp": "2026-09-28T01:04:00Z",
        }
        messages.append(draft)
        active_user_message = deep_copy(draft)
    return {
        "id": session_id,
        "topic": "暂停态下的用户插话、恢复按钮和草稿撤回是否保持一致？" if is_paused else "运行态消息流、输入框、目标菜单和终止操作是否清晰？",
        "status": status,
        "created_at": "2026-09-28T01:00:00Z",
        "updated_at": "2026-09-28T01:04:00Z",
        "archived": False,
        "archived_at": None,
        "messages": messages,
        "runtime_state": {"phase": "debate", "debate_title": "暂停态交互回归" if is_paused else "运行态交互回归"},
        "config_summary": {
            "pro": {"model": "preview-pro-model"},
            "con": {"model": "preview-con-model"},
        },
        "live_status": None if is_paused else {"role": "con", "label": "反方", "content": "正在组织下一轮回应..."},
        "active_user_message": active_user_message,
        "result": {},
    }


def error_session() -> dict[str, Any]:
    return {
        "id": "error-demo",
        "topic": "错误状态、Traceback 容器与错误 Markdown 预览",
        "status": "error",
        "created_at": "2026-09-26T10:00:00Z",
        "updated_at": "2026-09-26T10:02:00Z",
        "finished_at": "2026-09-26T10:02:00Z",
        "archived": False,
        "archived_at": None,
        "messages": [
            {
                "id": "error-system",
                "role": "system",
                "type": "error",
                "label": "系统",
                "timestamp": "2026-09-26T10:02:00Z",
                "content": "预览 fixture 主动构造的错误，不涉及真实模型或网络。",
            }
        ],
        "runtime_state": {"phase": "debate", "debate_title": "错误态回归"},
        "config_summary": {
            "pro": {"model": "preview-pro-model"},
            "con": {"model": "preview-con-model"},
        },
        "error_message": "PreviewFixtureError: 本地隔离错误样例",
        "error_traceback": "Traceback (most recent call last):\n  File \"frontend_preview.py\", line 1, in fixture\nPreviewFixtureError: synthetic failure",
        "result": {},
    }


def archived_session() -> dict[str, Any]:
    session = completed_session()
    session.update(
        {
            "id": "archived-demo",
            "topic": "已归档记录：验证查看、恢复、永久删除和按钮换行",
            "archived": True,
            "archived_at": "2026-09-28T02:00:00Z",
        }
    )
    session["runtime_state"]["debate_title"] = "已归档操作回归"
    for index, message in enumerate(session["messages"]):
        message["id"] = f"archived-message-{index + 1}"
    return session


def make_fixtures(empty: bool = False) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if empty:
        return {}, make_settings()
    sessions = {
        "completed-detail": completed_session(),
        "paused-demo": live_session("paused-demo", "paused"),
        "running-demo": live_session("running-demo", "running"),
        "error-demo": error_session(),
        "archived-demo": archived_session(),
    }
    return sessions, make_settings()


class PreviewState:
    def __init__(self, empty: bool = False) -> None:
        self.sessions, self.settings = make_fixtures(empty)
        self.lock = threading.RLock()
        self.next_session_number = 1
        self.active_detail_tasks: set[str] = set()
        self.cancelled_detail_tasks: set[str] = set()

    def session(self, session_id: str) -> dict[str, Any] | None:
        with self.lock:
            value = self.sessions.get(session_id)
            return deep_copy(value) if value is not None else None

    def summaries(self, archived: bool) -> list[dict[str, Any]]:
        with self.lock:
            items = [value for value in self.sessions.values() if bool(value.get("archived")) is archived]
            items.sort(key=lambda value: str(value.get("created_at") or ""), reverse=True)
            return [self._summary(value) for value in items]

    @staticmethod
    def _summary(session: dict[str, Any]) -> dict[str, Any]:
        messages = session.get("messages") or []
        title = str(session.get("runtime_state", {}).get("debate_title") or session.get("topic") or "")
        preview = str(messages[-1].get("content") or "")[:120] if messages else "暂无消息"
        result = session.get("result") or {}
        return {
            "id": session.get("id"),
            "topic": title,
            "status": session.get("status"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "finished_at": session.get("finished_at"),
            "preview": preview,
            "winner": result.get("winner"),
            "message_count": len(messages),
            "archived": bool(session.get("archived")),
            "archived_at": session.get("archived_at"),
        }


class PreviewRequestHandler(BaseHTTPRequestHandler):
    server_version = "LLMDebateFrontendPreview/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def state(self) -> PreviewState:
        return self.server.preview_state  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        path = self._path()
        if path == "/api/health":
            self._json({"status": "ok", "mode": "isolated-preview"})
            return
        if path == "/api/settings":
            with self.state.lock:
                self._json(deep_copy(self.state.settings))
            return
        if path == "/api/debates":
            self._json(self.state.summaries(archived=False))
            return
        if path == "/api/debates/archived":
            self._json(self.state.summaries(archived=True))
            return
        if path == "/api/records":
            self._json({"detail": [], "error": [self._record_summary("error-demo")]})
            return

        parts = self._parts(path)
        if len(parts) == 5 and parts[:2] == ["api", "debates"] and parts[3] == "export":
            self._export(parts[2], parts[4])
            return
        if len(parts) == 4 and parts[:2] == ["api", "debates"] and parts[3] == "events":
            self._events(parts[2])
            return
        if len(parts) == 4 and parts[:2] == ["api", "records"]:
            self._record(parts[2], parts[3])
            return
        if len(parts) == 3 and parts[:2] == ["api", "debates"]:
            session = self.state.session(parts[2])
            if session is None:
                self._error(HTTPStatus.NOT_FOUND, "未找到该辩论记录。")
            else:
                self._json(session)
            return
        self._static(path)

    def do_PUT(self) -> None:  # noqa: N802
        path = self._path()
        payload = self._read_json()
        if payload is None:
            return
        if path == "/api/settings":
            if not isinstance(payload, dict):
                self._error(HTTPStatus.BAD_REQUEST, "设置必须是 JSON 对象。")
                return
            with self.state.lock:
                preserved_limits = {
                    key: self.state.settings.get(key)
                    for key in ("preset_limit", "supplier_limit", "tool_limit")
                }
                self.state.settings = deep_copy(payload)
                for key, value in preserved_limits.items():
                    self.state.settings.setdefault(key, value)
                response = deep_copy(self.state.settings)
            self._json(response)
            return

        parts = self._parts(path)
        if len(parts) == 4 and parts[:2] == ["api", "debates"] and parts[3] == "title":
            title = str(payload.get("title") or "").strip()
            if not title:
                self._error(HTTPStatus.BAD_REQUEST, "标题不能为空。")
                return
            with self.state.lock:
                session = self.state.sessions.get(parts[2])
                if session is None:
                    self._error(HTTPStatus.NOT_FOUND, "未找到该辩论记录。")
                    return
                session.setdefault("runtime_state", {})["debate_title"] = title[:80]
                session["updated_at"] = utc_now()
                response = deep_copy(session)
            self._json(response)
            return
        self._error(HTTPStatus.NOT_FOUND, "未找到该预览接口。")

    def do_POST(self) -> None:  # noqa: N802
        path = self._path()
        if path == "/api/debates":
            payload = self._read_json()
            if payload is not None:
                self._create_session(payload)
            return

        parts = self._parts(path)
        if len(parts) == 4 and parts[:2] == ["api", "detail-tasks"] and parts[3] == "cancel":
            self._cancel_detail_task(parts[2])
            return
        if len(parts) != 4 or parts[:2] != ["api", "debates"]:
            self._error(HTTPStatus.NOT_FOUND, "未找到该预览接口。")
            return

        session_id, action = parts[2], parts[3]
        if action == "message-detail-view":
            payload = self._read_json()
            if payload is not None:
                self._detail_view(session_id, payload)
            return
        if action == "rewind":
            payload = self._read_json()
            if payload is not None:
                self._rewind(session_id, payload)
            return
        if action == "user-message":
            payload = self._read_json()
            if payload is not None:
                self._add_user_message(session_id, payload)
            return
        if action in {"pause", "resume", "stop", "archive", "restore"}:
            self._session_action(session_id, action)
            return
        self._error(HTTPStatus.NOT_FOUND, "未找到该预览接口。")

    def do_DELETE(self) -> None:  # noqa: N802
        parts = self._parts(self._path())
        if len(parts) == 4 and parts[:2] == ["api", "debates"] and parts[3] == "user-message":
            self._retract_user_message(parts[2])
            return
        if len(parts) == 3 and parts[:2] == ["api", "debates"]:
            with self.state.lock:
                deleted = self.state.sessions.pop(parts[2], None)
            if deleted is None:
                self._error(HTTPStatus.NOT_FOUND, "未找到该辩论记录。")
            else:
                self._json({"deleted": True})
            return
        self._error(HTTPStatus.NOT_FOUND, "未找到该预览接口。")

    def _path(self) -> str:
        return unquote(urlsplit(self.path).path)

    @staticmethod
    def _parts(path: str) -> list[str]:
        return [part for part in path.strip("/").split("/") if part]

    def _read_json(self) -> Any | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "请求体必须是有效 JSON。")
            return None

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, detail: str) -> None:
        self._json({"detail": detail}, status=status)

    def _static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.removeprefix("/assets/") if path.startswith("/assets/") else ""
        if not relative:
            self._error(HTTPStatus.NOT_FOUND, "未找到该静态资源。")
            return
        candidate = (FRONTEND_DIR / relative).resolve()
        try:
            candidate.relative_to(FRONTEND_DIR.resolve())
        except ValueError:
            self._error(HTTPStatus.FORBIDDEN, "禁止访问 frontend 目录之外的文件。")
            return
        if not candidate.is_file():
            self._error(HTTPStatus.NOT_FOUND, "未找到该静态资源。")
            return
        body = candidate.read_bytes()
        media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if candidate.suffix in {".js", ".css", ".md", ".txt", ".svg", ".html"}:
            media_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _events(self, session_id: str) -> None:
        if self.state.session(session_id) is None:
            self._error(HTTPStatus.NOT_FOUND, "未找到该辩论记录。")
            return
        body = b"retry: 5000\n: isolated preview heartbeat; reconnect is expected\n\n"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True

    def _record_summary(self, session_id: str) -> dict[str, Any]:
        session = self.state.session(session_id) or {}
        return {
            "session_id": session_id,
            "kind": "error",
            "display_title": session.get("runtime_state", {}).get("debate_title") or session.get("topic") or session_id,
        }

    def _record(self, kind: str, session_id: str) -> None:
        session = self.state.session(session_id)
        if session is None or kind != "error" or session.get("status") != "error":
            self._error(HTTPStatus.NOT_FOUND, "未找到该记录。")
            return
        content = self._error_markdown(session)
        self._json({**self._record_summary(session_id), "content": content})

    def _export(self, session_id: str, kind: str) -> None:
        session = self.state.session(session_id)
        if session is None:
            self._error(HTTPStatus.NOT_FOUND, "未找到该辩论记录。")
            return
        if kind not in {"simple", "detail"}:
            self._error(HTTPStatus.BAD_REQUEST, "导出类型仅支持 simple 或 detail。")
            return
        content = self._session_markdown(session, detailed=kind == "detail")
        body = content.encode("utf-8")
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{session_id}-{kind}.md"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _session_markdown(session: dict[str, Any], detailed: bool) -> str:
        title = session.get("runtime_state", {}).get("debate_title") or session.get("topic") or "预览记录"
        lines = [f"# {title}", "", f"- fixture ID: `{session.get('id')}`", f"- 状态：{session.get('status')}", "", "## 对话", ""]
        for message in session.get("messages") or []:
            lines.extend([f"### {message.get('label') or message.get('role')}", "", str(message.get("content") or ""), ""])
            if detailed and message.get("details"):
                lines.extend(["<details>", "<summary>调用细节 fixture</summary>", "", "```json", json.dumps(message["details"], ensure_ascii=False, indent=2), "```", "", "</details>", ""])
        result = session.get("result") or {}
        if result:
            lines.extend(["## 结论", "", str(result.get("conclusion") or "暂无结论"), ""])
        return "\n".join(lines)

    @staticmethod
    def _error_markdown(session: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"# 错误·{session.get('topic')}",
                "",
                "## 错误信息",
                "",
                "```text",
                str(session.get("error_message") or "Preview fixture error"),
                "```",
                "",
                "## Traceback",
                "",
                "```text",
                str(session.get("error_traceback") or "No traceback"),
                "```",
            ]
        )

    def _create_session(self, payload: Any) -> None:
        topic = str(payload.get("topic") or "").strip() if isinstance(payload, dict) else ""
        if not topic:
            self._error(HTTPStatus.BAD_REQUEST, "辩题不能为空。")
            return
        with self.state.lock:
            number = self.state.next_session_number
            self.state.next_session_number += 1
            session_id = f"preview-new-{number:03d}"
            session = live_session(session_id, "running")
            session.update({"topic": topic, "created_at": utc_now(), "updated_at": utc_now(), "messages": []})
            session["runtime_state"]["debate_title"] = "正在生成标题..."
            session["live_status"] = {"role": "system", "label": "系统", "content": "本地假会话已创建，不会调用模型。"}
            self.state.sessions[session_id] = session
            response = deep_copy(session)
        self._json(response, status=HTTPStatus.CREATED)

    def _session_action(self, session_id: str, action: str) -> None:
        with self.state.lock:
            session = self.state.sessions.get(session_id)
            if session is None:
                self._error(HTTPStatus.NOT_FOUND, "未找到该辩论记录。")
                return
            status = str(session.get("status") or "")
            if action == "archive" and status in {"queued", "running", "paused"}:
                self._error(HTTPStatus.CONFLICT, "进行中或暂停中的辩论不能归档，请先终止辩论。")
                return
            if action == "pause":
                session["status"] = "paused"
                session["live_status"] = None
            elif action == "resume":
                session["status"] = "running"
                session["live_status"] = {"role": "system", "label": "系统", "content": "本地预览已恢复运行。"}
            elif action == "stop":
                session["status"] = "terminated"
                session["live_status"] = None
                session["termination_message"] = "本地预览中由用户手动终止"
                session["finished_at"] = utc_now()
            elif action == "archive":
                session["archived"] = True
                session["archived_at"] = utc_now()
            elif action == "restore":
                session["archived"] = False
                session["archived_at"] = None
            session["updated_at"] = utc_now()
            response = deep_copy(session)
        self._json(response)

    def _add_user_message(self, session_id: str, payload: Any) -> None:
        content = str(payload.get("content") or "").strip() if isinstance(payload, dict) else ""
        target_role = payload.get("target_role") if isinstance(payload, dict) else None
        if not content:
            self._error(HTTPStatus.BAD_REQUEST, "用户消息不能为空。")
            return
        if target_role not in {None, "pro", "con"}:
            self._error(HTTPStatus.BAD_REQUEST, "发送对象仅支持 pro 或 con。")
            return
        with self.state.lock:
            session = self.state.sessions.get(session_id)
            if session is None:
                self._error(HTTPStatus.NOT_FOUND, "未找到该辩论记录。")
                return
            if session.get("status") not in {"queued", "running", "paused"}:
                self._error(HTTPStatus.CONFLICT, "当前状态不能插入用户消息。")
                return
            if session.get("active_user_message"):
                self._error(HTTPStatus.CONFLICT, "请先撤回当前用户发言。")
                return
            message_id = f"{session_id}-user-{len(session.get('messages') or []) + 1}"
            stage = "draft" if session.get("status") == "paused" else "queued"
            message = {
                "id": message_id,
                "role": "user",
                "label": "用户发言",
                "content": content,
                "target_role": target_role,
                "stage": stage,
                "locked": False,
                "timestamp": utc_now(),
            }
            session["active_user_message"] = deep_copy(message)
            if stage == "draft":
                session.setdefault("messages", []).append(message)
            session["updated_at"] = utc_now()
            response = deep_copy(session)
        self._json(response)

    def _retract_user_message(self, session_id: str) -> None:
        with self.state.lock:
            session = self.state.sessions.get(session_id)
            if session is None:
                self._error(HTTPStatus.NOT_FOUND, "未找到该辩论记录。")
                return
            active = session.get("active_user_message")
            if not isinstance(active, dict):
                self._error(HTTPStatus.CONFLICT, "当前没有可撤回的用户消息。")
                return
            message_id = active.get("id")
            session["messages"] = [item for item in session.get("messages") or [] if item.get("id") != message_id]
            session["active_user_message"] = None
            session["updated_at"] = utc_now()
            response = {
                "session": deep_copy(session),
                "content": active.get("content") or "",
                "target_role": active.get("target_role"),
            }
        self._json(response)

    def _rewind(self, session_id: str, payload: Any) -> None:
        message_id = str(payload.get("message_id") or "") if isinstance(payload, dict) else ""
        clone = bool(payload.get("clone")) if isinstance(payload, dict) else False
        with self.state.lock:
            source = self.state.sessions.get(session_id)
            if source is None:
                self._error(HTTPStatus.NOT_FOUND, "未找到该辩论记录。")
                return
            messages = source.get("messages") or []
            index = next((i for i, item in enumerate(messages) if item.get("id") == message_id), -1)
            if index < 0:
                self._error(HTTPStatus.NOT_FOUND, "未找到目标消息。")
                return
            if clone:
                number = self.state.next_session_number
                self.state.next_session_number += 1
                target = deep_copy(source)
                target_id = f"preview-rewind-{number:03d}"
                target["id"] = target_id
                target["topic"] = f"{source.get('topic')}-恢复"
                target.setdefault("runtime_state", {})["debate_title"] = f"{source.get('runtime_state', {}).get('debate_title') or source.get('topic')}-恢复"
                target["created_at"] = utc_now()
                target["archived"] = False
                target["archived_at"] = None
                self.state.sessions[target_id] = target
            else:
                target = source
                target_id = session_id
            target["messages"] = deep_copy(messages[:index])
            target["status"] = "paused"
            target["result"] = {}
            target["finished_at"] = None
            target["live_status"] = None
            target["active_user_message"] = None
            target["updated_at"] = utc_now()
            response = deep_copy(target)
        self._json(response)

    def _detail_view(self, session_id: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            self._error(HTTPStatus.BAD_REQUEST, "详情请求必须是 JSON 对象。")
            return
        task_id = str(payload.get("task_id") or f"preview-task-{time.monotonic_ns()}")
        with self.state.lock:
            self.state.active_detail_tasks.add(task_id)
            self.state.cancelled_detail_tasks.discard(task_id)
        for _ in range(7):
            time.sleep(DETAIL_DELAY_SECONDS / 7)
            with self.state.lock:
                if task_id in self.state.cancelled_detail_tasks:
                    self.state.active_detail_tasks.discard(task_id)
                    self._json({"cancelled": True, "task_id": task_id})
                    return

        with self.state.lock:
            session = self.state.sessions.get(session_id)
            if session is None:
                self.state.active_detail_tasks.discard(task_id)
                self._error(HTTPStatus.NOT_FOUND, "未找到该辩论记录。")
                return
            message = next((item for item in session.get("messages") or [] if item.get("id") == payload.get("message_id")), None)
            if not isinstance(message, dict):
                self.state.active_detail_tasks.discard(task_id)
                self._error(HTTPStatus.NOT_FOUND, "未找到可处理的辩手消息。")
                return
            try:
                detail = message["details"][int(payload.get("detail_index", -1))]
            except (KeyError, IndexError, TypeError, ValueError):
                self.state.active_detail_tasks.discard(task_id)
                self._error(HTTPStatus.NOT_FOUND, "未找到对应的调用细节。")
                return
            content_kind = str(payload.get("content_kind") or "")
            if content_kind == "reasoning":
                try:
                    container = detail["entries"][int(payload.get("entry_index", -1))]
                except (KeyError, IndexError, TypeError, ValueError):
                    self.state.active_detail_tasks.discard(task_id)
                    self._error(HTTPStatus.NOT_FOUND, "未找到对应的思考内容。")
                    return
            elif content_kind == "tool_result":
                container = detail
            else:
                self.state.active_detail_tasks.discard(task_id)
                self._error(HTTPStatus.BAD_REQUEST, "不支持的详情内容类型。")
                return
            view_name = str(payload.get("view") or "")
            if view_name == "translation":
                view = {
                    "view": "translation",
                    "source_language": "英语（fixture 自动判断）",
                    "translated_content": "这是本地预览服务器返回的假翻译，不调用任何模型。",
                    "content_kind": content_kind,
                    "created_at": utc_now(),
                }
            elif view_name == "summary":
                view = {
                    "view": "summary",
                    "summary_content": "本地假总结：该段内容用于验证切换、缓存、加载态和取消操作。",
                    "content_kind": content_kind,
                    "created_at": utc_now(),
                }
            else:
                self.state.active_detail_tasks.discard(task_id)
                self._error(HTTPStatus.BAD_REQUEST, "详情视图仅支持 translation 或 summary。")
                return
            container.setdefault("views", {})[view_name] = deep_copy(view)
            session["updated_at"] = utc_now()
            self.state.active_detail_tasks.discard(task_id)
            self.state.cancelled_detail_tasks.discard(task_id)
            response = {"view": view, "cached": False, "session": deep_copy(session)}
        self._json(response)

    def _cancel_detail_task(self, task_id: str) -> None:
        with self.state.lock:
            active = task_id in self.state.active_detail_tasks
            if active:
                self.state.cancelled_detail_tasks.add(task_id)
        self._json({"task_id": task_id, "cancelled": active})


class PreviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: PreviewState) -> None:
        super().__init__(address, PreviewRequestHandler)
        self.preview_state = state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the real frontend with isolated in-memory fixtures.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"bind host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help=f"bind port (default: {DEFAULT_PORT})")
    parser.add_argument("--empty", action="store_true", help="start with no debate or archive fixtures")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = PreviewState(empty=args.empty)
    server = PreviewHTTPServer((args.host, args.port), state)
    mode = "empty" if args.empty else "fixtures"
    print(f"Frontend preview ({mode}): http://{args.host}:{args.port}")
    print("In-memory only: no project config/data/logs and no model calls.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
