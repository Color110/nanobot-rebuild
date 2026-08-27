import pytest

from app.skills import SkillFormatError, SkillLoader


def create_skill(tmp_path, name="file-math"):
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)

    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"""---
name: {name}
description: 测试 Skill
always: false
---

# Test Skill

必须先读取真实文件，再执行任务。
""",
        encoding="utf-8",
    )

    return skill_file


def test_list_skills(tmp_path):
    create_skill(tmp_path)

    loader = SkillLoader(tmp_path)
    skills = loader.list_skills()

    assert len(skills) == 1
    assert skills[0].name == "file-math"
    assert skills[0].description == "测试 Skill"
    assert "必须先读取真实文件" in skills[0].instructions


def test_explicit_skill_invocation(tmp_path):
    create_skill(tmp_path)

    loader = SkillLoader(tmp_path)

    invoked = loader.get_explicitly_invoked_skills(
        "$file-math 请执行任务"
    )

    assert invoked == ["file-math"]


def test_unknown_explicit_skill_is_ignored(tmp_path):
    create_skill(tmp_path)

    loader = SkillLoader(tmp_path)

    invoked = loader.get_explicitly_invoked_skills(
        "$not-exists 请执行任务"
    )

    assert invoked == []


def test_summary_does_not_load_full_body(tmp_path):
    create_skill(tmp_path)

    loader = SkillLoader(tmp_path)
    summary = loader.build_summary()

    assert "file-math" in summary
    assert "测试 Skill" in summary
    assert "必须先读取真实文件" not in summary


def test_skill_name_must_match_directory(tmp_path):
    skill_dir = tmp_path / "skills" / "file-math"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: wrong-name
description: 错误 Skill
---

body
""",
        encoding="utf-8",
    )

    loader = SkillLoader(tmp_path)

    with pytest.raises(
        SkillFormatError,
        match="必须和目录名",
    ):
        loader.list_skills()