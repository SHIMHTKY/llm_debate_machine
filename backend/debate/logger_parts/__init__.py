"""`DebateLogger` 的分拆实现。"""

from .base import BaseDebateLogger, ROLE_LABELS, TRACKED_ROLES
from .logging import LoggingMixin
from .usage import UsageLoggerMixin


class DebateLogger(LoggingMixin, UsageLoggerMixin, BaseDebateLogger):
    """组合后的正式日志器。

    这个类本身不再塞业务细节，而是只负责把多个 mixin 线性叠起来。
    这样既保留了旧的 `DebateLogger` 对外名字，又让内部代码按职责拆开。
    """


__all__ = ["BaseDebateLogger", "DebateLogger", "ROLE_LABELS", "TRACKED_ROLES"]
