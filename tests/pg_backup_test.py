#!/usr/bin/env python3
"""Postgres-mode per-user backup/restore test (public-launch redesign).

Same Alice/Bob scenario as tests/backup_test.py, but against the
C++ server in Postgres mode, plus a direct table check: after Bob's
backup, decisions_backup must still hold Alice's row (the old code
did DELETE FROM decisions_backup with no WHERE clause).

Usage:
    python3 tests/pg_backup_test.py --server-cmd ./cpp_server --port 8191 \
        --database-url <your-TEST-database-url-only>
    # TEST database only. The test drops and recreates the tables.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def req(port, method, path, token=None, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read() or b"{}"
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def register_login(port, username, password):
    s, b = req(port, "POST", "/api/register",
               body={"username": username, "password": password})
    assert s in (200, 201), (username, b)
    s, b = req(port, "POST", "/api/login",
               body={"username": username, "password": password})
    assert s == 200, (username, b)
    return b["token"]


def titles(port, token):
    s, b = req(port, "GET", "/api/decisions", token=token)
    assert s == 200, b
    rows = b if isinstance(b, list) else b.get("decisions", [])
    return [d.get("title") for d in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-cmd", default="./cpp_server")
    ap.add_argument("--port", type=int, default=8191)
    ap.add_argument("--database-url", required=True)
    args = ap.parse_args()

    import psycopg2
    conn = psycopg2.connect(args.database_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        for t in ("daily_reports", "error_logs", "habit_log", "savings_goals",
                  "transactions", "tasks", "decisions_backup", "decisions", "users"):
            cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    conn.close()

    env = dict(os.environ, DATABASE_URL=args.database_url)
    proc = subprocess.Popen(args.server_cmd.split() + ["--port", str(args.port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env=env)
    try:
        for _ in range(50):
            s, _ = req(args.port, "GET", "/api/health")
            if s != 0:
                break
            time.sleep(0.2)
        alice = register_login(args.port, "alice", "Alice12345")
        bob = register_login(args.port, "bob", "Bob12345")
        for tok, title in ((alice, "AliceDecision"), (bob, "BobDecision")):
            s, b = req(args.port, "POST", "/api/decisions", token=tok,
                       body={"date": "2026-11-05", "type": "Daily",
                             "priority": 5, "title": title})
            assert s in (200, 201), b
        s, b = req(args.port, "POST", "/api/backup", token=alice, body={})
        check("pg alice backup", s == 200 and b.get("backedUp") == 1, str(b))
        s, b = req(args.port, "POST", "/api/backup", token=bob, body={})
        check("pg bob backup after alice", s == 200 and b.get("backedUp") == 1, str(b))
        conn = psycopg2.connect(args.database_url)
        with conn.cursor() as cur:
            cur.execute("SELECT owner, title FROM decisions_backup ORDER BY owner")
            rows = cur.fetchall()
        conn.close()
        check("pg both backups survive in table",
              ("alice", "AliceDecision") in rows and ("bob", "BobDecision") in rows,
              str(rows))
        for tok, title in ((alice, "AliceTemp"), (bob, "BobTemp")):
            req(args.port, "POST", "/api/decisions", token=tok,
                body={"date": "2026-11-05", "type": "Daily",
                      "priority": 5, "title": title})
        s, b = req(args.port, "POST", "/api/restore", token=alice,
                   body={"confirm": True})
        check("pg alice restore", s == 200 and b.get("restored") == 1, str(b))
        check("pg alice only her decision",
              titles(args.port, alice) == ["AliceDecision"], str(titles(args.port, alice)))
        check("pg bob untouched by alice restore",
              "BobDecision" in titles(args.port, bob) and "BobTemp" in titles(args.port, bob),
              str(titles(args.port, bob)))
        s, b = req(args.port, "POST", "/api/restore", token=alice, body={})
        check("pg restore without confirm rejected", s == 400, str(b))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    print(f"pg_backup_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
