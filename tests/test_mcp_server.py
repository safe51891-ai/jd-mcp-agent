import asyncio

from server.mcp_server import mcp


def test_mcp_server_registers_expected_tools():
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"get_order", "list_open_tickets", "create_crm_task"}


def test_write_tool_is_documented_as_write():
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert "WRITE ACTION" in tools["create_crm_task"].description
