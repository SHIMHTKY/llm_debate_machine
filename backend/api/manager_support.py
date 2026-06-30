"""`DebateRunManager` 的纯辅助层兼容导出。

原本这里承载了大量数据重建逻辑，文件越来越大。
现在已经按职责拆分为：
- `manager_support_parts/messages.py`
- `manager_support_parts/usage.py`
- `manager_support_parts/session_view.py`
- `manager_support_parts/rewind.py`

保留这个文件的唯一目的，是不打断现有导入路径。
调用方仍然可以继续：
`import manager_support as support`
而维护者若要深入阅读，则应直接进入上面四个分模块。
"""

from __future__ import annotations

from .manager_support_parts.messages import (
    build_runtime_from_session,
    create_user_history_item,
    create_user_message_payload,
    format_user_detail_message,
    normalize_target_role,
    required_response_roles,
    user_target_badge,
)
from .manager_support_parts.rewind import (
    mark_pending_user_requirements_responded,
    rebuild_runtime_from_messages,
    resolve_rewind_phase,
    resolve_rewind_target,
    restore_trailing_user_message,
)
from .manager_support_parts.session_view import find_preset_by_name, is_judge_phase, session_display_title
from .manager_support_parts.usage import (
    append_usage_timeline_entry,
    combine_usage_summaries,
    diff_usage_summaries,
    empty_usage_role_stats,
    empty_usage_stage_stats,
    empty_usage_summary,
    rebuild_usage_tracking,
)

__all__ = [
    "append_usage_timeline_entry",
    "build_runtime_from_session",
    "combine_usage_summaries",
    "create_user_history_item",
    "create_user_message_payload",
    "diff_usage_summaries",
    "empty_usage_role_stats",
    "empty_usage_stage_stats",
    "empty_usage_summary",
    "find_preset_by_name",
    "format_user_detail_message",
    "is_judge_phase",
    "mark_pending_user_requirements_responded",
    "normalize_target_role",
    "rebuild_runtime_from_messages",
    "rebuild_usage_tracking",
    "required_response_roles",
    "resolve_rewind_phase",
    "resolve_rewind_target",
    "restore_trailing_user_message",
    "session_display_title",
    "user_target_badge",
]
