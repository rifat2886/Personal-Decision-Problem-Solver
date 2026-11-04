#!/usr/bin/env python3
"""Postgres-mode tests for the C++ server (Route 2, Phase 1).

Runs the C++ server with DATABASE_URL pointing at a TEST database
only (never a production database), then checks, over HTTP:
  - /api/health storage=postgres, /api/info storage=postgres
  - register/login (first user ADMIN, second USER), wrong password 401
  - task/decision/transaction/savings/habit CRUD
  - per-user isolation: Bob cannot see Alice's task, PATCH/DELETE 404
  - legacy record visibility: sole-user sees legacy, hidden with 2 users
  - backup/restore, export txt+csv, daily-summary, error-log (empty)
  - CORS: allowed origin gets Access-Control-Allow-Origin + OPTIONS 204,
    disallowed origin gets no CORS header on API responses
  - 401 sweep: protected endpoints without a token return 401
  - fail-fast: a bad DATABASE_URL makes the server exit, not serve txt

The test database is created fresh by the caller: pass
--database-url postgres://... (a test database you control).
The test drops and recreates the pdps tables first, so it must
NEVER be pointed at a database holding real data.

Usage:
    python3 tests/pg_test.py --server-cmd ./cpp_server --port 8190 \
        --database-url postgres://postgres@localhost:5432/pdps_test
    # The test server must be built with libpq (make cpp_server on
    # a machine with libpq-dev, or the Dockerfile build).
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))


def req(port, method, path, token=None, body=None, headers=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-cmd", default="./cpp_server")
    ap.add_argument("--port", type=int, default=8190)
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--cors-origin", default="https://example.vercel.app")
    args = ap.parse_args()

    # Fresh schema: drop tables (test database only).
    import psycopg2
    conn = psycopg2.connect(args.database_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        for t in ("daily_reports", "error_logs", "habit_log", "savings_goals",
                  "transactions", "tasks", "decisions_backup", "decisions", "users"):
            cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    conn.close()

    env = dict(os.environ)
    env["DATABASE_URL"] = args.database_url
    env["CORS_ORIGINS"] = args.cors_origin
    proc = subprocess.Popen([args.server_cmd, "--port", str(args.port)],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(100):
            time.sleep(0.2)
            try:
                s, _, _ = req(args.port, "GET", "/api/health")
                if s == 200:
                    break
            except Exception:
                pass
        else:
            check("server starts in postgres mode", False, "no /api/health in 20s")
            return 1

        s, b, _ = req(args.port, "GET", "/api/health")
        check("health storage=postgres", s == 200 and json.loads(b).get("storage") == "postgres", b)
        s, b, _ = req(args.port, "GET", "/api/info")
        check("info unauthenticated is 401 (health is the public check)", s == 401, b)

        # Register Alice (first = ADMIN), Bob (USER)
        s, b, _ = req(args.port, "POST", "/api/register", body={"username": "alice", "password": "Alice1234"})
        check("register alice", s == 201 and json.loads(b).get("role") == "ADMIN", b)
        s, b, _ = req(args.port, "POST", "/api/register", body={"username": "bob", "password": "Bob12345"})
        check("register bob", s == 201 and json.loads(b).get("role") == "USER", b)
        s, b, _ = req(args.port, "POST", "/api/login", body={"username": "alice", "password": "wrongpass1"})
        check("wrong password 401", s == 401, b)
        s, b, _ = req(args.port, "POST", "/api/login", body={"username": "alice", "password": "Alice1234"})
        tok_a = json.loads(b).get("token") if s == 200 else None
        check("login alice", s == 200 and bool(tok_a), b)
        s, b, _ = req(args.port, "POST", "/api/login", body={"username": "bob", "password": "Bob12345"})
        tok_b = json.loads(b).get("token") if s == 200 else None
        check("login bob", s == 200 and bool(tok_b), b)
        s, b, _ = req(args.port, "GET", "/api/me", token=tok_a)
        check("me alice", s == 200 and json.loads(b).get("username") == "alice", b)
        s, b, _ = req(args.port, "GET", "/api/info", token=tok_a)
        check("info storage=postgres", s == 200 and json.loads(b).get("storage") == "postgres", b)

        # Alice task, decision, transaction, savings, habit
        s, b, _ = req(args.port, "POST", "/api/tasks", token=tok_a,
                      body={"title": "AliceSecretTask", "urgency": 8, "importance": 9, "deadline": "2026-11-20"})
        task_id = json.loads(b).get("id") if s == 201 else None
        check("alice task create", s == 201 and bool(task_id), b)
        s, b, _ = req(args.port, "POST", "/api/decisions", token=tok_a,
                      body={"type": "Daily", "priority": 42, "title": "AliceDecision"})
        check("alice decision create", s == 201, b)
        s, b, _ = req(args.port, "POST", "/api/transactions", token=tok_a,
                      body={"date": "2026-11-05", "type": "income", "category": "Salary", "amount": 5000, "note": "Nov"})
        check("alice transaction create", s == 201, b)
        s, b, _ = req(args.port, "POST", "/api/savings", token=tok_a, body={"name": "Trip", "target": 10000})
        check("alice savings create", s == 201, b)
        s, b, _ = req(args.port, "POST", "/api/habits", token=tok_a, body={"habit": "Reading", "date": "2026-11-05"})
        check("alice habit mark", s == 201, b)

        # Per-user isolation
        s, b, _ = req(args.port, "GET", "/api/tasks", token=tok_b)
        check("bob cannot see alice task", s == 200 and "AliceSecretTask" not in b, b)
        s, b, _ = req(args.port, "PATCH", "/api/tasks/" + str(task_id), token=tok_b, body={"status": "Completed"})
        check("bob patch alice task 404", s == 404, b)
        s, b, _ = req(args.port, "DELETE", "/api/tasks/" + str(task_id), token=tok_b)
        check("bob delete alice task 404", s == 404, b)
        s, b, _ = req(args.port, "GET", "/api/tasks", token=tok_a)
        check("alice still sees her task", s == 200 and "AliceSecretTask" in b, b)
        s, b, _ = req(args.port, "GET", "/api/decisions", token=tok_b)
        check("bob cannot see alice decision", s == 200 and "AliceDecision" not in b, b)
        s, b, _ = req(args.port, "GET", "/api/transactions", token=tok_b)
        check("bob cannot see alice transaction", s == 200 and "Salary" not in b, b)

        # Backup / restore / export / daily-summary
        s, b, _ = req(args.port, "POST", "/api/backup", token=tok_a, body={})
        check("backup", s == 200 and json.loads(b).get("backedUp") == 1, b)
        s, b, _ = req(args.port, "POST", "/api/decisions", token=tok_a,
                      body={"type": "Daily", "priority": 10, "title": "TempDecision"})
        s, b, _ = req(args.port, "POST", "/api/restore", token=tok_a, body={})
        check("restore", s == 200 and json.loads(b).get("restored") == 1, b)
        s, b, _ = req(args.port, "GET", "/api/decisions", token=tok_a)
        check("after restore only backed-up decision", s == 200 and "AliceDecision" in b and "TempDecision" not in b, b)
        s, b, _ = req(args.port, "GET", "/api/export?format=txt", token=tok_a)
        check("export txt", s == 200 and "Salary" in b, b)
        s, b, _ = req(args.port, "GET", "/api/export?format=csv", token=tok_a)
        check("export csv", s == 200 and "Salary" in b, b)
        s, b, _ = req(args.port, "POST", "/api/daily-summary", token=tok_a,
                      body={"income": 5000, "expenses": 1000, "habitsCompleted": 1, "habitsPlanned": 2})
        check("daily-summary", s == 200, b)
        s, b, _ = req(args.port, "GET", "/api/error-log", token=tok_a)
        check("error-log empty list", s == 200 and b.strip() == "[]", b)

        # CORS
        s, b, h = req(args.port, "GET", "/api/me", token=tok_a, headers={"Origin": args.cors_origin})
        aca = h.get("Access-Control-Allow-Origin") or h.get("access-control-allow-origin")
        check("cors allowed origin header", s == 200 and aca == args.cors_origin, str(h))
        s, b, h = req(args.port, "OPTIONS", "/api/me", headers={"Origin": args.cors_origin, "Access-Control-Request-Method": "GET"})
        check("cors preflight 204", s == 204, str(s))
        s, b, h = req(args.port, "GET", "/api/me", token=tok_a, headers={"Origin": "https://evil.example"})
        aca = h.get("Access-Control-Allow-Origin") or h.get("access-control-allow-origin")
        check("cors disallowed origin no header", s == 200 and not aca, str(h))

        # 401 sweep
        for path in ("/api/overview", "/api/tasks", "/api/decisions", "/api/transactions",
                     "/api/savings", "/api/habits", "/api/reports?month=2026-11", "/api/users"):
            s, _, _ = req(args.port, "GET", path)
            check(f"401 without token {path}", s == 401, str(s))

        # Legacy: insert a NULL-owner decision directly in SQL, check visibility.
        # With 2 users it must be hidden from both; after deleting bob it is
        # visible to sole user alice (mirrors txt legacy rule).
        conn2 = psycopg2.connect(args.database_url)
        conn2.autocommit = True
        with conn2.cursor() as cur:
            cur.execute("INSERT INTO decisions (record_date, type, priority, title, owner) VALUES ('2026-11-01','Daily',5,'LegacyDecision',NULL)")
        conn2.close()
        s, b, _ = req(args.port, "GET", "/api/decisions", token=tok_a)
        check("legacy hidden with 2 users", s == 200 and "LegacyDecision" not in b, b)
        # Delete bob directly in SQL (test-only), then legacy must appear for alice.
        conn3 = psycopg2.connect(args.database_url)
        conn3.autocommit = True
        with conn3.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username='bob'")
        conn3.close()
        s, b, _ = req(args.port, "GET", "/api/decisions", token=tok_a)
        check("legacy visible to sole user", s == 200 and "LegacyDecision" in b, b)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # Fail-fast: bad DATABASE_URL must exit, not serve txt.
    bad_env = dict(os.environ)
    bad_env["DATABASE_URL"] = "postgres://127.0.0.1:1/nonexistent"
    bad = subprocess.run([args.server_cmd, "--port", str(args.port + 1)],
                         env=bad_env, capture_output=True, text=True, timeout=20)
    check("fail-fast on bad DATABASE_URL", bad.returncode != 0, f"rc={bad.returncode}")

    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} pg checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
