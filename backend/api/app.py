"""FastAPI 应用入口。

这个文件只做三件事：
1. 创建 FastAPI 应用实例。
2. 注册静态资源与前端首页路由。
3. 把 HTTP 请求转交给 store / manager / settings 子系统处理。

换句话说，这里是“协议层”而不是“业务层”：
- 它关心 URL、HTTP 方法、状态码。
- 它不直接实现辩论流程本身。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..config.settings import load_settings_for_frontend, save_settings_for_frontend
from ..storage.sessions import SessionStore
from .detail_views import build_message_detail_view
from .manager import DebateCapacityError, DebateResumeError, DebateRunManager, DebateStateError
from .schemas import DebateRewindRequest, DebateStartRequest, DebateTitleUpdateRequest, DebateUserMessageRequest, MessageDetailViewRequest

# 项目根目录，用来定位前端静态资源。
BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

# store 负责会话与记录落盘。
store = SessionStore()
# manager 负责真正的运行时生命周期控制。
manager = DebateRunManager(store)


def create_app() -> FastAPI:
    """创建并组装 FastAPI 应用。"""

    app = FastAPI(title="LLM Debate Studio")

    @app.middleware("http")
    async def disable_frontend_cache(request: Request, call_next: Any) -> Response:
        """Avoid serving stale UI bundles while the local studio is iterating quickly."""

        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # 前端 JS/CSS/图片等静态资源统一挂到 /assets。
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")

    @app.get("/")
    async def index() -> FileResponse:
        """返回前端首页。"""

        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """健康检查接口，用于判断后端服务是否存活。"""

        return {"status": "ok"}

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        """读取前端设置页使用的配置快照。"""

        return load_settings_for_frontend()

    @app.put("/api/settings")
    async def update_settings(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """保存设置页提交的配置。

        这里把配置清洗失败统一转成 400，表示“请求格式或内容不合法”。
        """

        try:
            return save_settings_for_frontend(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/debates")
    async def list_debates() -> list[dict[str, Any]]:
        """列出未归档辩论。"""

        return store.list_sessions()

    @app.get("/api/debates/archived")
    async def list_archived_debates() -> list[dict[str, Any]]:
        """列出已归档辩论。"""

        return store.list_sessions(archived=True)

    @app.get("/api/debates/{session_id}")
    async def get_debate(session_id: str) -> dict[str, Any]:
        """读取单场辩论详情。"""

        session = store.load_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return session

    @app.post("/api/debates")
    async def create_debate(payload: DebateStartRequest) -> dict[str, Any]:
        """创建并启动一场新辩论。"""

        try:
            session = await manager.start_debate(
                topic=payload.topic.strip(),
                min_rounds=payload.min_rounds,
                max_rounds=payload.max_rounds,
            )
        except DebateCapacityError as exc:
            # 409 表示服务当前状态不允许创建，而不是请求格式错误。
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DebateStateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return session

    @app.post("/api/debates/{session_id}/stop")
    async def stop_debate(session_id: str) -> dict[str, Any]:
        """终止一场辩论。"""

        session = await manager.stop_debate(session_id, reason="用户手动终止")
        if session is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return session

    @app.post("/api/debates/{session_id}/pause")
    async def pause_debate(session_id: str) -> dict[str, Any]:
        """暂停一场辩论。"""

        session = await manager.pause_debate(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return session

    @app.post("/api/debates/{session_id}/resume")
    async def resume_debate(session_id: str) -> dict[str, Any]:
        """继续一场已暂停辩论。"""

        try:
            session = await manager.resume_debate(session_id)
        except DebateCapacityError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DebateResumeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DebateStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return session

    @app.post("/api/debates/{session_id}/user-message")
    async def add_user_message(session_id: str, payload: DebateUserMessageRequest) -> dict[str, Any]:
        """向辩论中插入一条用户消息。"""

        try:
            session = await manager.add_user_message(session_id, payload.content.strip(), payload.target_role)
        except DebateStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return session

    @app.delete("/api/debates/{session_id}/user-message")
    async def retract_user_message(session_id: str) -> dict[str, Any]:
        """撤回当前可编辑的用户消息。"""

        try:
            result = await manager.retract_user_message(session_id)
        except DebateStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return result

    @app.post("/api/debates/{session_id}/rewind")
    async def rewind_debate(session_id: str, payload: DebateRewindRequest) -> dict[str, Any]:
        """执行截断撤回，或从记录恢复出一个副本。"""

        try:
            session = await manager.rewind_debate(session_id, payload.message_id, clone=payload.clone)
        except DebateCapacityError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DebateStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return session

    @app.put("/api/debates/{session_id}/title")
    async def update_debate_title(session_id: str, payload: DebateTitleUpdateRequest) -> dict[str, Any]:
        """修改一场辩论的显示标题。"""

        try:
            session = await manager.update_debate_title(session_id, payload.title.strip())
        except DebateStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return session

    @app.post("/api/debates/{session_id}/message-detail-view")
    async def create_message_detail_view(session_id: str, payload: MessageDetailViewRequest) -> dict[str, Any]:
        """Generate or read cached translation / summary for a message detail text block."""

        return await build_message_detail_view(store, session_id, payload)

    @app.post("/api/debates/{session_id}/archive")
    async def archive_debate(session_id: str) -> dict[str, Any]:
        """归档一场辩论。"""

        session = store.archive_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return session

    @app.post("/api/debates/{session_id}/restore")
    async def restore_debate(session_id: str) -> dict[str, Any]:
        """把已归档辩论恢复回主列表。"""

        session = store.restore_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return session

    @app.delete("/api/debates/{session_id}")
    async def delete_debate(session_id: str) -> dict[str, bool]:
        """删除一场辩论及其关联数据。"""

        if store.load_session(session_id) is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        # 如果这场辩论仍在运行，先安全终止，再删磁盘数据。
        if manager.is_running(session_id):
            await manager.stop_debate(session_id, reason="用户手动终止")
        deleted = store.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return {"deleted": True}

    @app.get("/api/debates/{session_id}/export/{kind}")
    async def export_debate(session_id: str, kind: str) -> Response:
        """导出简版或详细版 markdown。"""

        if kind not in {"simple", "detail"}:
            raise HTTPException(status_code=400, detail="导出类型仅支持 simple 或 detail。")
        exported = store.export_session_markdown(session_id, kind)
        if exported is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return Response(
            content=exported["content"],
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=\"{exported['filename']}\""},
        )

    @app.get("/api/debates/{session_id}/events")
    async def stream_debate_events(session_id: str):
        """建立某场辩论的 SSE 事件流。"""

        if store.load_session(session_id) is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        return StreamingResponse(
            manager.event_stream(session_id),
            media_type="text/event-stream",
            headers={
                # SSE 需要禁缓存、禁代理缓冲，否则前端收不到实时事件。
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/records")
    async def list_records() -> dict[str, list[dict[str, Any]]]:
        """列出 detail / error 记录索引。"""

        return store.list_records()

    @app.get("/api/records/{kind}/{session_id}")
    async def get_record(kind: str, session_id: str) -> dict[str, Any]:
        """读取某场辩论的 detail 或 error 记录。"""

        record = store.read_record(kind, session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="未找到该记录。")
        return record

    @app.delete("/api/records/{kind}/{session_id}")
    async def delete_record(kind: str, session_id: str) -> dict[str, bool]:
        """删除某场辩论的 detail 或 error 记录文件。"""

        if store.load_session(session_id) is None:
            raise HTTPException(status_code=404, detail="未找到该辩论记录。")
        if manager.is_running(session_id):
            await manager.stop_debate(session_id, reason="用户手动终止")
        deleted = store.delete_record(kind, session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="未找到该记录。")
        return {"deleted": True}

    return app


# 给 uvicorn / main.py 一个可直接导入的应用对象。
app = create_app()
