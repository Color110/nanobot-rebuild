from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent import AgentRunResult, AgentRunner
from app.conversation import add_message
from app.execution_mode import ExecutionMode
from app.orchestration import OrchestrationResult, WorkflowOrchestrator
from app.session import SessionManager


@dataclass(frozen=True)
class AgentTurnResult:
    session_id: str
    mode: ExecutionMode
    run_result: AgentRunResult | None = None
    orchestration_result: OrchestrationResult | None = None

    def __post_init__(self) -> None:
        has_single = self.run_result is not None
        has_orchestrated = self.orchestration_result is not None
        if has_single == has_orchestrated:
            raise ValueError(
                "AgentTurnResult 必须且只能包含一种执行结果"
            )

    @property
    def final_content(self) -> str:
        if self.run_result is not None:
            return self.run_result.final_content
        assert self.orchestration_result is not None
        return self.orchestration_result.summary

    @property
    def workflow_id(self) -> str | None:
        if self.orchestration_result is None:
            return None
        return self.orchestration_result.workflow_id

    @property
    def trace_id(self) -> str | None:
        if self.orchestration_result is None:
            return None
        return self.orchestration_result.trace_id


class AgentLoop:
    """
    One user-turn lifecycle for both execution modes.

    SINGLE:
        restore -> add user -> AgentRunner -> commit

    ORCHESTRATED:
        restore -> add user -> WorkflowOrchestrator -> commit only the final
        workflow answer back into the parent Session.

    Child-Agent internal messages never leak into the parent Session.
    """

    def __init__(
        self,
        runner: AgentRunner,
        session_manager: SessionManager,
        *,
        orchestrator: WorkflowOrchestrator | None = None,
        orchestration_history_messages: int = 6,
    ) -> None:
        if orchestration_history_messages < 0:
            raise ValueError(
                "orchestration_history_messages 不能小于 0"
            )

        self.runner = runner
        self.session_manager = session_manager
        self.orchestrator = orchestrator
        self.orchestration_history_messages = (
            orchestration_history_messages
        )

    async def process_user_message(
        self,
        session_id: str,
        content: str,
        *,
        mode: ExecutionMode = ExecutionMode.SINGLE,
    ) -> AgentTurnResult:
        content = content.strip()
        if not content:
            raise ValueError("用户消息不能为空")

        session = self.session_manager.get_or_create(session_id)

        # Commit-on-success boundary: work on a copy first.
        initial_messages = list(session.messages)
        add_message(
            initial_messages,
            role="user",
            content=content,
        )

        if mode == ExecutionMode.SINGLE:
            run_result = await self.runner.run(
                initial_messages,
                task_text=content,
            )

            # AgentRunner already returns the full committed message chain.
            session.messages = run_result.messages
            session.metadata["last_execution"] = {
                "mode": ExecutionMode.SINGLE.value,
            }
            self.session_manager.save(session)

            return AgentTurnResult(
                session_id=session_id,
                mode=mode,
                run_result=run_result,
            )

        if mode == ExecutionMode.ORCHESTRATED:
            if self.orchestrator is None:
                raise RuntimeError(
                    "当前 AgentLoop 未配置 WorkflowOrchestrator"
                )

            orchestration_result = await self.orchestrator.run(
                user_goal=content,
                context={
                    "session_id": session_id,
                    "recent_conversation": (
                        self._build_recent_conversation_context(
                            session.messages
                        )
                    ),
                },
            )

            # Important isolation boundary:
            # commit only User + final workflow answer to the parent Session.
            # Planner/SubAgent/tool internal messages remain in TaskStore/Trace.
            committed_messages = initial_messages
            add_message(
                committed_messages,
                role="assistant",
                content=orchestration_result.summary,
            )

            session.messages = committed_messages
            session.metadata["last_execution"] = {
                "mode": ExecutionMode.ORCHESTRATED.value,
                "workflow_id": orchestration_result.workflow_id,
                "trace_id": orchestration_result.trace_id,
                "status": orchestration_result.status.value,
            }
            self.session_manager.save(session)

            return AgentTurnResult(
                session_id=session_id,
                mode=mode,
                orchestration_result=orchestration_result,
            )

        raise ValueError(f"不支持的 ExecutionMode: {mode}")

    def _build_recent_conversation_context(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """
        Give Planner a small amount of parent-conversation context without
        copying system/tool/internal messages into the workflow.
        """
        if self.orchestration_history_messages == 0:
            return []

        conversational: list[dict[str, str]] = []

        for message in messages:
            role = message.get("role")
            content = message.get("content")

            if role not in {"user", "assistant"}:
                continue
            if not isinstance(content, str) or not content.strip():
                continue

            conversational.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        return conversational[-self.orchestration_history_messages :]
