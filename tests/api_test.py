#!/usr/bin/env python3
"""Automated API regression test for the dashboard server.

Runs the server (C++ or Python fallback) in a fresh temporary data
directory, then exercises the API end to end. No real passwords are
used; all test accounts are created inside the temporary directory
and deleted with it.

Usage:
    python3 tests/api_test.py --server-cmd "path/to/cpp_server" --port 8123
    python3 tests/api_test.py --server-cmd "python3 dashboard/server.py" --port 8124

Exit code 0 = all checks passed, 1 = at least one check failed.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-cmd", required=True)
    ap.add_argument("--port", type=int, default=8123)
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="pdps-api-test-")
    print(f"data dir: {tmp}")
    # Old-format plaintext account, to test backward-compatible migration.
    with open(os.path.join(tmp, "users.txt"), "w") as f:
        f.write("olduser OldPass123 ADMIN\n")
    cmd = args.server_cmd.split() + ["--port", str(args.port),
                                     "--data-dir", tmp]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        # Wait for server to accept connections.
        for _ in range(30):
            # Any HTTP response (even a 404 for a missing static file
            # in the temp data dir) proves the server is listening.
            status, _ = req(args.port, "GET", "/")
            if status != 0:
                break
            time.sleep(0.5)
        else:
            print("FAIL server did not start")
            return 1

        port = args.port
        # 1. Old plaintext account logs in, then is migrated to a hash.
        status, body = req(port, "POST", "/api/login",
                           body={"username": "olduser", "password": "OldPass123"})
        check("old-plaintext login", status == 200 and "token" in body, str(body))
        token_old = body.get("token", "")
        with open(os.path.join(tmp, "users.txt")) as f:
            users_line = f.read()
        check("old account migrated to hash",
              "OldPass123" not in users_line and "pbkdf2$100000$" in users_line,
              users_line[:80])
        status, body = req(port, "POST", "/api/login",
                           body={"username": "olduser", "password": "OldPass123"})
        check("hashed login", status == 200 and "token" in body, str(body))
        token_old = body.get("token", token_old)

        # 2. New registration is hashed, second user is USER, admin list.
        status, body = req(port, "POST", "/api/register",
                           body={"username": "newuser", "password": "NewPass123"})
        check("register newuser", status == 201 and body.get("role") == "USER", str(body))
        with open(os.path.join(tmp, "users.txt")) as f:
            check("new account hashed",
                  "NewPass123" not in f.read())
        status, body = req(port, "POST", "/api/login",
                           body={"username": "newuser", "password": "NewPass123"})
        check("newuser login", status == 200 and "token" in body, str(body))
        token_new = body.get("token", "")

        # 2b. Confirm password (auth fix, 2026-11-09): matching confirm
        # registers, mismatched confirm is rejected with 400.
        status, body = req(port, "POST", "/api/register",
                           body={"username": "confirmuser", "password": "Confirm123",
                                 "confirm_password": "Confirm123"})
        check("register with matching confirm", status == 201, str(body))
        status, body = req(port, "POST", "/api/register",
                           body={"username": "mismatchuser", "password": "Mismatch123",
                                 "confirm_password": "Other1234"})
        check("register with mismatched confirm 400", status == 400, str(body))
        status, body = req(port, "GET", "/api/admin", token=token_new)
        check("non-admin admin endpoint 403", status == 403, str(body))
        status, body = req(port, "GET", "/api/admin", token=token_old)
        check("admin endpoint for ADMIN", status == 200, str(body))

        # 3. Rate limiting: 5 wrong logins, then 429.
        for _ in range(5):
            req(port, "POST", "/api/login",
                body={"username": "newuser", "password": "Wrong1234"})
        status, _ = req(port, "POST", "/api/login",
                        body={"username": "newuser", "password": "Wrong1234"})
        check("rate limiting 429", status == 429, str(status))

        # 4. Core features (using the ADMIN token).
        t = token_old
        status, body = req(port, "POST", "/api/daily-decision", token=t,
                           body={"availableTime": 120, "requiredTime": 60,
                                 "urgency": 9, "importance": 9, "energy": 8})
        check("daily decision", status in (200, 201), str(body))
        status, body = req(port, "POST", "/api/priority", token=t,
                           body={"urgency": 10, "importance": 10})
        check("priority 50", status == 200 and body.get("score") == 50, str(body))
        status, body = req(port, "POST", "/api/tasks", token=t,
                           body={"title": "TaskA", "urgency": 8, "importance": 8,
                                 "deadline": "2026-11-20"})
        check("task create", status in (200, 201), str(body))
        task_id = body.get("id")
        if task_id is not None:
            status, body = req(port, "PATCH", f"/api/tasks/{task_id}", token=t,
                               body={"status": "In Progress"})
            check("task PATCH In Progress", status == 200, str(body))
        status, body = req(port, "GET", "/api/deadlines?today=2026-11-10", token=t)
        check("deadlines UPCOMING", status == 200 and
              any("TaskA" in str(d) for d in (body if isinstance(body, list) else [])), str(body)[:200])
        status, body = req(port, "POST", "/api/decision-explanation", token=t,
                           body={"urgency": 9, "importance": 9})
        check("decision explanation 45", status == 200 and body.get("score") == 45, str(body))
        status, body = req(port, "POST", "/api/compare-options", token=t,
                           body={"name1": "Alpha", "benefit1": 8, "cost1": 3, "risk1": 2,
                                 "name2": "Beta", "benefit2": 5, "cost2": 4, "risk2": 6})
        check("compare Alpha wins", status == 200 and body.get("suggested") == "Alpha", str(body))
        status, body = req(port, "POST", "/api/multi-task", token=t,
                           body={"availableEnergy": 5, "availableTime": 3,
                                 "tasks": [{"name": "Assignment", "deadlineUrgency": 5,
                                            "energy": 3, "time": 2}]})
        check("multi-task Assignment", status == 200 and
              any(x.get("name") == "Assignment" for x in body.get("recommended", [])), str(body))
        status, body = req(port, "GET", "/api/budget?income=5000&expenses=1200", token=t)
        check("budget remaining 3800", status == 200 and body.get("remaining") == 3800, str(body))
        status, body = req(port, "POST", "/api/transactions", token=t,
                           body={"type": "income", "category": "Salary", "amount": 5000,
                                 "note": "Nov", "date": "2026-11-01"})
        check("transaction add", status in (200, 201), str(body))
        status, body = req(port, "POST", "/api/savings", token=t,
                           body={"name": "Laptop", "target": 10000})
        check("savings goal", status in (200, 201), str(body))
        # Concurrent savings adds: 10 x 100 must total 1000, no lost update.
        def add_savings():
            req(port, "POST", "/api/savings/add", token=t,
                body={"name": "Laptop", "amount": 100})
        threads = [threading.Thread(target=add_savings) for _ in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        status, body = req(port, "GET", "/api/savings", token=t)
        saved = None
        for g in (body if isinstance(body, list) else []):
            if g.get("name") == "Laptop":
                saved = g.get("saved")
        check("concurrent savings = 1000", saved == 1000, str(body))
        status, body = req(port, "POST", "/api/habits", token=t,
                           body={"habit": "Reading", "date": "2026-11-03"})
        check("habit mark", status in (200, 201), str(body))
        status, body = req(port, "POST", "/api/habit-streak-calc", token=t,
                           body={"previousDays": 5, "completedToday": 1})
        check("streak calc", status == 200, str(body))
        status, body = req(port, "POST", "/api/study-planner", token=t,
                           body={"subject": "Math", "days": 3, "hours": 2})
        check("study planner 6h", status == 200 and body.get("totalHours") == 6, str(body))
        status, body = req(port, "POST", "/api/time-allocation", token=t,
                           body={"study": 7, "work": 7, "sleep": 7, "other": 0})
        check("time allocation", status == 200, str(body))
        status, body = req(port, "GET", "/api/reports?month=2026-11", token=t)
        check("monthly report", status == 200, str(body)[:200])
        status, body = req(port, "GET", "/api/decisions?search=Daily", token=t)
        check("search finds Daily", status == 200, str(body)[:200])
        status, body = req(port, "POST", "/api/backup", token=t)
        check("backup", status == 200, str(body))
        status, body = req(port, "GET", "/api/export?format=csv", token=t)
        check("export csv", status == 200, str(body)[:200])
        status, body = req(port, "GET", "/api/overview", token=t)
        check("overview", status == 200, str(body)[:200])
        status, body = req(port, "GET", "/api/info", token=t)
        check("info backend", status == 200 and "backend" in body, str(body))
        status, body = req(port, "GET", "/api/overview")
        check("unauthenticated overview 401", status == 401, str(status))
        status, body = req(port, "GET", "/users.txt")
        check("static /users.txt 404", status == 404, str(status))
        status, body = req(port, "GET", "/")
        check("landing page 200", status == 200, str(status))
        # 5. Google Sign-In (Phase 3): separate clearly-delimited
        # block, 6 checks on EACH server (total becomes 44).
        # No GOOGLE_CLIENT_ID is set here, so the C++ server
        # reports sign-in disabled (config enabled=false, sign-in
        # 503) and the Python server answers 501 for Google auth
        # (after login) while unauthenticated calls still get 401.
        if "server.py" in args.server_cmd:
            status, body = req(port, "GET", "/api/auth/google/config", token=t)
            check("google config 501 (python)", status == 501, str(body))
            status, body = req(port, "POST", "/api/auth/google", token=t,
                               body={"credential": "x.y.z"})
            check("google sign-in 501 (python)", status == 501, str(body))
            status, body = req(port, "POST", "/api/auth/google/link", token=t,
                               body={"credential": "x.y.z"})
            check("google link 501 (python)", status == 501, str(body))
            status, body = req(port, "POST", "/api/auth/google/unlink", token=t, body={})
            check("google unlink 501 (python)", status == 501, str(body))
            status, body = req(port, "POST", "/api/auth/set-password", token=t,
                               body={"password": "NewPass123", "confirm_password": "NewPass123"})
            check("google set-password 501 (python)", status == 501, str(body))
            status, body = req(port, "POST", "/api/auth/google",
                               body={"credential": "x.y.z"})
            check("google sign-in without token 401 (python)", status == 401, str(status))
        else:
            status, body = req(port, "GET", "/api/auth/google/config")
            check("google config disabled", status == 200
                  and body.get("enabled") is False
                  and body.get("clientId") == "", str(body))
            status, body = req(port, "POST", "/api/auth/google",
                               body={"credential": "x.y.z"})
            check("google sign-in 503 (no client id)", status == 503, str(body))
            status, body = req(port, "POST", "/api/auth/google/link",
                               body={"credential": "x.y.z"})
            check("google link without token 401", status == 401, str(status))
            status, body = req(port, "POST", "/api/auth/google/unlink", body={})
            check("google unlink without token 401", status == 401, str(status))
            status, body = req(port, "POST", "/api/auth/set-password",
                               body={"password": "NewPass123", "confirm_password": "NewPass123"})
            check("google set-password without token 401", status == 401, str(status))
            status, body = req(port, "POST", "/api/auth/google", body={})
            check("google sign-in missing credential 400", status == 400, str(body))
        status, body = req(port, "POST", "/api/logout", token=t)
        check("logout", status == 200, str(body))
        status, body = req(port, "GET", "/api/overview", token=t)
        check("token invalid after logout", status == 401, str(status))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\napi_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
