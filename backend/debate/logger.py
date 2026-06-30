"""日志器兼容入口。

外部模块仍然继续从 `backend.debate.logger` 导入 `DebateLogger`，
这样拆分内部实现后，不需要同时修改整条调用链的导入路径。
"""

from .logger_parts import DebateLogger, ROLE_LABELS, TRACKED_ROLES

__all__ = ["DebateLogger", "ROLE_LABELS", "TRACKED_ROLES"]
