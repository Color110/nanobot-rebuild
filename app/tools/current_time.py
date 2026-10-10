from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field

from app.tools.base import PydanticTool, ToolExecutionError


class CurrentTimeArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str = Field(
        default="UTC",
        min_length=1,
        max_length=100,
        description=(
            "IANA timezone，例如 UTC、Asia/Shanghai、Asia/Tokyo。"
            "如果用户没有给出时区，应优先使用明确的上下文时区，否则使用 UTC。"
        ),
    )


class CurrentTimeTool(PydanticTool):
    @property
    def name(self) -> str:
        return "current_time"

    @property
    def description(self) -> str:
        return (
            "获取指定 IANA timezone 的当前日期和时间。"
            "当任务依赖‘现在、今天、今晚、当前日期’等实时时间信息时使用。"
        )

    @property
    def argument_model(self) -> type[BaseModel]:
        return CurrentTimeArguments

    async def execute(self, **kwargs: Any) -> str:
        timezone_name = kwargs["timezone"]
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ToolExecutionError(
                f"未知 timezone: {timezone_name}",
                error_type="INVALID_TIMEZONE",
            ) from exc

        now = datetime.now(tz=zone)
        return json.dumps(
            {
                "timezone": timezone_name,
                "iso8601": now.isoformat(),
                "date": now.date().isoformat(),
                "time": now.timetz().isoformat(),
                "unix_seconds": int(now.astimezone(timezone.utc).timestamp()),
            },
            ensure_ascii=False,
        )
