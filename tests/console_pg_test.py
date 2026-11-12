#!/usr/bin/env python3
"""Console-app Postgres-mode tests (Phase 4, Batch B).

Runs the console binary with DATABASE_URL pointing at a TEST database
only (never a production database), then checks, over the console and
via direct SQL:
  - register/login in Postgres mode (first user ADMIN, second USER)
  - no txt data files are created in Postgres mode
  - decisions/tasks/transactions/savings/habits/daily-reports via the console
  - per-user isolation between two console users
  - backup/restore/delete via the console
  - legacy NULL-owner row visibility (sole user sees it, hidden with 2 users)
  - cross-check with the C++ server API on the SAME database, both directions
  - fail-fast: an unreachable DATABASE_URL exits non-zero, no txt fallback

The test drops and recreates the pdps tables first, so it must NEVER
be pointed at a database holding real data.

Usage:
    python3 tests/console_pg_test.py --binary ./project \
        --database-url postgres://postgres@localhost:5432/pdps_test
    # The console binary must be built with libpq (make on a machine
    # with libpq-dev). --server-cmd/--port select the C++ server used
    # for the API cross-checks.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

PASS = 0
FAIL = 0

TABLES = ("ai_history", "daily_reports", "error_logs", "habit_log",
          "savings_goals", "transactions", "tasks", "decisions_backup",
          "decisions", "users")

# txt data files that must NEVER appear in Postgres mode (the console
# reads/writes the database instead). Local outputs/scratch
# (financial_report.txt, search_history.txt, system_log.txt) are
# allowed and are not in this list.
TXT_DATA_FILES = ("users.txt", "decisions.txt", "tasks.txt",
                  "transactions.txt", "savings_goals.txt", "habit_log.txt",
                  "daily_report.txt", "error_log.txt", "decisions_backup.txt")


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def run_console(binary, data_dir, script, database_url):
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    proc = subprocess.run([binary], input=script, capture_output=True,
                          text=True, cwd=data_dir, timeout=60, env=env)
    return proc.returncode, proc.stdout


def dbrows(url, sql, args=None):
    import psycopg2
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return cur.fetchall()
    finally:
        conn.close()


def dbexec(url, sql, args=None):
    import psycopg2
    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
    finally:
        conn.close()


def req(port, method, path, token=None, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--server-cmd", default="./cpp_server")
    ap.add_argument("--port", type=int, default=8191)
    args = ap.parse_args()
    args.binary = os.path.abspath(args.binary)
    args.server_cmd = os.path.abspath(args.server_cmd)

    # Fresh schema: drop tables (test database only).
    import psycopg2
    conn = psycopg2.connect(args.database_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        for t in TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    conn.close()

    tmp = tempfile.mkdtemp(prefix="pdps-console-pg-test-")
    print(f"data dir: {tmp}")
    proc = None
    try:
        # S1: register alice (first = ADMIN) + bob (USER).
        script1 = (
            "1\nalice\nAlice1234\nAlice1234\n\n\n"
            "1\nbob\nBob12345\nBob12345\n\n\n"
            "0\n"
        )
        code, out = run_console(args.binary, tmp, script1, args.database_url)
        check("pg exit 0", code == 0, str(code))
        check("pg mode banner", "Postgres mode: using the online database" in out)
        check("pg register alice", "Registration successful" in out)
        users = dbrows(args.database_url,
                       "SELECT username, role FROM users ORDER BY username")
        check("pg users in DB", users == [("alice", "ADMIN"), ("bob", "USER")],
              str(users))
        check("pg no txt data files",
              not any(os.path.exists(os.path.join(tmp, f)) for f in TXT_DATA_FILES),
              str(os.listdir(tmp)))
        # Plaintext must never land in the DB.
        hashes = dbrows(args.database_url, "SELECT password_hash FROM users")
        check("pg passwords hashed",
              all("pbkdf2$100000$" in h[0] for h in hashes) and
              all("Alice1234" not in h[0] and "Bob12345" not in h[0]
                  for h in hashes), str(hashes))

        # S2: alice writes everything through the console.
        script2 = (
            "2\nalice\nAlice1234\n\n\n"
            "9\n60\n30\n8\n8\n5\n\n\n"          # daily decision
            "11\n1\nPgTask\n8\n8\n2026-11-20\n\n\n"  # task
            "16\n2026-11-09\nincome\nSalary\n10000\nMonthly pay\n\n\n"
            "16\n2026-11-09\nexpense\nFood\n1000\nLunch\n\n\n"
            "18\n\n\n"                          # balance
            "19\nLaptop\n10000\n\n\n"           # savings goal
            "20\nLaptop\n1000\n\n\n"            # add savings
            "19\nLaptop\n5000\n\n\n"            # duplicate goal -> refused
            "22\nReading\n2026-11-09\n\n\n"     # habit
            "26\n\n\n"                          # export TXT
            "36\n10000\n1000\n3\n4\n\n\n"       # daily report
            "31\n\n\n"                          # backup
            "0\n"
        )
        code, out = run_console(args.binary, tmp, script2, args.database_url)
        check("pg session2 exit 0", code == 0, str(code))
        check("pg login alice", "Login successful" in out)
        check("pg daily suggestion", "Complete this task first." in out)
        check("pg task saved msg", "Tasks saved to the database." in out)
        check("pg balance 9000",
              "Total Income: 10000.00" in out and
              "Total Expense: 1000.00" in out and
              "Current Balance: 9000.00" in out, out[-800:])
        check("pg duplicate goal refused", "may already exist" in out)
        check("pg export msg", "TXT report exported to financial_report.txt" in out)
        with open(os.path.join(tmp, "financial_report.txt")) as f:
            rep = f.read()
        check("pg export file has console tx", "Salary" in rep and "Monthly pay" in rep, rep)
        decs = dbrows(args.database_url,
                      "SELECT type, priority, title, owner FROM decisions ORDER BY id")
        check("pg decisions in DB", len(decs) == 2 and
              decs[0][0] == "Daily" and decs[0][1] == 40 and
              decs[0][2] == "Daily decision: Complete this task first." and
              decs[0][3] == "alice" and decs[1][0] == "Task", str(decs))
        tasks = dbrows(args.database_url,
                       "SELECT title, urgency, importance, deadline, status, owner FROM tasks")
        check("pg task in DB", tasks == [("PgTask", 8, 8, "2026-11-20", "Pending", "alice")],
              str(tasks))
        txs = dbrows(args.database_url,
                     "SELECT tx_date, type, category, amount, note, owner FROM transactions ORDER BY id")
        check("pg transactions in DB",
              len(txs) == 2 and txs[0][1] == "income" and float(txs[0][3]) == 10000.0
              and txs[1][1] == "expense" and float(txs[1][3]) == 1000.0
              and txs[0][5] == "alice", str(txs))
        goals = dbrows(args.database_url,
                       "SELECT name, target, saved, owner FROM savings_goals")
        check("pg savings in DB",
              len(goals) == 1 and goals[0][0] == "Laptop" and
              float(goals[0][1]) == 10000.0 and float(goals[0][2]) == 1000.0,
              str(goals))
        habits = dbrows(args.database_url,
                        "SELECT habit, log_date, owner FROM habit_log")
        check("pg habit in DB", habits == [("Reading", "2026-11-09", "alice")],
              str(habits))
        reps = dbrows(args.database_url, "SELECT line FROM daily_reports")
        check("pg daily report in DB",
              len(reps) == 1 and "User: alice" in reps[0][0] and
              "Balance: 9000.00" in reps[0][0], str(reps))
        bak = dbrows(args.database_url, "SELECT COUNT(*) FROM decisions_backup")
        check("pg backup rows in DB", bak[0][0] == 2, str(bak))

        # S3: cross-check A — the server API reads console-written data.
        env = dict(os.environ)
        env["DATABASE_URL"] = args.database_url
        proc = subprocess.Popen([args.server_cmd, "--port", str(args.port)],
                                env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        try:
            for _ in range(100):
                time.sleep(0.2)
                # If our server died at startup (e.g. the port is taken
                # by a stale server), stop: polling /api/health would
                # otherwise talk to the stranger server.
                if proc.poll() is not None:
                    check("api server starts",
                          False, f"server exited with {proc.returncode}")
                    return 1
                try:
                    s, _ = req(args.port, "GET", "/api/health")
                    if s == 200:
                        break
                except Exception:
                    pass
            else:
                check("api server starts", False, "no /api/health in 20s")
                return 1
            check("api server is ours (still running)", proc.poll() is None)
            s, b = req(args.port, "GET", "/api/health")
            check("api health storage=postgres",
                  s == 200 and json.loads(b).get("storage") == "postgres", b)
            s, b = req(args.port, "POST", "/api/login",
                       body={"username": "alice", "password": "Alice1234"})
            tok_a = json.loads(b).get("token") if s == 200 else None
            check("api login alice", s == 200 and bool(tok_a), b)
            s, b = req(args.port, "POST", "/api/login",
                       body={"username": "bob", "password": "Bob12345"})
            tok_b = json.loads(b).get("token") if s == 200 else None
            check("api login bob", s == 200 and bool(tok_b), b)
            s, b = req(args.port, "GET", "/api/tasks", token=tok_a)
            check("api sees console task", s == 200 and "PgTask" in b, b)
            s, b = req(args.port, "GET", "/api/decisions", token=tok_a)
            check("api sees console decisions",
                  s == 200 and "Complete this task first." in b and "PgTask" in b, b)
            s, b = req(args.port, "GET", "/api/transactions", token=tok_a)
            check("api sees console transactions",
                  s == 200 and "Salary" in b and "Monthly pay" in b, b)
            s, b = req(args.port, "GET", "/api/savings", token=tok_a)
            check("api sees console savings", s == 200 and "Laptop" in b, b)
            s, b = req(args.port, "GET", "/api/habits", token=tok_a)
            check("api sees console habit", s == 200 and "Reading" in b, b)
            s, b = req(args.port, "GET", "/api/tasks", token=tok_b)
            check("api bob cannot see alice task",
                  s == 200 and "PgTask" not in b, b)

            # S4: cross-check B — API writes, console reads.
            s, b = req(args.port, "POST", "/api/tasks", token=tok_a,
                       body={"title": "ApiTask", "urgency": 5,
                             "importance": 5, "deadline": "2026-11-25"})
            check("api task create", s == 201, b)
            s, b = req(args.port, "POST", "/api/transactions", token=tok_a,
                       body={"date": "2026-11-09", "type": "income",
                             "category": "Bonus", "amount": 500, "note": "ApiTx"})
            check("api transaction create", s == 201, b)
            s, b = req(args.port, "POST", "/api/decisions", token=tok_a,
                       body={"type": "Daily", "priority": 7,
                             "title": "ApiDecision"})
            check("api decision create", s == 201, b)
        finally:
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                proc = None

        script4 = (
            "2\nalice\nAlice1234\n\n\n"
            "13\n1\n2\n\n\n"      # task status list (shows ApiTask)
            "17\n\n\n"            # transactions (shows ApiTx)
            "28\nApiDecision\n\n\n"  # search decisions for ApiDecision
            "0\n"
        )
        code, out = run_console(args.binary, tmp, script4, args.database_url)
        check("pg session4 exit 0", code == 0, str(code))
        check("console sees api task", "ApiTask" in out, out[-800:])
        check("console sees api transaction", "ApiTx" in out, out[-800:])
        check("console search finds api decision", "ApiDecision" in out)

        # S5: bob isolation + admin panel.
        script5 = (
            "2\nbob\nBob12345\n\n\n"
            "17\n\n\n"
            "13\n\n\n"
            "5\n\n\n"
            "0\n"
        )
        code, out = run_console(args.binary, tmp, script5, args.database_url)
        check("pg bob session exit 0", code == 0, str(code))
        check("pg bob cannot see alice tx", "Salary" not in out, out[-600:])
        check("pg bob cannot see alice task", "PgTask" not in out, out[-600:])
        check("pg bob not admin", "Admin access required" in out)
        script5b = (
            "2\nalice\nAlice1234\n\n\n"
            "5\n\n\n"
            "0\n"
        )
        code, out = run_console(args.binary, tmp, script5b, args.database_url)
        check("pg admin panel lists users",
              "Username: alice | Role: ADMIN" in out and
              "Username: bob | Role: USER" in out and
              "Alice1234" not in out and "Bob12345" not in out, out[-500:])

        # Legacy: NULL-owner decision, hidden with 2 users, visible to sole user.
        dbexec(args.database_url,
               "INSERT INTO decisions (record_date, type, priority, title, owner) "
               "VALUES ('2026-11-01','Daily',5,'LegacyDecision',NULL)")
        script_leg1 = (
            "2\nalice\nAlice1234\n\n\n"
            "28\nLegacyDecision\n\n\n"
            "0\n"
        )
        code, out = run_console(args.binary, tmp, script_leg1, args.database_url)
        check("pg legacy hidden with 2 users", "No matching records found." in out,
              out[-400:])
        dbexec(args.database_url, "DELETE FROM users WHERE username='bob'")
        code, out = run_console(args.binary, tmp, script_leg1, args.database_url)
        check("pg legacy visible to sole user", "LegacyDecision" in out, out[-400:])

        # S6: password change + re-login (alice).
        script6 = (
            "2\nalice\nAlice1234\n\n\n"
            "4\nAlice1234\nAliceNew123\n\n\n"
            "0\n"
        )
        code, out = run_console(args.binary, tmp, script6, args.database_url)
        check("pg password changed", "Password changed successfully!" in out,
              out[-400:])
        code, out = run_console(args.binary, tmp,
                                "2\nalice\nAliceNew123\n\n\n0\n",
                                args.database_url)
        check("pg re-login with new password", "Login successful" in out)
        code, out = run_console(args.binary, tmp,
                                "2\nalice\nAlice1234\n\n\n0\n",
                                args.database_url)
        check("pg old password rejected", "Invalid username or password!" in out)

        # S7: delete a decision, then restore it from the backup.
        daily_id = dbrows(args.database_url,
                          "SELECT id FROM decisions WHERE owner='alice' "
                          "AND type='Daily' AND title LIKE %s",
                          ("Daily decision:%",))
        check("pg daily decision id found", len(daily_id) == 1, str(daily_id))
        did = str(daily_id[0][0])
        script7 = (
            "2\nalice\nAliceNew123\n\n\n"
            f"34\n{did}\ny\n\n\n"
            "0\n"
        )
        code, out = run_console(args.binary, tmp, script7, args.database_url)
        check("pg delete decision", "Decision deleted successfully." in out,
              out[-400:])
        gone = dbrows(args.database_url,
                      "SELECT COUNT(*) FROM decisions WHERE id=%s", (int(did),))
        check("pg decision gone from DB", gone[0][0] == 0, str(gone))
        script7b = (
            "2\nalice\nAliceNew123\n\n\n"
            "32\ny\n\n\n"
            "0\n"
        )
        code, out = run_console(args.binary, tmp, script7b, args.database_url)
        check("pg restore decisions", "Decisions restored successfully!" in out,
              out[-400:])
        back = dbrows(args.database_url,
                      "SELECT COUNT(*) FROM decisions WHERE owner='alice'")
        check("pg decisions restored in DB", back[0][0] == 2, str(back))

        # Error log: a row written directly in SQL must show in menu 33.
        dbexec(args.database_url,
               "INSERT INTO error_logs (line) VALUES ('console-pg-test error line')")
        code, out = run_console(args.binary, tmp,
                                "2\nalice\nAliceNew123\n\n\n33\n\n\n0\n",
                                args.database_url)
        check("pg error log shows row", "console-pg-test error line" in out,
              out[-400:])

        # S8: fail-fast on an unreachable DATABASE_URL.
        bad_url = "postgresql://postgres:wrongpass@127.0.0.1:1/pdps_test"
        code, out = run_console(args.binary, tmp, "0\n", bad_url)
        check("pg fail-fast exit non-zero", code != 0, str(code))
        check("pg fail-fast message",
              "Postgres mode failed" in out and "will not fall back" in out,
              out[-400:])

        # Txt mode: no banner, exit 0 (binary built with libpq still
        # runs txt mode when DATABASE_URL is unset).
        env = dict(os.environ)
        env.pop("DATABASE_URL", None)
        proc2 = subprocess.run([args.binary], input="0\n", capture_output=True,
                               text=True, cwd=tmp, timeout=30, env=env)
        check("txt mode exit 0", proc2.returncode == 0, str(proc2.returncode))
        check("txt mode no pg banner", "Postgres mode" not in proc2.stdout)
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nconsole_pg_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
