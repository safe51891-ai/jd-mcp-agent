import sqlite3

import pytest

from agent.graph import rule_based_planner, run_agent
from server import db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


def test_db_seeded_and_reads(conn):
    assert db.get_order(conn, "ORD-1001")["customer"] == "Acme Ltd"
    assert db.get_order(conn, "ORD-9999") is None
    open_tickets = db.list_open_tickets(conn, "ORD-1002")
    assert [t["id"] for t in open_tickets] == ["TCK-1"]


def test_read_only_request_runs_without_approval(conn):
    state = run_agent("What is the status of ORD-1001 and any open tickets?", conn)
    tools_run = [r["tool"] for r in state["results"]]
    assert tools_run == ["get_order", "list_open_tickets"]
    assert state["pending_write"] is None
    assert "shipped" in state["answer"]


def test_write_is_blocked_without_approval(conn):
    state = run_agent("Create a follow-up task for Acme Ltd about ORD-1001", conn, approved=False)
    assert state["pending_write"]["tool"] == "create_crm_task"
    assert all(r["tool"] != "create_crm_task" for r in state["results"])
    assert "needs approval" in " ".join(state["trace"])
    # nothing written to the CRM table
    assert conn.execute("SELECT COUNT(*) FROM crm_tasks").fetchone()[0] == 0


def test_write_executes_when_approved(conn):
    state = run_agent("Create a follow-up task for Acme Ltd about ORD-1001", conn, approved=True)
    assert state["pending_write"] is None
    assert conn.execute("SELECT COUNT(*) FROM crm_tasks").fetchone()[0] == 1


def test_step_limit_stops_a_looping_planner(conn):
    def looping_planner(request, results):
        return [{"tool": "get_order", "args": {"order_id": "ORD-1001"}}]

    state = run_agent("loop", conn, max_steps=3, planner=looping_planner)
    assert state["steps"] <= 4
    assert any("step limit" in t for t in state["trace"])


def test_unknown_tool_is_rejected(conn):
    def bad_planner(request, results):
        return [{"tool": "drop_table", "args": {}}] if not results else []

    state = run_agent("x", conn, planner=bad_planner)
    assert any("reject unknown tool drop_table" in t for t in state["trace"])
    assert state["results"] == []


def test_rule_based_planner_extracts_orders_and_tasks():
    plan = rule_based_planner("Check ORD-1002 tickets and create a follow-up task for Bluebird Co.")
    names = [p["tool"] for p in plan]
    assert names == ["get_order", "list_open_tickets", "create_crm_task"]
