"""会话存储公共入口。

真正实现已经拆分到 `backend.storage.session_parts`：
- `base.py`：基础路径、锁和底层读写。
- `data.py`：会话 JSON 主数据。
- `records.py`：detail / error 日志文件。
- `export.py`：Markdown 导出。

这里保留兼容层，只为了让旧导入路径继续生效。
"""

from __future__ import annotations

from .session_parts.base import BaseSessionStore
from .session_parts.data import SessionDataMixin
from .session_parts.export import SessionExportMixin
from .session_parts.records import SessionRecordMixin


class SessionStore(SessionExportMixin, SessionRecordMixin, SessionDataMixin, BaseSessionStore):
    """组合后的最终 `SessionStore`。"""


__all__ = ["SessionStore"]
