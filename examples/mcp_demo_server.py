from __future__ import annotations

from mcp.server.fastmcp import (
    FastMCP,
)


mcp = FastMCP(
    "nanobot-mcp-demo"
)


_DEMO_RECORDS = {
    "A-100": (
        "MCP-DEMO-OK: "
        "这是来自真实 MCP Server "
        "进程的数据。"
    ),
    "B-200": (
        "MCP-DEMO-B: "
        "第二条测试记录。"
    ),
}


@mcp.tool()
def lookup_demo_record(
    record_id: str,
) -> str:
    """
    根据记录编号查询 MCP Demo Server
    内部保存的测试记录。
    """

    record_id = (
        record_id.strip()
    )

    if not record_id:
        raise ValueError(
            "record_id 不能为空"
        )

    value = (
        _DEMO_RECORDS.get(
            record_id
        )
    )

    if value is None:
        raise ValueError(
            "不存在记录: "
            f"{record_id}"
        )

    return value

@mcp.resource("demo://guide")
def demo_guide() -> str:
    """返回 Demo MCP Server 的使用说明。"""
    return (
        "这是 MCP Resource Demo。"
        "A-100 是第一条测试记录，"
        "B-200 是第二条测试记录。"
        "Resource 表示可读取的数据，不是 Tool。"
    )


@mcp.prompt()
def explain_demo_record(record_id: str) -> str:
    """生成解释 Demo Record 的提示模板。"""
    return (
        f"请解释测试记录 {record_id} 的含义。"
        "回答时先说明记录编号，再用简洁中文总结内容。"
    )

if __name__ == "__main__":
    mcp.run(
        transport="stdio"
    )