"""独立的模型自由对话存储。"""

from __future__ import annotations

from pathlib import Path

from .sessions import SessionStore


class ConversationStore(SessionStore):
    """复用会话文件格式，但把自由对话落到独立目录。"""

    def __init__(self, base_dir: Path | None = None) -> None:
        super().__init__(base_dir=base_dir)
        self.session_dir = self.base_dir / "data" / "conversations"
        self.runtime_config_dir = self.base_dir / "data" / "conversation_runtime_configs"
        self.detail_dir = self.base_dir / "logs" / "conversation_details"
        self.error_dir = self.base_dir / "logs" / "conversation_errors"
        for path in (self.session_dir, self.runtime_config_dir, self.detail_dir, self.error_dir):
            path.mkdir(parents=True, exist_ok=True)

    def create_conversation(
        self,
        prompt: str,
        participants: list[dict],
        config_summary: dict,
        runtime_settings: dict,
    ) -> dict:
        session = self.create_session(
            topic=prompt,
            min_rounds=0,
            max_rounds=0,
            config_summary=config_summary,
            runtime_settings=runtime_settings,
            kind="conversation",
            id_prefix="conversation_",
        )
        return self.update_session(
            session["id"],
            lambda current: {
                **current,
                "participants": participants,
                "prompt": prompt,
            },
        ) or session

    def list_sessions(self, archived: bool = False, *, kind: str = "conversation") -> list[dict]:
        return super().list_sessions(archived=archived, kind=kind)

