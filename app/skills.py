import re
from dataclasses import dataclass
from pathlib import Path

import yaml


_FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?",
    re.DOTALL,
)

_SKILL_NAME_PATTERN = re.compile(
    r"^(?!.*--)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$"
)

_SKILL_REFERENCE_PATTERN = re.compile(
    r"(?<![\w$])\$([A-Za-z0-9_-]+)"
)


class SkillFormatError(ValueError):
    """SKILL.md 格式不合法。"""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path
    instructions: str
    always: bool = False


class SkillLoader:
    """发现、解析和加载 workspace 中的 Skills。"""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.skills_dir = self.workspace / "skills"

    def list_skills(self) -> list[Skill]:
        if not self.skills_dir.exists():
            return []

        skills: list[Skill] = []

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            skills.append(self._load_file(skill_file))

        return skills

    def get(self, name: str) -> Skill | None:
        for skill in self.list_skills():
            if skill.name == name:
                return skill

        return None

    def get_explicitly_invoked_skills(self, text: str) -> list[str]:
        available = {skill.name for skill in self.list_skills()}
        invoked: list[str] = []

        for match in _SKILL_REFERENCE_PATTERN.finditer(text):
            name = match.group(1)

            if name in available and name not in invoked:
                invoked.append(name)

        return invoked

    def get_active_skills(self, current_message: str) -> list[Skill]:
        skills = self.list_skills()
        explicitly_invoked = set(
            self.get_explicitly_invoked_skills(current_message)
        )

        return [
            skill
            for skill in skills
            if skill.always or skill.name in explicitly_invoked
        ]

    def build_summary(self, exclude: set[str] | None = None) -> str:
        excluded = exclude or set()

        skills = [
            skill
            for skill in self.list_skills()
            if skill.name not in excluded
        ]

        if not skills:
            return ""

        lines = [
            "## Available Skills",
            (
                "Skills are reusable task procedures. "
                "When a skill is relevant, read its SKILL.md with "
                "read_text_file before executing the task."
            ),
        ]

        for skill in skills:
            relative_path = skill.path.relative_to(self.workspace).as_posix()
            lines.append(
                f"- **{skill.name}** — {skill.description}  `{relative_path}`"
            )

        return "\n".join(lines)

    def render_active_skills(self, skills: list[Skill]) -> str:
        if not skills:
            return ""

        parts = ["## Active Skills"]

        for skill in skills:
            parts.append(
                f"### Skill: {skill.name}\n\n{skill.instructions}"
            )

        return "\n\n".join(parts)

    def _load_file(self, path: Path) -> Skill:
        content = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_PATTERN.match(content)

        if match is None:
            raise SkillFormatError(
                f"{path} 缺少合法 YAML frontmatter"
            )

        try:
            metadata = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            raise SkillFormatError(
                f"{path} YAML frontmatter 解析失败"
            ) from exc

        if not isinstance(metadata, dict):
            raise SkillFormatError(
                f"{path} frontmatter 必须是 YAML object"
            )

        directory_name = path.parent.name
        name = metadata.get("name")
        description = metadata.get("description")
        always = metadata.get("always", False)

        if not isinstance(name, str):
            raise SkillFormatError(f"{path} 缺少 name")

        if name != directory_name:
            raise SkillFormatError(
                f"Skill name '{name}' 必须和目录名 "
                f"'{directory_name}' 一致"
            )

        if not _SKILL_NAME_PATTERN.fullmatch(name):
            raise SkillFormatError(
                f"非法 Skill name: {name}"
            )

        if not isinstance(description, str) or not description.strip():
            raise SkillFormatError(
                f"{path} 缺少合法 description"
            )

        if len(description.strip()) > 1024:
            raise SkillFormatError(
                f"{path} description 过长"
            )

        if not isinstance(always, bool):
            raise SkillFormatError(
                f"{path} always 必须是 boolean"
            )

        instructions = content[match.end():].strip()

        if not instructions:
            raise SkillFormatError(
                f"{path} 没有 Skill instructions"
            )

        return Skill(
            name=name,
            description=description.strip(),
            path=path,
            instructions=instructions,
            always=always,
        )