from dataclasses import dataclass
from collections.abc import Iterable

from app.skills import Skill


class SkillCatalogError(RuntimeError):
    """SkillCatalog 构建或查询异常。"""


@dataclass(frozen=True)
class SkillDescriptor:
    """
    Skill 的轻量路由描述。

    与完整 Skill 不同：
    - 不包含 instructions
    - 不包含 path
    - 不包含 version/hash
    - 只包含 Skill Selection 真正需要的信息
    """

    name: str
    description: str
    tags: tuple[str, ...]

    @classmethod
    def from_skill(cls, skill: Skill) -> "SkillDescriptor":
        return cls(
            name=skill.name,
            description=skill.description,
            tags=skill.tags,
        )
    def get_descriptor(
        self,
        name: str,
        ) -> "SkillDescriptor":
        return SkillDescriptor.from_skill(
            self.get_enabled(name)
        )

    def routing_text(self) -> str:
        tags_text = ", ".join(self.tags)

        return (
            f"name: {self.name}\n"
            f"description: {self.description}\n"
            f"tags: {tags_text}"
        )


class SkillCatalog:
    """
    Skill 的运行时目录。

    SkillLoader：
        负责从 SKILL.md 加载合法 Skill。

    SkillCatalog：
        负责维护当前系统中的 Skill，
        并提供 enabled Skill 给后续 Retriever / Router。
    """

    def __init__(self, skills: Iterable[Skill]) -> None:
        self._skills_by_name: dict[str, Skill] = {}

        for skill in skills:
            if skill.name in self._skills_by_name:
                raise SkillCatalogError(
                    f"duplicate skill name: {skill.name}"
                )

            self._skills_by_name[skill.name] = skill

    def list_all(self) -> tuple[Skill, ...]:
        """返回所有已加载 Skill，包括 disabled Skill。"""

        return tuple(self._skills_by_name.values())

    def list_enabled(self) -> tuple[Skill, ...]:
        """只返回当前运行时允许使用的 Skill。"""

        return tuple(
            skill
            for skill in self._skills_by_name.values()
            if skill.enabled
        )

    def get(self, name: str) -> Skill | None:
        """
        获取 Skill。

        即使 Skill disabled，也可以查到。
        主要用于管理、调试等场景。
        """

        return self._skills_by_name.get(name)

    def get_enabled(self, name: str) -> Skill | None:
        """
        获取当前可用 Skill。

        Retriever、Router、显式激活应该使用这个接口。
        """

        skill = self.get(name)

        if skill is None:
            return None

        if not skill.enabled:
            return None

        return skill
    def get_descriptor(
        self,
        name: str,
    ) -> SkillDescriptor:
        """
        返回一个可用于 Retrieval / Router 的轻量 Skill 描述。

        Router 只看到：
        - name
        - description
        - tags

        不暴露完整 instructions。
        """

        skill = self.get_enabled(name)

        return SkillDescriptor(
            name=skill.name,
            description=skill.description,
            tags=skill.tags,
        )
    def descriptors(self) -> tuple[SkillDescriptor, ...]:
        """
        返回所有可检索 Skill 的轻量描述。

        后面的 SkillRetriever 就从这里建立索引。
        """

        return tuple(
            SkillDescriptor.from_skill(skill)
            for skill in self.list_enabled()
        )

    def __len__(self) -> int:
        return len(self._skills_by_name)