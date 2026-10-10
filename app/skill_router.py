from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.skill_catalog import SkillCatalog
from app.skill_retriever import SkillCandidate


# ============================================================
# Router Input
# ============================================================


@dataclass(frozen=True)
class SkillRouteCandidate:
    """
    LLM Skill Router 真正看到的候选 Skill。

    Retriever 负责产生：
        skill_name / score / rank / retrieval_method

    Catalog 负责补充：
        description / tags

    Router 不直接访问 Retriever 或 Catalog。
    """

    name: str
    description: str
    tags: tuple[str, ...]

    retrieval_rank: int
    retrieval_score: float
    retrieval_method: str


# ============================================================
# Router Output
# ============================================================


class SkillRouteDecision(BaseModel):
    """
    Skill Router 的结构化输出。

    selected_skills:
        []              -> NO_SKILL
        ["code-review"] -> ONE_SKILL
        ["a", "b"]      -> MULTI_SKILL

    confidence 当前只用于 Trace / Eval，
    不作为 Runtime 硬阈值。
    """

    selected_skills: tuple[str, ...] = ()

    reason: str = ""

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    @field_validator("selected_skills")
    @classmethod
    def deduplicate_selected_skills(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(value)
        )


# ============================================================
# Router Model Contract
# ============================================================


class SkillRouterModel(Protocol):
    """
    SkillRouter 与具体 LLMProvider 之间的最小契约。

    SkillRouter 不直接依赖 OpenAI / Qwen / DeepSeek
    或项目已有的 LLMProvider。

    Provider Adapter 下一阶段实现。
    """

    async def decide_skill_route(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> SkillRouteDecision:
        ...


# ============================================================
# Errors
# ============================================================


class InvalidSkillRouteError(
    RuntimeError
):
    pass


# ============================================================
# Prompt
# ============================================================


_ROUTER_SYSTEM_PROMPT = """
You are the Skill Router of an Agent runtime.

Your task is to select which candidate Skills are actually required
for the user's current task.

Rules:

1. Decide primarily according to the user's task intent,
   not merely according to topic keywords.

2. Select a Skill only when the procedure represented by that Skill
   is genuinely required to complete the task.

3. Do not select a Skill merely because the user mentions terms
   related to that Skill.

4. Select no Skill when none of the provided candidates is applicable.

5. Select multiple Skills only when the user's task genuinely contains
   multiple distinct procedures that require different Skills.

6. You may select only Skills from the provided candidate list.

7. Prefer a more specific applicable Skill over a generic Skill.

8. Retrieval rank and retrieval score are weak hints only.
   They must not override semantic applicability.

9. Do not invent Skill names.

Return a structured SkillRouteDecision.
""".strip()


def build_router_prompt(
    *,
    query: str,
    candidates: tuple[
        SkillRouteCandidate,
        ...
    ],
) -> str:
    candidate_blocks: list[str] = []

    for candidate in candidates:
        tags = ", ".join(
            candidate.tags
        )

        block = "\n".join(
            [
                (
                    f"Skill: "
                    f"{candidate.name}"
                ),
                (
                    f"Description: "
                    f"{candidate.description}"
                ),
                (
                    f"Tags: {tags}"
                ),
                (
                    "Retrieval method: "
                    f"{candidate.retrieval_method}"
                ),
                (
                    "Retrieval rank: "
                    f"{candidate.retrieval_rank}"
                ),
                (
                    "Retrieval score: "
                    f"{candidate.retrieval_score:.6f}"
                ),
            ]
        )

        candidate_blocks.append(block)

    candidates_text = "\n\n".join(
        candidate_blocks
    )

    return f"""
User task:

{query}

Candidate Skills:

{candidates_text}

Return:

- selected_skills:
  only Skill names from Candidate Skills.
  Use an empty list if no Skill is needed.

- reason:
  one short explanation of the routing decision.

- confidence:
  a number between 0 and 1.
""".strip()


# ============================================================
# Retrieval Candidate -> Router Candidate
# ============================================================


def build_route_candidates(
    *,
    retrieval_candidates: tuple[
        SkillCandidate,
        ...
    ],
    catalog: SkillCatalog,
) -> tuple[
    SkillRouteCandidate,
    ...
]:
    result: list[
        SkillRouteCandidate
    ] = []

    for candidate in retrieval_candidates:
        descriptor = (
            catalog.get_descriptor(
                candidate.skill_name
            )
        )

        result.append(
            SkillRouteCandidate(
                name=descriptor.name,
                description=(
                    descriptor.description
                ),
                tags=descriptor.tags,
                retrieval_rank=(
                    candidate.rank
                ),
                retrieval_score=(
                    candidate.score
                ),
                retrieval_method=(
                    candidate.retrieval_method
                ),
            )
        )

    return tuple(result)


# ============================================================
# Skill Router
# ============================================================


class SkillRouter:
    def __init__(
        self,
        model: SkillRouterModel,
    ) -> None:
        self.model = model

    async def route(
        self,
        *,
        query: str,
        candidates: tuple[
            SkillRouteCandidate,
            ...
        ],
    ) -> SkillRouteDecision:
        query = query.strip()

        if not query:
            return SkillRouteDecision(
                selected_skills=(),
                reason="empty user task",
                confidence=1.0,
            )

        if not candidates:
            return SkillRouteDecision(
                selected_skills=(),
                reason=(
                    "no candidate skills"
                ),
                confidence=1.0,
            )

        user_prompt = build_router_prompt(
            query=query,
            candidates=candidates,
        )

        decision = (
            await self.model.decide_skill_route(
                system_prompt=(
                    _ROUTER_SYSTEM_PROMPT
                ),
                user_prompt=user_prompt,
            )
        )

        self._validate_decision(
            decision=decision,
            candidates=candidates,
        )

        return decision

    @staticmethod
    def _validate_decision(
        *,
        decision: SkillRouteDecision,
        candidates: tuple[
            SkillRouteCandidate,
            ...
        ],
    ) -> None:
        candidate_names = {
            candidate.name
            for candidate in candidates
        }

        invalid_names = [
            skill_name
            for skill_name
            in decision.selected_skills
            if skill_name
            not in candidate_names
        ]

        if invalid_names:
            raise InvalidSkillRouteError(
                "router selected skills "
                "outside candidate set: "
                + ", ".join(
                    invalid_names
                )
            )