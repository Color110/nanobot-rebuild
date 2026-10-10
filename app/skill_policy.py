from __future__ import annotations

from dataclasses import dataclass

from app.skill_activation import (
    SkillActivation,
)


class SkillPolicyError(
    RuntimeError
):
    pass


class SkillConflictError(
    SkillPolicyError
):
    pass


class SkillWorkflowRequiredError(
    SkillPolicyError
):
    pass


class TooManyActiveSkillsError(
    SkillPolicyError
):
    pass


@dataclass(frozen=True)
class SkillConflictRule:
    skills: frozenset[str]
    reason: str

    def __post_init__(self) -> None:
        if len(self.skills) < 2:
            raise ValueError(
                "SkillConflictRule 至少需要两个 Skill"
            )


@dataclass(frozen=True)
class SkillWorkflowRule:
    skills: frozenset[str]
    workflow_name: str
    reason: str

    def __post_init__(self) -> None:
        if len(self.skills) < 2:
            raise ValueError(
                "SkillWorkflowRule 至少需要两个 Skill"
            )

        if not self.workflow_name.strip():
            raise ValueError(
                "workflow_name 不能为空"
            )


@dataclass(frozen=True)
class SkillRuntimePolicy:
    """
    Skill Runtime 的确定性硬约束。
    """

    max_active_skills: int = 3

    conflict_rules: tuple[
        SkillConflictRule,
        ...
    ] = ()

    workflow_rules: tuple[
        SkillWorkflowRule,
        ...
    ] = ()

    def __post_init__(self) -> None:
        if self.max_active_skills <= 0:
            raise ValueError(
                "max_active_skills 必须大于 0"
            )


class SkillPolicyValidator:
    def __init__(
        self,
        policy: SkillRuntimePolicy,
    ) -> None:
        self.policy = policy

    def validate(
        self,
        activations: tuple[
            SkillActivation,
            ...
        ],
    ) -> tuple[
        SkillActivation,
        ...
    ]:
        names = {
            activation.name
            for activation in activations
        }

        if (
            len(names)
            > self.policy.max_active_skills
        ):
            raise TooManyActiveSkillsError(
                "Active Skills 数量超过 "
                f"{self.policy.max_active_skills}: "
                + ", ".join(sorted(names))
            )

        for rule in (
            self.policy.conflict_rules
        ):
            if rule.skills.issubset(names):
                raise SkillConflictError(
                    "检测到互斥 Skills: "
                    + ", ".join(
                        sorted(rule.skills)
                    )
                    + f"; {rule.reason}"
                )

        for rule in (
            self.policy.workflow_rules
        ):
            if rule.skills.issubset(names):
                raise SkillWorkflowRequiredError(
                    "Skill 组合必须由 Workflow "
                    f"'{rule.workflow_name}' 执行: "
                    + ", ".join(
                        sorted(rule.skills)
                    )
                    + f"; {rule.reason}"
                )

        return activations