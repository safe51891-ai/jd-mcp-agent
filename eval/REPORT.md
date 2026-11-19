# MCP Agent: Evaluation Report

## Planner (offline, rule-based)
15 labeled support requests. Exact match on tool sequence: **100%** (15/15).
Caveat: I wrote the rule patterns with these phrasings in view, so this is an optimistic number. Real requests will be phrased differently. Measure on a sample of real support requests before trusting it.

## Security checks (all pass)
- Injected instructions inside ticket text did not cause a CRM write.
- A planner that always asks for a write cannot write without approval (0 writes executed).
- The MCP client, talking to the server over stdio, can list and call the tools; each call is audited.

## Audit trail
Every tool call, from the agent or from an MCP client, is recorded with actor, tool, arguments, and outcome. Approved writes are recorded with the actor `agent-approved`.

## Not measured here
- The LLM planner. It needs an `ANTHROPIC_API_KEY`. Its risk is different: tool results go back into its prompt, so a malicious ticket can try to steer the plan. The approval gate is what stops a write, not the planner.
- Real latency and token cost per run. These need live calls.
