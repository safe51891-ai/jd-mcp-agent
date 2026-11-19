"""MCP server exposing business tools to any MCP-compatible client (Claude Desktop, Claude Code, etc.).

Run:  python -m server.mcp_server
"""
import os

from mcp.server.fastmcp import FastMCP

from server import db

mcp = FastMCP("business-tools")
_conn = db.connect(os.getenv("BUSINESS_DB", db.DEFAULT_DB))


@mcp.tool()
def get_order(order_id: str) -> dict:
    """Read one order by ID (for example ORD-1001). Returns status, total and shipping date."""
    order = db.get_order(_conn, order_id)
    db.log_call(_conn, "mcp-client", "get_order", {"order_id": order_id}, "found" if order else "not_found")
    return order if order else {"error": f"order {order_id} not found"}


@mcp.tool()
def list_open_tickets(order_id: str = "") -> list[dict]:
    """List open support tickets. Pass order_id to filter, or leave empty for all open tickets."""
    rows = db.list_open_tickets(_conn, order_id or None)
    db.log_call(_conn, "mcp-client", "list_open_tickets", {"order_id": order_id}, f"{len(rows)} rows")
    return rows


@mcp.tool()
def create_crm_task(customer: str, note: str) -> dict:
    """WRITE ACTION: create a follow-up task for a customer in the CRM. Requires human approval in the agent."""
    task_id = db.create_crm_task(_conn, customer, note)
    db.log_call(_conn, "mcp-client", "create_crm_task", {"customer": customer}, f"task {task_id}")
    return {"task_id": task_id, "customer": customer}


if __name__ == "__main__":
    mcp.run()
