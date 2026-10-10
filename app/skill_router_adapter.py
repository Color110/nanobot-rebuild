from __future__ import annotations

import json

from app.providers.base import LLMProvider
from app.skill_router import (
    InvalidSkillRouteError,
    SkillRouteDecision,
)


_ROUTE_SKILLS_TOOL = {
    "type": "function",
    "function": {
        "name": "route_skills",
        "description": (
            "Return the final Skill routing decision."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "selected_skills": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "reason": {
                    "type": "string",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
            },
            "required": [
                "selected_skills",
                "reason",
                "confidence",
            ],
            "additionalProperties": False,
        },
    },
}


class LLMProviderSkillRouterAdapter:
    def __init__(
        self,
        provider: LLMProvider,
    ) -> None:
        self.provider = provider

    async def decide_skill_route(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> SkillRouteDecision:
        response = await self.provider.complete(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": (
                        user_prompt
                        + "\n\n"
                        + "You must call route_skills exactly once."
                    ),
                },
            ],
            tools=[
                _ROUTE_SKILLS_TOOL
            ],
        )

        if len(response.tool_calls) != 1:
            raise InvalidSkillRouteError(
                "router must return exactly one "
                "route_skills tool call"
            )

        tool_call = response.tool_calls[0]

        if tool_call.name != "route_skills":
            raise InvalidSkillRouteError(
                "unexpected router tool call: "
                f"{tool_call.name}"
            )

        raw_arguments = tool_call.arguments

        if isinstance(
            raw_arguments,
            str,
        ):
            raw_arguments = json.loads(
                raw_arguments
            )

        if not isinstance(
            raw_arguments,
            dict,
        ):
            raise InvalidSkillRouteError(
                "route_skills arguments "
                "must be an object"
            )

        return (
            SkillRouteDecision
            .model_validate(
                raw_arguments
            )
        )
        