import json
import os,re
import secrets

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.providers import LLMProvider

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryCandidate(BaseModel):
    """LLM 从 Conversation 中提取出的一条候选长期记忆。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$",
        description=(
            "稳定、简洁的小写记忆键，例如 "
            "user.name、user.language_preference、project.main_language"
        ),
    )

    value: str = Field(
        min_length=1,
        max_length=500,
        description="值得未来继续使用的长期信息",
    )


@dataclass
class MemoryRecord:
    """真正写入长期存储的一条 Memory。"""

    key: str
    value: str
    source_session: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source_session": self.source_session,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        return cls(
            key=str(data["key"]),
            value=str(data["value"]),
            source_session=str(data.get("source_session", "unknown")),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
        )


class MemoryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memories: list[MemoryCandidate] = Field(
        max_length=20,
        description="从当前 Conversation 中提取出的值得长期保存的信息列表",
    )


MEMORY_SAVE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "save_memories",
        "description": (
            "提交从当前对话中提取出的长期记忆。"
            "只保存未来仍然有价值的稳定信息。"
        ),
        "parameters": MemoryBatch.model_json_schema(),
    },
}
_SECRET_KEY_PATTERN = re.compile(
    r"(?:^|[._-])"
    r"(?:password|passwd|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|private[_-]?key|secret)"
    r"(?:$|[._-])",
    re.IGNORECASE,
)


_SECRET_VALUE_PATTERNS = (
    re.compile(
        r"\bsk-[A-Za-z0-9_-]{12,}\b"
    ),
    re.compile(
        r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
    ),
    re.compile(
        r"(?:password|passwd|api[_ -]?key|"
        r"access[_ -]?token|refresh[_ -]?token|"
        r"secret|密码)"
        r"\s*[:=：]\s*\S+",
        re.IGNORECASE,
    ),
)
@dataclass(frozen=True)
class MemoryAdmissionPolicy:
    """
    长期 Memory 的 Runtime 准入边界。

    LLM 只负责提出 Candidate；
    Runtime 决定 Candidate 是否允许持久化。
    """

    def filter(
        self,
        memories: list[MemoryCandidate],
    ) -> list[MemoryCandidate]:

        accepted: list[MemoryCandidate] = []

        for memory in memories:
            key = memory.key.strip().lower()
            value = memory.value.strip()

            if _SECRET_KEY_PATTERN.search(key):
                continue

            if any(
                pattern.search(value)
                for pattern in _SECRET_VALUE_PATTERNS
            ):
                continue

            accepted.append(
                MemoryCandidate(
                    key=key,
                    value=value,
                )
            )

        return accepted
class MemoryStore:

    def __init__(self, workspace: Path) -> None:
        self.memory_dir = workspace.resolve() / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.memory_dir / "memories.json"

    def load(self) -> list[MemoryRecord]:
        if not self.memory_file.exists():
            return []

        try:
            raw = self.memory_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("长期记忆文件损坏或无法读取") from exc

        if not isinstance(data, list):
            raise RuntimeError("Memory 文件顶层必须是数组")

        return [
            MemoryRecord.from_dict(item)
            for item in data
            if isinstance(item, dict)
        ]

    def save(self, records: list[MemoryRecord]) -> None:
        payload = json.dumps(
            [record.to_dict() for record in records],
            ensure_ascii=False,
            indent=2,
        )

        temp_path = self.memory_file.with_name(
            f".{self.memory_file.name}.{secrets.token_hex(4)}.tmp"
        )

        try:
            with temp_path.open("x", encoding="utf-8") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())

            os.replace(temp_path, self.memory_file)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def upsert_many(self, memories: list[MemoryCandidate], source_session: str) -> int:
        records = self.load()
        by_key = {record.key: record for record in records}
        changed = 0

        for memory in memories:
            key = memory.key.strip().lower()
            value = memory.value.strip()
            now = utc_now()

            existing = by_key.get(key)

            if existing is None:
                by_key[key] = MemoryRecord(
                    key=key,
                    value=value,
                    source_session=source_session,
                    created_at=now,
                    updated_at=now,
                )
                changed += 1
                continue

            if existing.value != value:
                existing.value = value
                existing.source_session = source_session
                existing.updated_at = now
                changed += 1

        self.save(sorted(by_key.values(), key=lambda item: item.key))
        return changed

   
    def clear(self) -> None:
        self.save([])

    def list_records(self) -> list[MemoryRecord]:
        return self.load()
    def delete(
        self,
        key: str,
    ) -> bool:

        normalized_key = key.strip().lower()

        records = self.load()

        kept = [
            record
            for record in records
            if record.key.lower()
            != normalized_key
        ]

        if len(kept) == len(records):
            return False

        self.save(kept)

        return True
def build_memory_transcript(
    messages: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    for message in messages:
        role = message.get("role")
        content = message.get("content")

        # 长期用户事实只允许来自用户明确陈述。
        if role != "user":
            continue

        if not isinstance(content, str):
            continue

        content = content.strip()

        if not content:
            continue

        lines.append(f"USER: {content}")

    return "\n".join(lines)

async def extract_memories(
    messages: list[dict[str, Any]],
    provider: LLMProvider,
) -> list[MemoryCandidate]:
    transcript = build_memory_transcript(messages)

    if not transcript:
        return []

    extraction_messages = [
        {
            "role": "system",
            "content": (
                "你是长期记忆提取器。"
                "你只能依据 USER 明确陈述过的信息生成长期记忆。"
                "不能把 Assistant 的推断、总结或外部工具内容当作用户事实。"
                "不要根据语气、暗示或可能性猜测长期状态。"
                "请从对话中提取未来多个会话中仍然有价值的稳定信息。"
                "\n\n"
                "适合保存："
                "\n- 稳定身份信息"
                "\n- 长期偏好"
                "\n- 长期学习或工作目标"
                "\n- 持续性的项目事实"
                "\n- 明确的长期约束"
                "\n\n"
                "不要保存："
                "\n- 一次性问题"
                "\n- 临时状态"
                "\n- 当前工具输出"
                "\n- API Key、密码、Token等秘密信息"
                "\n- 没有明确依据的推测"
                "\n\n"
                "如果存在值得保存的信息，调用 save_memories。"
                "如果没有，直接回复 NONE。"
            ),
        },
        {
            "role": "user",
            "content": transcript,
        },
    ]

    result = await provider.complete(extraction_messages, tools=[MEMORY_SAVE_TOOL_SCHEMA])

    candidates: list[MemoryCandidate] = []

    for tool_call in result.tool_calls:
        if tool_call.name != "save_memories":
            continue

        batch = MemoryBatch.model_validate(tool_call.arguments, strict=True)
        candidates.extend(batch.memories)

    return candidates

async def consolidate_session_to_memory(
    messages: list[dict[str, Any]],
    session_id: str,
    store: MemoryStore,
    provider: LLMProvider,
    admission_policy: MemoryAdmissionPolicy | None = None,
) -> tuple[int, list[MemoryCandidate]]:

    candidates = await extract_memories(
        messages,
        provider,
    )

    policy = (
        admission_policy
        or MemoryAdmissionPolicy()
    )

    accepted = policy.filter(candidates)

    changed = store.upsert_many(
        accepted,
        source_session=session_id,
    )

    return changed, accepted