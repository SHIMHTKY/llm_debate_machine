"""设置清洗用的小工具函数。

这些函数都有一个共同特点：它们不关心“辩论业务”本身，
只关心“把外部输入安全地整理成内部想要的类型”。
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any
from uuid import uuid4

from .constants import (
    DEFAULT_CONTEXT_ROUNDS,
    MASKED_SECRET,
    MAX_CONTEXT_ROUNDS,
    MIN_CONTEXT_ROUNDS,
)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """把任意输入尽量转换成布尔值。"""

    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _text(value: Any, default: str = "") -> str:
    """把任意值规整成去首尾空格后的字符串。"""

    if value is None:
        return default
    return str(value).strip()


def _positive_int(value: Any, default: int) -> int:
    """读取正整数；非法值直接回退默认值。"""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _normalize_context_rounds(value: Any, default: int = DEFAULT_CONTEXT_ROUNDS, *, strict: bool = False) -> int:
    """校验上下文轮数是否合法。"""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        if strict:
            raise ValueError(f"上下文轮数必须是 {MIN_CONTEXT_ROUNDS} 到 {MAX_CONTEXT_ROUNDS} 之间的整数。")
        return default
    if MIN_CONTEXT_ROUNDS <= parsed <= MAX_CONTEXT_ROUNDS:
        return parsed
    if strict:
        raise ValueError(f"上下文轮数必须是 {MIN_CONTEXT_ROUNDS} 到 {MAX_CONTEXT_ROUNDS} 之间的整数。")
    return default


def _mask_secret(value: Any) -> str:
    """把真实密钥映射成统一掩码。"""

    return MASKED_SECRET if _text(value) else ""


def _normalize_secret(value: Any, existing_value: str = "") -> str:
    """处理前端回传的密钥字段。

    当前端把掩码原样提交回来时，说明用户没有改密钥，
    这时应该继续沿用旧值，而不是把掩码写进配置文件。
    """

    if value is None:
        return existing_value
    text = _text(value)
    if text == MASKED_SECRET and existing_value:
        return existing_value
    return text


def _normalize_extra_body(
    value: Any,
    existing_value: dict[str, Any] | None = None,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """把 extra_body 转成对象。

    这里允许较宽松的输入，是因为设置页经常会收到用户手写文本：
    - 标准 JSON
    - Python 字典字面量
    - 键未加引号的近似 JSON
    """

    base_value = existing_value.copy() if isinstance(existing_value, dict) else {}
    if value is None:
        return base_value
    if isinstance(value, dict):
        return value.copy()

    text = _text(value)
    if not text:
        return {}

    relaxed_text = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', text)
    relaxed_text = relaxed_text.replace("True", "true").replace("False", "false").replace("None", "null")

    last_error: Exception | None = None
    for parser, candidate in ((json.loads, text), (ast.literal_eval, text), (json.loads, relaxed_text)):
        try:
            parsed = parser(candidate)
        except (json.JSONDecodeError, ValueError, SyntaxError) as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed.copy()
        last_error = ValueError("extra_body must be an object")

    if strict:
        raise ValueError(
            'ChatOpenAI 额外参数 extra_body 必须是对象，例如 {"enable_thinking": true} 或 {"enable_thinking": True}。'
        ) from last_error
    return base_value


def _create_preset_id() -> str:
    """生成短一些的 preset ID，便于前后端传递。"""

    return f"preset_{uuid4().hex[:12]}"
