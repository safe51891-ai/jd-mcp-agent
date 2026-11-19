"""LangGraph multi-step agent over the business tools.

Flow:  plan -> (act | approve | finish) -> plan ...
- plan:    choose the next tool call (LLM if ANTHROPIC_API_KEY is set, otherwise a rule-based planner)
- act:     run a read-only tool and record the result
- approve: write actions are NOT executed; they wait for human approval (state.approved)
- Guards:  max_steps limit, write-permission gate, full trace of every decision
"""
import json
import os
import re
from typing import Any, Callable, TypedDict

from langgraph.graph import END, StateGraph

from server import db

WRITE_TOOLS = {"create_crm_task"}
MAX_STEPS_DEFAULT = 5


class AgentState(TypedDict, total=False):
    request: str
    customer: str
    plan_queue: list[dict]         # tool calls the planner wants to run, in order
    results: list[dict]
    pending_write: dict | None     # write action waiting for approval
    approved: bool
    steps: int
    max_steps: int
    trace: list[str]
    answer: str


_conn = None  # set by build_graph so audit writes go to the same database


def make_tools(conn) -> dict[str, Callable[..., Any]]:
    return {
        "get_order": lambda **kw: db.get_order(conn, kw["order_id"]),
        "list_open_tickets": lambda **kw: db.list_open_tickets(conn, kw.get("order_id")),
        "create_crm_task": lambda **kw: {"task_id": db.create_crm_task(conn, kw["customer"], kw["note"])},
    }


# ---------- planners ----------

def rule_based_planner(request: str) -> list[dict]:
    """Offline fallback: looks for order IDs and keywords. Deterministic, so it is testable."""
    plan: list[dict] = []
    order_ids = re.findall(r"ORD-\d+", request, flags=re.IGNORECASE)
    for oid in order_ids:
        plan.append({"tool": "get_order", "args": {"order_id": oid.upper()}})
        if re.search(r"ticket|issue|complain", request, flags=re.IGNORECASE):
            plan.append({"tool": "list_open_tickets", "args": {"order_id": oid.upper()}})
    if re.search(r"follow.?up|task|remind", request, flags=re.IGNORECASE):
        customer_match = re.search(r"for ([A-Z][\w ]+?)(?:[.,]|$)", request)
        customer = customer_match.group(1).strip() if customer_match else "unknown"
        plan.append({"tool": "create_crm_task", "args": {"customer": customer, "note": request}})
    return plan


def llm_planner(request: str, results: list[dict]) -> list[dict]:
    """Calls Claude to plan tool calls as JSON. Only used when ANTHROPIC_API_KEY is set."""
    import anthropic  # imported lazily so tests run without the SDK key

    client = anthropic.Anthropic()
    prompt = (
        "You can call these tools: get_order(order_id), list_open_tickets(order_id), "
        "create_crm_task(customer, note). Given the request and results so far, return a JSON list "
        'of the next tool calls, e.g. [{"tool": "get_order", "args": {"order_id": "ORD-1001"}}]. '
        "Return [] when the task is complete.\n"
        f"Request: {request}\nResults so far: {json.dumps(results, default=str)}"
    )
    msg = client.messages.create(
        model=os.getenv("AGENT_MODEL", "claude-haiku-5-5"),
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text
    match = re.search(r"\[.*\]", text, flags=re.DOTALL)
    return json.loads(match.group(0)) if match else []


# ---------- graph nodes ----------

def build_graph(conn, planner: Callable | None = None):
    global _conn
    _conn = conn
    tools = make_tools(conn)
    if planner is None:
        planner = llm_planner if os.getenv("ANTHROPIC_API_KEY") else (
            lambda request, results: rule_based_planner(request) if not results else []
        )

    def plan(state: AgentState) -> AgentState:
        steps = state.get("steps", 0) + 1
        trace = state.get("trace", []) + [f"plan (step {steps})"]
        if steps > state.get("max_steps", MAX_STEPS_DEFAULT):
            return {"steps": steps, "trace": trace + ["stop: step limit reached"], "plan_queue": []}
        queue = state.get("plan_queue") or planner(state["request"], state.get("results", []))
        return {"steps": steps, "plan_queue": queue, "trace": trace}

    def act(state: AgentState) -> AgentState:
        call, *rest = state["plan_queue"]
        name, args = call["tool"], call.get("args", {})
        if name not in tools:
            return {"plan_queue": rest, "trace": state["trace"] + [f"reject unknown tool {name}"]}
        result = tools[name](**args)
        db.log_call(_conn, "agent", name, args, "ok")
        return {
            "plan_queue": rest,
            "results": state.get("results", []) + [{"tool": name, "args": args, "result": result}],
            "trace": state["trace"] + [f"ran {name}"],
        }

    def approve(state: AgentState) -> AgentState:
        call, *rest = state["plan_queue"]
        if not state.get("approved"):
            return {
                "plan_queue": rest,
                "pending_write": call,
                "trace": state["trace"] + [f"blocked write {call['tool']}: needs approval"],
            }
        result = tools[call["tool"]](**call["args"])
        db.log_call(_conn, "agent-approved", call["tool"], call["args"], "ok")
        return {
            "plan_queue": rest,
            "results": state.get("results", []) + [{"tool": call["tool"], "args": call["args"], "result": result}],
            "trace": state["trace"] + [f"executed approved write {call['tool']}"],
        }

    def finish(state: AgentState) -> AgentState:
        summary = [f"{r['tool']}: {r['result']}" for r in state.get("results", [])]
        answer = "\n".join(summary) if summary else "No results."
        if state.get("pending_write"):
            answer += f"\nPending approval: {state['pending_write']['tool']} {state['pending_write']['args']}"
        return {"answer": answer, "trace": state["trace"] + ["finish"]}

    def route(state: AgentState) -> str:
        if state.get("steps", 0) > state.get("max_steps", MAX_STEPS_DEFAULT) or not state.get("plan_queue"):
            return "finish"  # planner returned nothing new, or the step limit was hit
        return "approve" if state["plan_queue"][0]["tool"] in WRITE_TOOLS else "act"

    g = StateGraph(AgentState)
    g.add_node("plan", plan)
    g.add_node("act", act)
    g.add_node("approve", approve)
    g.add_node("finish", finish)
    g.set_entry_point("plan")
    g.add_conditional_edges("plan", route, {"act": "act", "approve": "approve", "finish": "finish"})
    # after every tool step, go back to the planner so it can decide the next step (or stop)
    g.add_edge("act", "plan")
    g.add_edge("approve", "plan")
    g.add_edge("finish", END)
    return g.compile()


def run_agent(request: str, conn, approved: bool = False, max_steps: int = MAX_STEPS_DEFAULT,
              planner: Callable | None = None) -> AgentState:
    graph = build_graph(conn, planner=planner)
    return graph.invoke({
        "request": request,
        "approved": approved,
        "max_steps": max_steps,
        "steps": 0,
        "results": [],
        "plan_queue": [],
        "pending_write": None,
        "trace": [],
    })
