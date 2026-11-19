"""SQLite-backed business data. Every tool in the MCP server and the agent reads/writes through here."""
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "business.db"


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            customer TEXT NOT NULL,
            status TEXT NOT NULL,
            total_usd REAL NOT NULL,
            shipped_on TEXT
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            order_id TEXT,
            subject TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL DEFAULT (datetime('now')),
            actor TEXT NOT NULL,
            tool TEXT NOT NULL,
            args TEXT NOT NULL,
            outcome TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS crm_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            note TEXT NOT NULL
        );
        """
    )
    if conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO orders VALUES (?,?,?,?,?)",
            [
                ("ORD-1001", "Acme Ltd", "shipped", 1200.0, "2026-11-10"),
                ("ORD-1002", "Bluebird Co", "processing", 350.5, None),
                ("ORD-1003", "Cedar Labs", "delivered", 89.0, "2026-11-01"),
            ],
        )
        conn.executemany(
            "INSERT INTO tickets VALUES (?,?,?,?)",
            [
                ("TCK-1", "ORD-1002", "Delivery delayed", "open"),
                ("TCK-2", "ORD-1001", "Damaged box", "open"),
                ("TCK-3", "ORD-1003", "Invoice question", "closed"),
            ],
        )
        conn.commit()
    return conn


def get_order(conn: sqlite3.Connection, order_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return dict(row) if row else None


def list_open_tickets(conn: sqlite3.Connection, order_id: str | None = None) -> list[dict]:
    if order_id:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE status = 'open' AND order_id = ?", (order_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tickets WHERE status = 'open'").fetchall()
    return [dict(r) for r in rows]


def create_crm_task(conn: sqlite3.Connection, customer: str, note: str) -> int:
    cur = conn.execute("INSERT INTO crm_tasks (customer, note) VALUES (?, ?)", (customer, note))
    conn.commit()
    return cur.lastrowid


def log_call(conn: sqlite3.Connection, actor: str, tool: str, args: dict, outcome: str) -> None:
    import json

    conn.execute(
        "INSERT INTO audit_log (actor, tool, args, outcome) VALUES (?, ?, ?, ?)",
        (actor, tool, json.dumps(args, default=str), outcome),
    )
    conn.commit()
