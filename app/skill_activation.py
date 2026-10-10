from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.skill_catalog import SkillCatalog
from app.skills import Skill

import re
from dataclasses import dataclass

from app.skill_catalog import SkillCatalog



_SKILL_REFERENCE_PATTERN = re.compile(
    r"(?<![\w$])\$([A-Za-z0-9_-]+)"
)


ActivationSource = Literal[
    "always",
    "explicit",
    "semantic",
]


ActivationIssueReason = Literal[
    "unknown",
    "disabled",
]


@dataclass(frozen=True)
class SkillActivation:
    """
    一项 Skill 激活结果。

    sources 用 tuple 是因为同一个 Skill
    可能同时被 always / explicit / semantic 命中。
    """

    skill: Skill
    sources: tuple[ActivationSource, ...]


@dataclass(frozen=True)
class SkillActivationIssue:
    """
    显式 Skill 激活失败。

    例如：
    $not-exist
    $disabled-skill
    """

    name: str
    reason: ActivationIssueReason


@dataclass(frozen=True)
class SkillActivationResult:
    activations: tuple[SkillActivation, ...]
    issues: tuple[SkillActivationIssue, ...]


class SkillActivationResolver:
    """
    汇总 Skill 的不同激活来源。

    当前支持：
    1. always
    2. explicit $skill-name

    后续会接入：
    3. semantic retrieval/router
    """

    def __init__(self, catalog: SkillCatalog) -> None:
        self.catalog = catalog

    def resolve_always(self) -> tuple[SkillActivation, ...]:
        """
        enabled=true 且 always=true 的 Skill 自动激活。
        """

        return tuple(
            SkillActivation(
                skill=skill,
                sources=("always",),
            )
            for skill in self.catalog.list_enabled()
            if skill.always
        )

    def resolve_explicit(
        self,
        text: str,
    ) -> tuple[
        tuple[SkillActivation, ...],
        tuple[SkillActivationIssue, ...],
    ]:
        """
        解析用户显式写出的 $skill-name。
        """

        activations: list[SkillActivation] = []
        issues: list[SkillActivationIssue] = []

        seen: set[str] = set()

        for match in _SKILL_REFERENCE_PATTERN.finditer(text):
            name = match.group(1).lower()

            if name in seen:
                continue

            seen.add(name)

            skill = self.catalog.get(name)

            if skill is None:
                issues.append(
                    SkillActivationIssue(
                        name=name,
                        reason="unknown",
                    )
                )
                continue

            if not skill.enabled:
                issues.append(
                    SkillActivationIssue(
                        name=name,
                        reason="disabled",
                    )
                )
                continue

            activations.append(
                SkillActivation(
                    skill=skill,
                    sources=("explicit",),
                )
            )

        return (
            tuple(activations),
            tuple(issues),
        )

    def resolve_semantic(
        self,
        skill_names: tuple[str, ...],
    ) -> tuple[SkillActivation, ...]:
        """
        为下一阶段 Semantic Retriever 预留。

        Retriever / Router 最终给出 skill name 后，
        在这里重新经过 Catalog 可用性校验。
        """

        activations: list[SkillActivation] = []

        for name in skill_names:
            skill = self.catalog.get_enabled(name)

            if skill is None:
                continue

            activations.append(
                SkillActivation(
                    skill=skill,
                    sources=("semantic",),
                )
            )

        return tuple(activations)

    def resolve(
        self,
        text: str,
        semantic_skill_names: tuple[str, ...] = (),
    ) -> SkillActivationResult:
        """
        汇总：
        always + explicit + semantic

        当前 semantic_skill_names 可以为空。
        后面 SkillRouter 完成后直接接入。
        """

        always_activations = self.resolve_always()

        (
            explicit_activations,
            issues,
        ) = self.resolve_explicit(text)

        semantic_activations = self.resolve_semantic(
            semantic_skill_names
        )

        merged = self._merge_activations(
            always_activations,
            explicit_activations,
            semantic_activations,
        )

        return SkillActivationResult(
            activations=merged,
            issues=issues,
        )

    @staticmethod
    def _merge_activations(
        *groups: tuple[SkillActivation, ...],
    ) -> tuple[SkillActivation, ...]:
        """
        按 Skill name 去重，同时保留所有激活来源。
        """

        merged: dict[str, SkillActivation] = {}
        order: list[str] = []

        for group in groups:
            for activation in group:
                name = activation.skill.name

                if name not in merged:
                    merged[name] = activation
                    order.append(name)
                    continue

                current = merged[name]

                sources = tuple(
                    dict.fromkeys(
                        [
                            *current.sources,
                            *activation.sources,
                        ]
                    )
                )

                merged[name] = SkillActivation(
                    skill=current.skill,
                    sources=sources,
                )

        return tuple(
            merged[name]
            for name in order
        )

_EXPLICIT_SKILL_PATTERN = re.compile(
    r"\$([A-Za-z0-9][A-Za-z0-9_-]*)"
)


@dataclass(frozen=True)
class SkillActivation:
    name: str
    sources: tuple[str, ...]


class ActivationResolver:
    def __init__(
        self,
        catalog: SkillCatalog,
    ) -> None:
        self.catalog = catalog

    def resolve(
        self,
        *,
        user_text: str,
        semantic_skill_names: tuple[
            str,
            ...
        ] = (),
    ) -> tuple[
        SkillActivation,
        ...
    ]:
        source_map: dict[
            str,
            list[str],
        ] = {}

        def add(
            name: str,
            source: str,
        ) -> None:
            skill = (
                self.catalog.get_enabled(
                    name
                )
            )

            if skill.name not in source_map:
                source_map[
                    skill.name
                ] = []

            if (
                source
                not in source_map[
                    skill.name
                ]
            ):
                source_map[
                    skill.name
                ].append(
                    source
                )

        # 1. always
        for skill in (
            self.catalog.list_enabled()
        ):
            if skill.always:
                add(
                    skill.name,
                    "always",
                )

        # 2. explicit
        for name in (
            _EXPLICIT_SKILL_PATTERN.findall(
                user_text
            )
        ):
            add(
                name,
                "explicit",
            )

        # 3. semantic
        for name in (
            semantic_skill_names
        ):
            add(
                name,
                "semantic",
            )

        return tuple(
            SkillActivation(
                name=name,
                sources=tuple(sources),
            )
            for name, sources
            in source_map.items()
        )