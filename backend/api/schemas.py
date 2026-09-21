from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class DebateStartRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    min_rounds: int = Field(default=4, ge=2, le=10)
    max_rounds: int = Field(default=6, ge=2, le=10)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("辩题不能为空。")
        return cleaned

    @model_validator(mode="after")
    def validate_rounds(self) -> "DebateStartRequest":
        if self.max_rounds < self.min_rounds:
            raise ValueError("最小轮数必须小于等于最大轮数。")
        return self


class DebateUserMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    target_role: Literal["pro", "con"] | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("用户消息不能为空。")
        return cleaned


class DebateRewindRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=128)
    clone: bool = False


class DebateTitleUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("标题不能为空。")
        return cleaned


class MessageDetailViewRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=128)
    detail_index: int = Field(ge=0)
    content_kind: Literal["reasoning", "tool_result"]
    view: Literal["translation", "summary"]
    entry_index: int | None = Field(default=None, ge=0)
    task_id: str | None = Field(default=None, min_length=1, max_length=128)
