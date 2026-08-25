import json
import os
import re
import secrets

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.conversation import create_conversation


SESSION_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
)


def utc_now() -> str:
    """
    返回 UTC ISO 8601 时间字符串。
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


@dataclass
class Session:
    """
    一段可持久化的 Agent 会话。
    """

    session_id: str

    messages: list[
        dict[str, Any]
    ] = field(
        default_factory=create_conversation
    )

    created_at: str = field(
        default_factory=utc_now
    )

    updated_at: str = field(
        default_factory=utc_now
    )

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    def touch(self) -> None:
        """
        更新最后修改时间。
        """

        self.updated_at = utc_now()

    def clear(self) -> None:
        """
        清空当前会话，
        重新保留初始 System Prompt。
        """

        self.messages = (
            create_conversation()
        )

        self.touch()

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        转换成可 JSON 序列化结构。
        """

        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "messages": self.messages,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "Session":

        session_id = data.get(
            "session_id"
        )

        messages = data.get(
            "messages"
        )

        if not isinstance(
            session_id,
            str,
        ):
            raise ValueError(
                "Session 缺少合法 session_id"
            )

        if not isinstance(
            messages,
            list,
        ):
            raise ValueError(
                "Session messages 必须是 list"
            )

        metadata = data.get(
            "metadata",
            {},
        )

        if not isinstance(
            metadata,
            dict,
        ):
            raise ValueError(
                "Session metadata 必须是 object"
            )

        return cls(
            session_id=session_id,
            messages=messages,
            created_at=str(
                data.get(
                    "created_at",
                    utc_now(),
                )
            ),
            updated_at=str(
                data.get(
                    "updated_at",
                    utc_now(),
                )
            ),
            metadata=metadata,
        )


class SessionManager:
    """
    Session 的创建、加载和持久化入口。
    """

    def __init__(
        self,
        sessions_dir: Path,
    ) -> None:

        self.sessions_dir = (
            sessions_dir.resolve()
        )

        self.sessions_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def validate_session_id(
        session_id: str,
    ) -> None:

        if not SESSION_ID_PATTERN.fullmatch(
            session_id
        ):
            raise ValueError(
                "非法 Session ID。"
                "只允许字母、数字、_、-、.，"
                "长度1~64，且必须以字母或数字开头。"
            )

    def get_session_path(
        self,
        session_id: str,
    ) -> Path:

        self.validate_session_id(
            session_id
        )

        return (
            self.sessions_dir
            / f"{session_id}.json"
        )

    def exists(
        self,
        session_id: str,
    ) -> bool:

        return self.get_session_path(
            session_id
        ).exists()

    def create(
        self,
        session_id: str,
    ) -> Session:

        self.validate_session_id(
            session_id
        )

        return Session(
            session_id=session_id
        )

    def load(
        self,
        session_id: str,
    ) -> Session | None:

        path = self.get_session_path(
            session_id
        )

        if not path.exists():
            return None

        try:
            raw = path.read_text(
                encoding="utf-8"
            )

            data = json.loads(raw)

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:

            raise RuntimeError(
                f"Session 文件损坏或无法读取: "
                f"{path}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise RuntimeError(
                "Session 文件顶层必须是 JSON object"
            )

        session = Session.from_dict(
            data
        )

        if (
            session.session_id
            != session_id
        ):
            raise RuntimeError(
                "Session 文件中的 ID "
                "与请求 ID 不一致"
            )

        return session

    def get_or_create(
        self,
        session_id: str,
    ) -> Session:

        session = self.load(
            session_id
        )

        if session is not None:
            return session

        return self.create(
            session_id
        )

    def save(
        self,
        session: Session,
    ) -> None:
        """
        原子保存 Session。

        先写临时文件，
        成功后再替换正式文件。
        """

        path = self.get_session_path(
            session.session_id
        )

        session.touch()

        payload = json.dumps(
            session.to_dict(),
            ensure_ascii=False,
            indent=2,
        )
        temp_path = path.with_name(
            f".{path.name}."
            f"{secrets.token_hex(4)}"
            f".tmp"
        )
        try:
            with temp_path.open(
                "x",
                encoding="utf-8",
            ) as file:

                file.write(
                    payload
                )

                file.flush()

                os.fsync(
                    file.fileno()
                )

            os.replace(
                temp_path,
                path,
            )

        finally:
            if temp_path.exists():
                temp_path.unlink()

    def list_session_ids(
        self,
    ) -> list[str]:

        return sorted(
            path.stem
            for path
            in self.sessions_dir.glob(
                "*.json"
            )
        )