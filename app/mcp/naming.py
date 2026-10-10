import re


_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_component(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} 不能为空")

    if not _COMPONENT_RE.fullmatch(value):
        raise ValueError(
            f"{label} 只能包含字母、数字、下划线和连字符"
        )


def make_mcp_tool_name(*, server_name: str, tool_name: str) -> str:
    _validate_component(server_name, "MCP server_name")
    _validate_component(tool_name, "MCP tool_name")
    return f"mcp__{server_name}__{tool_name}"


def make_mcp_prompt_name(*, server_name: str, prompt_name: str) -> str:
    _validate_component(server_name, "MCP server_name")
    _validate_component(prompt_name, "MCP prompt_name")
    return f"mcp__{server_name}__prompt__{prompt_name}"