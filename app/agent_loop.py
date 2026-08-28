from dataclasses import dataclass

from app.agent import AgentRunResult, AgentRunner
from app.conversation import add_message
from app.session import SessionManager


@dataclass(frozen=True)
class AgentTurnResult:
    session_id: str
    run_result: AgentRunResult

    @property
    def final_content(self) -> str:
        return self.run_result.final_content


class AgentLoop:
    """
    管理一次用户消息的完整 Turn 生命周期。

    当前 Stage 14 只负责：
    restore session
    -> add user input
    -> run AgentRunner
    -> commit
    -> persist

    Stage 15 再加入 MessageBus。
    """

    def __init__(
        self,
        runner: AgentRunner,
        session_manager: SessionManager,
    ) -> None:
        self.runner = runner
        self.session_manager = session_manager

    async def process_user_message(
        self,
        session_id: str,
        content: str,
    ) -> AgentTurnResult:
        content = content.strip()

        if not content:
            raise ValueError("用户消息不能为空")

        session = self.session_manager.get_or_create(session_id)

        # 创建本轮输入列表，不直接修改 session.messages。
        initial_messages = list(session.messages)

        add_message(
            initial_messages,
            role="user",
            content=content,
        )

        # Runner 自己还会 deepcopy，
        # 因此 Session 在 Run 成功之前始终不会被修改。
        run_result = await self.runner.run(initial_messages)

        # 只有完整 Run 成功到这里，才真正 commit。
        session.messages = run_result.messages

        # commit 后立即持久化。
        self.session_manager.save(session)

        return AgentTurnResult(
            session_id=session_id,
            run_result=run_result,
        )