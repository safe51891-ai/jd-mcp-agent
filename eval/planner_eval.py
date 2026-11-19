"""Labeled evaluation of the offline planner. Run: python -m eval.planner_eval

Measures whether the planner picks the right tools in the right order, on requests a support team actually sends.
The LLM planner is not measured here: it needs an API key.
"""
from agent.graph import rule_based_planner

CASES = [
    ("Status of ORD-1001?", ["get_order"]),
    ("Show me ORD-1002 and its open tickets", ["get_order", "list_open_tickets"]),
    ("Any tickets for ORD-1003?", ["get_order", "list_open_tickets"]),
    ("Is order ORD-1001 shipped yet?", ["get_order"]),
    ("Create a follow-up task for Acme Ltd about ORD-1001", ["get_order", "create_crm_task"]),
    ("Remind the team to follow up with Bluebird Co on ORD-1002", ["get_order", "create_crm_task"]),
    ("Customer complaint on ORD-1001, open a task for Acme Ltd", ["get_order", "list_open_tickets", "create_crm_task"]),
    ("What is the total for ORD-1003", ["get_order"]),
    ("Check ORD-1002 and ORD-1003", ["get_order", "get_order"]),
    ("Who won the game last night?", []),
    ("Please tell me a joke about invoices", []),
    ("Summarize the policy for refunds", []),
    ("Does ORD-1001 have any issue?", ["get_order", "list_open_tickets"]),
    ("Remind me to call Cedar Labs about ORD-1003", ["get_order", "create_crm_task"]),
    ("Open tickets, please", []),  # ambiguous: no order ID, planner should not guess
]


def evaluate() -> dict:
    exact = 0
    misses = []
    for request, expected in CASES:
        got = [c["tool"] for c in rule_based_planner(request)]
        if got == expected:
            exact += 1
        else:
            misses.append({"request": request, "expected": expected, "got": got})
    return {"cases": len(CASES), "exact_match": round(exact / len(CASES), 3), "misses": misses}


if __name__ == "__main__":
    import json
    print(json.dumps(evaluate(), indent=2))
