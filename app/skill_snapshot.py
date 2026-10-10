from __future__ import annotations

from dataclasses import dataclass

from app.skills import Skill


@dataclass(frozen=True)
class SkillSnapshot:
    """
    一次 Agent Run 使用的不可变 Skill 执行快照。

    Snapshot 创建以后，本次 Run 不再回到
    SkillLoader / SkillCatalog 读取 instructions。
    """

    name: str
    version: str
    content_hash: str
    instructions: str
    sources: tuple[str, ...]

    @classmethod
    def capture(
        cls,
        *,
        skill: Skill,
        sources: tuple[str, ...],
    ) -> "SkillSnapshot":
        if not skill.content_hash:
            raise ValueError(
                f"Skill {skill.name} 缺少 content_hash"
            )

        return cls(
            name=skill.name,
            version=skill.version,
            content_hash=skill.content_hash,
            instructions=skill.instructions,
            sources=sources,
        )

    @property
    def ref(self) -> str:
        return (
            f"{self.name}@{self.version}"
            f"#{self.content_hash[:12]}"
        )