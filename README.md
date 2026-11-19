# MCP Tool Server + LangGraph Agent

A Model Context Protocol (MCP) server that exposes business tools (orders, support tickets, CRM tasks) to any MCP client, plus a LangGraph agent that plans multi-step tasks over the same tools.

## What it demonstrates
- **MCP server** (`server/mcp_server.py`) built with FastMCP: typed tools with docstrings that the model reads.
- **Write-action gate**: `create_crm_task` is a write. The agent never runs it without `approved=True`; it reports the pending action instead.
- **LangGraph state machine** (`agent/graph.py`): plan -> act/approve -> plan, with a step limit and a full trace of every decision.
- **Pluggable planner**: a deterministic rule-based planner for offline use and tests, or Claude (set `ANTHROPIC_API_KEY`) for real planning.
- **Tests** (`tests/`): permissions, step limits, unknown-tool rejection, and tool registration.

## Measured (eval/REPORT.md)
- Planner exact match on 15 labeled requests: 100% (optimistic: the rules were written with these phrasings in view).
- Injection: instructions hidden in ticket text caused no write. A planner that always requests a write executed zero writes without approval.
- Every tool call, from the agent or an MCP client, is recorded in an audit log.

## Run it
```bash
pip install -r requirements.txt
pytest -q                                   # runs offline, no API key needed

# Agent demo (offline planner)
python -c "from agent.graph import run_agent; from server.db import connect; \
s = run_agent('Check ORD-1002 tickets and create a follow-up task for Bluebird Co.', connect()); \
print(s['answer']); print(s['trace'])"

# Start the MCP server (for Claude Desktop / Claude Code)
python -m server.mcp_server
```

To use with Claude Code, add to your MCP config:
```json
{ "mcpServers": { "business-tools": { "command": "python", "args": ["-m", "server.mcp_server"], "cwd": "/path/to/jd-mcp-agent" } } }
```

## Design notes
- The agent calls the same database functions as the MCP server. It does not go through MCP. Routing the agent through an MCP client is a natural next step.
- Write tools are gated in the agent, but the MCP server itself does not gate writes. Add an approval step or a scoped API token before exposing it outside your machine.
- The step limit caps cost and prevents loops. Token use would be logged per call in a production version.
