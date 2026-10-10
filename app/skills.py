import re
from dataclasses import dataclass
from pathlib import Path

import yaml
import hashlib

_FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?",
    re.DOTALL,
)

_SKILL_NAME_PATTERN = re.compile(
    r"^(?!.*--)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$"
)


_SKILL_VERSION_PATTERN = re.compile(
    r"^\d+\.\d+\.\d+$"
)


class SkillFormatError(ValueError):
    """SKILL.md 格式不合法。"""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    version: str 
    tags:tuple[str, ...]
    path: Path
    instructions: str
    always: bool = False
    enabled: bool = True
    content_hash: str=""


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

    def _load_file(self, path: Path) -> Skill:
        content = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_PATTERN.match(content)
        content_hash = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()
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
        version = metadata.get("version", "1.0.0")
        tags = metadata.get("tags", [])
        enabled = metadata.get("enabled", True)

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

        if not isinstance(version, str):
            raise SkillFormatError(
                f"{path} version 必须是 string"
            )

        version = version.strip()

        if not _SKILL_VERSION_PATTERN.fullmatch(version):
            raise SkillFormatError(
                f"{path} version 必须符合 x.y.z 格式"
            )

        if not isinstance(tags, list):
            raise SkillFormatError(
                f"{path} tags 必须是 string list"
            )

        normalized_tags: list[str] = []

        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                raise SkillFormatError(
                    f"{path} tags 必须包含非空字符串"
                )

            normalized_tags.append(tag.strip().lower())
        tags = tuple(normalized_tags)
        if not isinstance(enabled, bool):
            raise SkillFormatError(
                f"{path} enabled 必须是 boolean"
            )
        instructions = content[match.end():].strip()

        if not instructions:
            raise SkillFormatError(
                f"{path} 没有 Skill instructions"
            )

        return Skill(
            name=name,
            description=description.strip(),
            version=version,
            tags=tags,
            path=path,
            instructions=instructions,
            always=always,
            enabled=enabled,
            content_hash=content_hash
        )