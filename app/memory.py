import json
import os
import secrets

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.llm import ask_llm


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryCandidate(BaseModel):
    """LLM 从 Conversation 中提取出的一条候选长期记忆。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(
        min_length=1,
        max_length=80,
        description="稳定、简洁的记忆键，例如 user.name、user.language_preference、project.main_language",
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
            key = memory.key.strip()
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

    def render_context(self) -> str:
        records = self.load()
        if not records:
            return ""

        lines = ["## Long-term Memory"]
        for record in records:
            lines.append(f"- [{record.key}] {record.value}")
        return "\n".join(lines)

    def clear(self) -> None:
        self.save([])

    def list_records(self) -> list[MemoryRecord]:
        return self.load()


def build_memory_transcript(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if role not in {"user", "assistant"}:
            continue

        if not isinstance(content, str):
            continue

        content = content.strip()
        if not content:
            continue

        lines.append(f"{role.upper()}: {content}")

    return "\n".join(lines)


def extract_memories(messages: list[dict[str, Any]]) -> list[MemoryCandidate]:
    transcript = build_memory_transcript(messages)

    if not transcript:
        return []

    extraction_messages = [
        {
            "role": "system",
            "content": (
                "你是长期记忆提取器。"
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

    result = ask_llm(extraction_messages, tools=[MEMORY_SAVE_TOOL_SCHEMA])

    candidates: list[MemoryCandidate] = []

    for tool_call in result.tool_calls:
        if tool_call.name != "save_memories":
            continue

        batch = MemoryBatch.model_validate(tool_call.arguments, strict=True)
        candidates.extend(batch.memories)

    return candidates


def consolidate_session_to_memory(
    messages: list[dict[str, Any]],
    session_id: str,
    store: MemoryStore,
) -> tuple[int, list[MemoryCandidate]]:
    candidates = extract_memories(messages)
    changed = store.upsert_many(candidates, source_session=session_id)
    return changed, candidates