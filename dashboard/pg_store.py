"""pg_store.py — PostgreSQL compatibility reader for the PDPS schema.

Route 2, Phase 1. This module does NOT change the Python server:
the Python server stays txt-only (see dashboard/server.py). This
module exists so that:

1. The migration tool (tools/migrate_txt_to_pg.py) and the
   compatibility test (tests/pg_test.py) can read Postgres tables
   with the same field names, owner rules, and legacy semantics
   as the txt files and the C++ server.
2. A future Python Postgres mode, if it is ever built, has a
   single, tested place to start from, instead of duplicating
   SQL in server.py.

It requires psycopg2 (or psycopg) to be installed. Without it,
importing this module succeeds, but connecting raises a clear
ImportError — txt mode never imports it, so local txt use keeps
working with only the standard library.

Legacy rule (identical to txt mode and the C++ server): a record
whose owner is NULL is visible only when the users table has
exactly one user and that user is the requester. ADMIN does NOT
see other users' records.
"""

import os


def _driver():
    try:
        import psycopg2
        return psycopg2
    except ImportError:
        try:
            import psycopg
            return psycopg
        except ImportError as exc:
            raise ImportError(
                "PostgreSQL driver not installed. Install psycopg2 "
                "(pip install psycopg2-binary) to use Postgres tools."
            ) from exc


def connect(conninfo=None):
    """Connect from DATABASE_URL (or the given string). Never logs it."""
    driver = _driver()
    url = conninfo or os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL is not set.")
    return driver.connect(url)


def load_users(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT username, password_hash, role FROM users ORDER BY username")
        return {u: {"password": p, "role": r} for u, p, r in cur.fetchall()}


def owner_visible(owner, user, users):
    if owner == user:
        return True
    if owner:
        return False
    return len(users) == 1 and user in users


def _rows(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def load_decisions(conn):
    out = []
    for r in _rows(conn, "SELECT id, record_date, type, priority, title, owner FROM decisions ORDER BY id"):
        out.append({"id": str(r["id"]), "date": r["record_date"], "type": r["type"],
                    "priority": int(r["priority"]), "title": r["title"],
                    "owner": r["owner"] or ""})
    return out


def load_tasks(conn):
    out = []
    for r in _rows(conn, "SELECT id, title, urgency, importance, deadline, status, owner FROM tasks ORDER BY id"):
        out.append({"id": str(r["id"]), "title": r["title"],
                    "urgency": int(r["urgency"]), "importance": int(r["importance"]),
                    "deadline": r["deadline"], "status": r["status"],
                    "owner": r["owner"] or ""})
    out.sort(key=lambda t: (-(t["urgency"] * 2 + t["importance"] * 3), t["id"]))
    return out


def load_transactions(conn):
    out = []
    for r in _rows(conn, "SELECT tx_date, type, category, amount, note, owner FROM transactions ORDER BY id"):
        out.append({"date": r["tx_date"], "type": r["type"], "category": r["category"],
                    "amount": float(r["amount"]), "note": r["note"],
                    "owner": r["owner"] or ""})
    return out


def load_savings(conn):
    out = []
    for r in _rows(conn, "SELECT name, target, saved, owner FROM savings_goals ORDER BY id"):
        out.append({"name": r["name"], "target": float(r["target"]),
                    "saved": float(r["saved"]), "owner": r["owner"] or ""})
    return out


def load_habits(conn):
    out = {}
    for r in _rows(conn, "SELECT habit, log_date, owner FROM habit_log ORDER BY id"):
        out.setdefault(r["habit"], []).append({"date": r["log_date"], "owner": r["owner"] or ""})
    return out
