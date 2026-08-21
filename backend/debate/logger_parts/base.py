"""日志器基础能力。

这个文件只放“所有日志功能都会依赖的最底层能力”：
1. 会话级目录与文件路径初始化。
2. 统一的时间格式生成。
3. detail / error 文件追加写入。
4. SSE 事件回调透传。

之所以把这部分单独拆出来，是为了让上层的 usage 统计逻辑、
业务日志逻辑都只关心“写什么”，而不用重复关心“往哪里写”。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# 这里维护“内部角色键 -> 前端显示名称”的统一映射。
# 后续 detail 日志、SSE 事件、统计汇总都会共用这份映射，
# 所以放在最基础的模块里，避免各处各写一遍字符串。
ROLE_LABELS = {
    "judge": "裁判",
    "pro": "正方",
    "con": "反方",
    "system": "系统",
}

# 只有这三个角色会参与 token / 搜索统计。
# “system” 只负责报错和状态提示，不计入模型资源消耗。
TRACKED_ROLES = ("judge", "pro", "con")


class BaseDebateLogger:
    """提供日志器最基础的文件与事件能力。"""

    def __init__(
        self,
        session_id: str,
        topic: str,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        base_dir: Path | None = None,
        metrics_enabled: bool = False,
    ) -> None:
        # 会话 ID 是所有日志文件命名的主键。
        self.session_id = session_id
        # 辩题会写进 detail / error 日志头部，方便离线排查。
        self.topic = topic
        # on_event 用于把“状态变化 / 消息 / 总结 / 报错”实时推给前端。
        self.on_event = on_event
        # 这里把默认根目录固定为项目根目录，避免调用方每次手动传路径。
        self.base_dir = base_dir or Path(__file__).resolve().parents[3]
        # 详情日志和错误日志分目录存放，方便后续独立清理。
        self.detail_dir = self.base_dir / "logs" / "details"
        self.error_dir = self.base_dir / "logs" / "errors"
        # mkdir 使用 exist_ok=True，保证重复初始化不会报错。
        self.detail_dir.mkdir(parents=True, exist_ok=True)
        self.error_dir.mkdir(parents=True, exist_ok=True)

        # detail 日志在整场辩论里始终固定为一个文件。
        self.detail_log_file = self.detail_dir / f"{session_id}.md"
        # error 日志只有真正发生异常时才创建，所以先记为 None。
        self.error_log_file: Path | None = None
        # 是否启用 token / 工具统计由外层会话设置控制。
        self.metrics_enabled = bool(metrics_enabled)
        # _usage_stats 的具体结构由 UsageLoggerMixin 提供。
        self._usage_stats = self._create_usage_stats()
        # 暂存一次可见消息产生前的模型调用链，消息落盘时会写入 message.details。
        self._pending_model_details: dict[str, list[dict[str, Any]]] = {role: [] for role in TRACKED_ROLES}
        # A debate phase buffers its detail log until the session/runtime commit succeeds.
        self._detail_transaction: list[str] | None = None

    def begin_detail_transaction(self) -> None:
        """Buffer detail-log entries produced by the current runtime phase."""

        self._detail_transaction = []

    def commit_detail_transaction(self) -> None:
        """Append the completed phase detail block after its state commit."""

        entries = self._detail_transaction
        self._detail_transaction = None
        if not entries:
            return
        with self.detail_log_file.open("a", encoding="utf-8") as file:
            file.write("".join(entries))

    def discard_detail_transaction(self) -> None:
        """Discard detail entries from an interrupted or failed phase."""

        self._detail_transaction = None

    def _now(self) -> str:
        """返回带时区的当前时间字符串，秒级精度足够用于日志。"""

        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _code_block(self, content: Any) -> str:
        """把任意对象包成 Markdown 代码块，方便写入 detail 日志。

        这里要把 ``` 做一次转义，避免模型输出里如果刚好带反引号，
        破坏整段日志的 Markdown 结构。
        """

        safe = str(content).replace("```", "``\\`")
        return f"```text\n{safe}\n```"

    def _append_detail(self, text: str) -> None:
        """向 detail 日志文件追加文本。"""

        if self._detail_transaction is not None:
            self._detail_transaction.append(text)
            return
        with self.detail_log_file.open("a", encoding="utf-8") as file:
            file.write(text)

    def _append_error(self, text: str) -> None:
        """向 error 日志文件追加文本。

        error 文件采用懒创建，是因为绝大多数正常辩论不会报错，
        没必要为每个会话都提前生成一个空错误文件。
        """

        if self.error_log_file is None:
            self.error_log_file = self.error_dir / f"{self.session_id}.md"
        with self.error_log_file.open("a", encoding="utf-8") as file:
            file.write(text)

    def _emit(self, payload: dict[str, Any]) -> None:
        """把事件透传给前端。

        这里故意不吞异常，也不做复杂包装：
        事件回调出错属于上游通信问题，应该尽早暴露，而不是在日志层静默忽略。
        """

        if self.on_event is not None:
            self.on_event(payload)
