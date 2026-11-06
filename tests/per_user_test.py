#!/usr/bin/env python3
"""Two-user per-user isolation test (Issue 2) for the dashboard server.

Alice and Bob each create a decision, a task, a transaction, a savings
goal and a habit. Each must see only their own records, must get 404
when trying to PATCH/DELETE the other's task/decision, and ADMIN
(Alice, first user) must NOT see Bob's records via any personal-data
endpoint (ADMIN list is username/role only, by design).

Also tests legacy migration:
- Single-user legacy: an old-format record (no owner) is visible to
  the sole user, and is preserved on disk (never deleted).
- Multi-user legacy: the same old-format record becomes hidden from
  both users once a second user exists, and is still on disk.

Usage:
    python3 tests/per_user_test.py --server-cmd "./cpp_server" --port 8180
    python3 tests/per_user_test.py --server-cmd "python3 dashboard/server.py" --port 8181
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
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
        with urllib.request.urlopen(r, timeout=10) as resp:
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


def login(port, username, password):
    status, body = req(port, "POST", "/api/login",
                       body={"username": username, "password": password})
    assert status == 200, (username, body)
    return body["token"]


def register(port, username, password):
    status, body = req(port, "POST", "/api/register",
                       body={"username": username, "password": password})
    assert status in (200, 201), (username, body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-cmd", required=True)
    ap.add_argument("--port", type=int, default=8180)
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="pdps-per-user-")
    print(f"data dir: {tmp}")
    # Legacy record, written BEFORE any server start, in old format
    # (no owner field). Backed up first, per the implementation rules.
    with open(os.path.join(tmp, "decisions.txt"), "w") as f:
        f.write("900|2026-11-01|Daily|50|LegacyDecision\n")
    shutil.copy(os.path.join(tmp, "decisions.txt"),
                os.path.join(tmp, "decisions.txt.pre-migration-backup"))
    cmd = args.server_cmd.split() + ["--port", str(args.port),
                                     "--data-dir", tmp]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        port = args.port
        for _ in range(30):
            status, _ = req(port, "GET", "/")
            if status != 0:
                break
            time.sleep(0.5)
        else:
            print("FAIL server did not start")
            return 1

        # Single-user legacy: Alice registers first (ADMIN), legacy
        # record must be visible to her (sole user) and preserved.
        register(port, "alice", "AlicePass123")
        tok_a = login(port, "alice", "AlicePass123")
        status, body = req(port, "GET", "/api/decisions", token=tok_a)
        check("single-user legacy visible to sole user",
              status == 200 and any("LegacyDecision" in str(d) for d in body), str(body)[:200])

        # Alice creates her own data.
        status, body = req(port, "POST", "/api/tasks", token=tok_a,
                           body={"title": "AliceTask", "urgency": 8, "importance": 8,
                                 "deadline": "2026-11-20"})
        task_a = body.get("id")
        check("alice task create", status in (200, 201) and task_a, str(body))
        status, body = req(port, "POST", "/api/transactions", token=tok_a,
                           body={"type": "income", "category": "Salary", "amount": 5000,
                                 "note": "AlicePay", "date": "2026-11-01"})
        check("alice transaction create", status in (200, 201), str(body))
        status, body = req(port, "POST", "/api/savings", token=tok_a,
                           body={"name": "AliceGoal", "target": 1000})
        check("alice savings create", status in (200, 201), str(body))
        status, body = req(port, "POST", "/api/habits", token=tok_a,
                           body={"habit": "AliceHabit", "date": "2026-11-03"})
        check("alice habit create", status in (200, 201), str(body))
        status, body = req(port, "POST", "/api/decisions", token=tok_a,
                           body={"type": "Daily", "priority": 40, "title": "AliceDecision"})
        dec_a = body.get("id")
        check("alice decision create", status in (200, 201) and dec_a, str(body))

        # Bob registers; legacy must now be hidden from BOTH users.
        register(port, "bob", "BobPass123")
        tok_b = login(port, "bob", "BobPass123")
        status, body = req(port, "GET", "/api/decisions", token=tok_b)
        check("multi-user legacy hidden from bob",
              status == 200 and not any("LegacyDecision" in str(d) for d in body), str(body)[:200])
        status, body = req(port, "GET", "/api/decisions", token=tok_a)
        check("multi-user legacy hidden from alice too",
              status == 200 and not any("LegacyDecision" in str(d) for d in body), str(body)[:200])
        with open(os.path.join(tmp, "decisions.txt")) as f:
            raw = f.read()
        check("legacy record preserved on disk",
              "LegacyDecision" in raw, raw[:200])
        check("pre-migration backup exists",
              os.path.exists(os.path.join(tmp, "decisions.txt.pre-migration-backup")))

        # Bob creates his own data, including same savings name.
        status, body = req(port, "POST", "/api/tasks", token=tok_b,
                           body={"title": "BobTask", "urgency": 7, "importance": 7,
                                 "deadline": "2026-11-21"})
        task_b = body.get("id")
        check("bob task create", status in (200, 201) and task_b, str(body))
        status, body = req(port, "POST", "/api/transactions", token=tok_b,
                           body={"type": "income", "category": "Salary", "amount": 3000,
                                 "note": "BobPay", "date": "2026-11-01"})
        check("bob transaction create", status in (200, 201), str(body))
        status, body = req(port, "POST", "/api/savings", token=tok_b,
                           body={"name": "AliceGoal", "target": 2000})
        check("bob same savings name allowed (per-user)", status in (200, 201), str(body))
        status, body = req(port, "POST", "/api/habits", token=tok_b,
                           body={"habit": "BobHabit", "date": "2026-11-03"})
        check("bob habit create", status in (200, 201), str(body))

        # Isolation: each sees only their own.
        status, body = req(port, "GET", "/api/tasks", token=tok_a)
        check("alice tasks only hers",
              status == 200 and any("AliceTask" in str(t) for t in body) and not any("BobTask" in str(t) for t in body), str(body)[:200])
        status, body = req(port, "GET", "/api/tasks", token=tok_b)
        check("bob tasks only his",
              status == 200 and any("BobTask" in str(t) for t in body) and not any("AliceTask" in str(t) for t in body), str(body)[:200])
        status, body = req(port, "GET", "/api/transactions", token=tok_a)
        check("alice transactions only hers",
              status == 200 and any("AlicePay" in str(t) for t in body) and not any("BobPay" in str(t) for t in body), str(body)[:200])
        status, body = req(port, "GET", "/api/transactions", token=tok_b)
        check("bob transactions only his",
              status == 200 and any("BobPay" in str(t) for t in body) and not any("AlicePay" in str(t) for t in body), str(body)[:200])
        status, body = req(port, "GET", "/api/habits", token=tok_a)
        check("alice habits only hers",
              status == 200 and any("AliceHabit" in str(t) for t in body) and not any("BobHabit" in str(t) for t in body), str(body)[:200])
        status, body = req(port, "GET", "/api/overview", token=tok_a)
        check("alice overview counts only hers",
              status == 200 and body.get("income") == 5000, str(body)[:200])
        status, body = req(port, "GET", "/api/overview", token=tok_b)
        check("bob overview counts only his",
              status == 200 and body.get("income") == 3000, str(body)[:200])
        status, body = req(port, "GET", "/api/admin", token=tok_a)
        check("admin endpoint does not leak bob records",
              status == 200 and "BobPay" not in str(body) and "BobTask" not in str(body), str(body)[:200])

        # Cross-user edit/delete must fail with 404 (not leak existence).
        if task_a:
            status, _ = req(port, "PATCH", f"/api/tasks/{task_a}", token=tok_b,
                            body={"status": "Completed"})
            check("bob cannot PATCH alice task", status == 404, str(status))
            status, _ = req(port, "DELETE", f"/api/tasks/{task_a}", token=tok_b)
            check("bob cannot DELETE alice task", status == 404, str(status))
        if dec_a:
            status, _ = req(port, "DELETE", f"/api/decisions/{dec_a}", token=tok_b)
            check("bob cannot DELETE alice decision", status == 404, str(status))
        # Alice's own task/decision still intact after Bob's attempts.
        status, body = req(port, "GET", "/api/tasks", token=tok_a)
        check("alice task intact after bob attempts",
              status == 200 and any("AliceTask" in str(t) for t in body), str(body)[:200])
        # Alice can still edit her own task.
        if task_a:
            status, _ = req(port, "PATCH", f"/api/tasks/{task_a}", token=tok_a,
                            body={"status": "In Progress"})
            check("alice can PATCH own task", status == 200, str(status))
        # Bob savings add must not affect Alice's goal of same name.
        status, body = req(port, "POST", "/api/savings/add", token=tok_b,
                           body={"name": "AliceGoal", "amount": 100})
        check("bob savings add", status == 200 and body.get("saved") == 100, str(body))
        status, body = req(port, "GET", "/api/savings", token=tok_a)
        alice_saved = None
        for g in body if isinstance(body, list) else []:
            if g.get("name") == "AliceGoal":
                alice_saved = g.get("saved")
        check("alice savings untouched by bob", alice_saved == 0, str(body))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nper_user_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
