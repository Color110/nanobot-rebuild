from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.skill_activation import (
    ActivationResolver,
    SkillActivation,
)
from app.skill_catalog import (
    SkillCatalog,
)
from app.skill_policy import (
    SkillPolicyValidator,
)
from app.skill_retriever import (
    SkillCandidate,
)
from app.skill_router import (
    SkillRouteDecision,
    SkillRouter,
    build_route_candidates,
)
from app.skill_snapshot import (
    SkillSnapshot,
)


class SkillCandidateRetriever(
    Protocol
):
    async def retrieve(
        self,
        query: str,
        top_k: int,
    ) -> tuple[
        SkillCandidate,
        ...
    ]:
        ...


@dataclass(frozen=True)
class SkillSelectionResult:
    retrieval_candidates: tuple[
        SkillCandidate,
        ...
    ]

    route_decision: SkillRouteDecision

    activations: tuple[
        SkillActivation,
        ...
    ]

    snapshots: tuple[
        SkillSnapshot,
        ...
    ]


class SkillSelectionRuntime:
    def __init__(
        self,
        *,
        catalog: SkillCatalog,
        retriever: SkillCandidateRetriever,
        router: SkillRouter,
        activation_resolver: (
            ActivationResolver
        ),
        policy_validator: (
            SkillPolicyValidator
        ),
        top_k: int = 3,
    ) -> None:
        if top_k <= 0:
            raise ValueError(
                "top_k 必须大于 0"
            )

        self.catalog = catalog
        self.retriever = retriever
        self.router = router

        self.activation_resolver = (
            activation_resolver
        )

        self.policy_validator = (
            policy_validator
        )

        self.top_k = top_k

    async def select(
        self,
        user_query: str,
    ) -> SkillSelectionResult:
        # ====================================================
        # 1. Candidate Retrieval
        # ====================================================

        retrieval_candidates = (
            await self.retriever.retrieve(
                user_query,
                top_k=self.top_k,
            )
        )

        # ====================================================
        # 2. Router Candidate Metadata
        # ====================================================

        route_candidates = (
            build_route_candidates(
                retrieval_candidates=(
                    retrieval_candidates
                ),
                catalog=self.catalog,
            )
        )

        # ====================================================
        # 3. LLM Semantic Routing
        # ====================================================

        route_decision = (
            await self.router.route(
                query=user_query,
                candidates=route_candidates,
            )
        )

        # ====================================================
        # 4. Merge Activation Sources
        # ====================================================

        activations = (
            self.activation_resolver.resolve(
                user_text=user_query,
                semantic_skill_names=(
                    route_decision
                    .selected_skills
                ),
            )
        )

        # ====================================================
        # 5. Deterministic Runtime Policy
        # ====================================================

        activations = (
            self.policy_validator.validate(
                activations
            )
        )

        # ====================================================
        # 6. Capture Run-level Snapshot
        # ====================================================

        snapshots = tuple(
            SkillSnapshot.capture(
                skill=(
                    self.catalog.get_enabled(
                        activation.name
                    )
                ),
                sources=activation.sources,
            )
            for activation
            in activations
        )

        return SkillSelectionResult(
            retrieval_candidates=(
                retrieval_candidates
            ),
            route_decision=(
                route_decision
            ),
            activations=activations,
            snapshots=snapshots,
        )