#!/usr/bin/env python3
"""DB/store-failure registration test (Phase 2, C1/C2, 2026-11-10).

A user store that cannot be read must NEVER look like "no users
yet": registration must answer 500 and create nothing, and no ADMIN
may be granted. Covers all three programs:

  C++ server, Postgres mode: stop the local Postgres after startup,
    register -> 500 "Could not create the account...", login -> 500
    (not 401); after the database returns, the same username
    registers fine as USER behind the existing ADMIN (proving the
    failed attempt created nothing).
  C++ server, txt mode: users.txt replaced by a directory (this
    works even as root, where chmod 000 does not block reads),
    register -> 500; after restoring the file, the same username
    registers as USER.
  Python server, txt mode: same directory trick, register -> 500.
  Console, Postgres mode: stop Postgres mid-run, register ->
    refused with "Cannot read user data. Please try again later.",
    no "Registration successful" for the second user; after the
    database returns, the user registers as USER.
  Console, txt mode: users.txt replaced by a directory mid-run,
    register -> refused with the same message.

Uses only disposable local data (temp dirs + the local pdps_test
database). NEVER points at Neon. The Postgres service is stopped
twice and always restarted in a finally block, so a failure cannot
leave the service down. Usage:
  python3 tests/db_failure_test.py [--database-url URL]
"""
import argparse, json, os, random, shutil, subprocess, sys, tempfile, time
import urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0
TAG = "dbfail" + str(random.randint(100000, 999999))
DB_URL_DEFAULT = "postgresql://postgres:testpass@127.0.0.1:5432/pdps_test"
TABLES = ("ai_history", "daily_reports", "error_logs", "habit_log",
          "savings_goals", "transactions", "tasks", "decisions_backup",
          "decisions", "users")

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS " + name)
    else:
        FAIL += 1
        print("FAIL " + name + (" " + str(detail) if detail else ""))
    return cond

def req(base, method, path, body=None, token=None):
    r = urllib.request.Request(base + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}

def wait_up(base, proc, timeout=20):
    for _ in range(int(timeout * 5)):
        if proc.poll() is not None:
            return False
        try:
            s, _ = req(base, "GET", "/api/health")
            if s == 200:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False

def start_server(cmd, port, data_dir, env_extra=None, log_path="/tmp/db-failure-test-server.log"):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    full = cmd + ["--port", str(port), "--data-dir", data_dir]
    return subprocess.Popen(full, cwd=ROOT,
                            stdout=open(log_path, "w"),
                            stderr=subprocess.STDOUT, env=env)

def stop_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

def pg_stop():
    subprocess.run(["sudo", "-n", "service", "postgresql", "stop"],
                   capture_output=True, timeout=60)
    # The postmaster may exit before its backends finish dying, so
    # a query sent immediately can still slip through. Give the
    # backends a moment to terminate before any assertion runs.
    time.sleep(2)

def pg_start():
    subprocess.run(["sudo", "-n", "service", "postgresql", "start"],
                   capture_output=True, timeout=60)

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

def drop_tables(url):
    import psycopg2
    conn = psycopg2.connect(url)
    conn.autocommit = True
    with conn.cursor() as cur:
        for t in TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    conn.close()

def register(base, user, pw="F1234567"):
    return req(base, "POST", "/api/register",
               {"username": user, "password": pw, "confirm_password": pw})

def users_txt_as_dir(data_dir):
    """Replace users.txt by a directory: unreadable for every user,
    root included (chmod 000 does not block root). Returns the saved
    file content so the caller can restore it."""
    path = os.path.join(data_dir, "users.txt")
    saved = open(path, "rb").read()
    os.remove(path)
    os.mkdir(path)
    return saved

def restore_users_txt(data_dir, saved):
    path = os.path.join(data_dir, "users.txt")
    os.rmdir(path)
    with open(path, "wb") as f:
        f.write(saved)

def section_cpp_pg(db_url):
    print("== [cpp-pg] C++ server, Postgres, database stopped mid-run ==")
    drop_tables(db_url)
    tmp = tempfile.mkdtemp(prefix="pdps-dbfail-cpp-pg-")
    base = "http://127.0.0.1:8280"
    u1, u2 = TAG + "a", TAG + "b"
    proc = start_server(["./cpp_server"], 8280, tmp,
                        {"DATABASE_URL": db_url})
    try:
        check("[cpp-pg] server starts on healthy DB", wait_up(base, proc))
        s, r = register(base, u1)
        check(f"[cpp-pg] register {u1} -> 201 ADMIN", s == 201 and r.get("role") == "ADMIN")
        pg_stop()
        try:
            # Wait until the server's connection is observably dead:
            # a probe login returns 401 while the DB is up (no side
            # effects) and 500 once the store cannot be read.
            dead = False
            for _ in range(50):
                s, _ = req(base, "POST", "/api/login",
                           {"username": TAG + "probe", "password": "P1234567"})
                if s == 500:
                    dead = True
                    break
                time.sleep(0.3)
            check("[cpp-pg] store observably dead before assertions", dead)
            s, r = register(base, u2)
            check(f"[cpp-pg] register {u2} with DB down -> 500 (got {s})", s == 500)
            check("[cpp-pg] 500 message is the register message",
                  isinstance(r, dict) and r.get("error") == "Could not create the account. Please try again later.")
            s, r = req(base, "POST", "/api/login", {"username": u1, "password": "F1234567"})
            check(f"[cpp-pg] login {u1} with DB down -> 500, not 401 (got {s})", s == 500)
        finally:
            pg_start()
        log = open("/tmp/db-failure-test-server.log").read()
        check("[cpp-pg] real error logged to server stderr",
              "[register] could not read user store" in log, log[-300:])
        check("[cpp-pg] failed attempt never reached the INSERT",
              f"[register] could not save user '{u2}'" not in log)
    finally:
        stop_server(proc)
    # Database is back: the server restarts (fresh connection) and the
    # failed registration must not have left anything behind.
    proc = start_server(["./cpp_server"], 8280, tmp,
                        {"DATABASE_URL": db_url})
    try:
        check("[cpp-pg] server restarts after DB returns", wait_up(base, proc))
        s, r = register(base, u2)
        check(f"[cpp-pg] register {u2} after recovery -> 201 USER", s == 201 and r.get("role") == "USER")
        users = dbrows(db_url, "SELECT username, role FROM users ORDER BY username")
        check("[cpp-pg] DB holds exactly the two intended users",
              users == [(u1, "ADMIN"), (u2, "USER")], str(users))
    finally:
        stop_server(proc)
    shutil.rmtree(tmp, ignore_errors=True)

def section_cpp_txt():
    print("== [cpp-txt] C++ server, txt mode, users.txt unreadable ==")
    tmp = tempfile.mkdtemp(prefix="pdps-dbfail-cpp-txt-")
    base = "http://127.0.0.1:8281"
    u1, u2 = TAG + "c", TAG + "d"
    proc = start_server(["./cpp_server"], 8281, tmp)
    try:
        check("[cpp-txt] server starts (txt mode)", wait_up(base, proc))
        s, r = register(base, u1)
        check(f"[cpp-txt] register {u1} -> 201 ADMIN", s == 201 and r.get("role") == "ADMIN")
        saved = users_txt_as_dir(tmp)
        try:
            s, r = register(base, u2)
            check(f"[cpp-txt] register {u2} with users.txt unreadable -> 500 (got {s})", s == 500)
            check("[cpp-txt] 500 message is the register message",
                  isinstance(r, dict) and r.get("error") == "Could not create the account. Please try again later.")
        finally:
            restore_users_txt(tmp, saved)
        check("[cpp-txt] failed attempt wrote nothing to users.txt",
              u2 not in open(os.path.join(tmp, "users.txt")).read())
        s, r = register(base, u2)
        check(f"[cpp-txt] register {u2} after restore -> 201 USER", s == 201 and r.get("role") == "USER")
    finally:
        stop_server(proc)
    shutil.rmtree(tmp, ignore_errors=True)

def section_py_txt():
    print("== [py-txt] Python server, txt mode, users.txt unreadable ==")
    tmp = tempfile.mkdtemp(prefix="pdps-dbfail-py-txt-")
    base = "http://127.0.0.1:8282"
    u1, u2 = TAG + "e", TAG + "f"
    proc = start_server(["python3", "dashboard/server.py"], 8282, tmp)
    try:
        check("[py-txt] server starts (txt mode)", wait_up(base, proc))
        s, r = register(base, u1)
        check(f"[py-txt] register {u1} -> 201 ADMIN", s == 201 and r.get("role") == "ADMIN")
        saved = users_txt_as_dir(tmp)
        try:
            s, r = register(base, u2)
            check(f"[py-txt] register {u2} with users.txt unreadable -> 500 (got {s})", s == 500)
            check("[py-txt] 500 message is the register message",
                  isinstance(r, dict) and r.get("error") == "Could not create the account. Please try again later.")
        finally:
            restore_users_txt(tmp, saved)
        log = open("/tmp/db-failure-test-server.log").read()
        check("[py-txt] real error logged to server stderr",
              "[register] could not read user store" in log)
        check("[py-txt] failed attempt wrote nothing to users.txt",
              u2 not in open(os.path.join(tmp, "users.txt")).read())
        s, r = register(base, u2)
        check(f"[py-txt] register {u2} after restore -> 201 USER", s == 201 and r.get("role") == "USER")
    finally:
        stop_server(proc)
    shutil.rmtree(tmp, ignore_errors=True)

def run_console_blocks(binary, data_dir, steps, database_url=None):
    """Run the console interactively: steps is a list of
    (input_block, sleep_after, break_fn). break_fn runs while the
    console waits at the menu, before the next block is written.
    Returns (returncode, stdout)."""
    env = dict(os.environ)
    if database_url is None:
        env.pop("DATABASE_URL", None)
    else:
        env["DATABASE_URL"] = database_url
    proc = subprocess.Popen([binary], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, cwd=data_dir, env=env)
    try:
        for block, pause, break_fn in steps:
            if break_fn:
                break_fn()
            proc.stdin.write(block)
            proc.stdin.flush()
            time.sleep(pause)
        proc.stdin.close()
        proc.wait(timeout=30)
        return proc.returncode, proc.stdout.read()
    except Exception:
        proc.kill()
        raise

def reg_block(user, pw="F1234567"):
    # Same scripted shape as tests/console_pg_test.py: menu 1,
    # username, password, confirm, then the blanks the main-loop
    # pause consumes.
    return f"1\n{user}\n{pw}\n{pw}\n\n\n"

def section_console_pg(db_url):
    print("== [console-pg] Console, Postgres, database stopped mid-run ==")
    drop_tables(db_url)
    tmp = tempfile.mkdtemp(prefix="pdps-dbfail-console-pg-")
    binary = os.path.join(ROOT, "project")
    u1, u2 = TAG + "g", TAG + "h"
    code, out = run_console_blocks(binary, tmp, [
        (reg_block(u1), 3.5, None),
        (reg_block(u2) + "0\n", 0, pg_stop),
    ], database_url=db_url)
    try:
        check("[console-pg] console exits 0", code == 0, str(code))
        check("[console-pg] first registration succeeded once",
              out.count("Registration successful") == 1, out[-500:])
        check("[console-pg] refusal message shown for the second user",
              "Cannot read user data. Please try again later." in out)
    finally:
        pg_start()
    users = dbrows(db_url, "SELECT username, role FROM users ORDER BY username")
    check("[console-pg] DB holds only the first user (ADMIN)",
          users == [(u1, "ADMIN")], str(users))
    # Database is back: the second user registers as USER.
    proc = subprocess.run([binary], input=reg_block(u2) + "0\n",
                          capture_output=True, text=True, cwd=tmp, timeout=60,
                          env={**os.environ, "DATABASE_URL": db_url})
    check("[console-pg] second user registers after recovery",
          "Registration successful" in proc.stdout)
    users = dbrows(db_url, "SELECT username, role FROM users ORDER BY username")
    check("[console-pg] DB holds both users, ADMIN only the first",
          users == [(u1, "ADMIN"), (u2, "USER")], str(users))
    shutil.rmtree(tmp, ignore_errors=True)

def section_console_txt():
    print("== [console-txt] Console, txt mode, users.txt unreadable ==")
    tmp = tempfile.mkdtemp(prefix="pdps-dbfail-console-txt-")
    binary = os.path.join(ROOT, "project")
    u1, u2 = TAG + "i", TAG + "j"
    saved = {}
    def break_store():
        # Wait until the console has flushed u1's registration to
        # users.txt before snapshotting it: the fixed 3.5s sleep in
        # run_console_blocks is not enough on a loaded machine, and
        # reading the file early saves content without u1 (flaky
        # 2-check failure seen 2026-11-13). Poll up to 15s; on
        # timeout proceed anyway and let the checks fail honestly.
        path = os.path.join(tmp, "users.txt")
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                if u1.encode() in open(path, "rb").read():
                    break
            except OSError:
                pass
            time.sleep(0.2)
        saved["content"] = users_txt_as_dir(tmp)
    code, out = run_console_blocks(binary, tmp, [
        (reg_block(u1), 3.5, None),
        (reg_block(u2) + "0\n", 0, break_store),
    ])
    try:
        check("[console-txt] console exits 0", code == 0, str(code))
        check("[console-txt] first registration succeeded once",
              out.count("Registration successful") == 1, out[-500:])
        check("[console-txt] refusal message shown for the second user",
              "Cannot read user data. Please try again later." in out)
    finally:
        if "content" in saved:
            restore_users_txt(tmp, saved["content"])
    content = open(os.path.join(tmp, "users.txt")).read()
    check("[console-txt] failed attempt wrote nothing to users.txt",
          u2 not in content and u1 in content)
    proc = subprocess.run([binary], input=reg_block(u2) + "0\n",
                          capture_output=True, text=True, cwd=tmp, timeout=60,
                          env={k: v for k, v in os.environ.items()
                               if k != "DATABASE_URL"})
    check("[console-txt] second user registers after restore",
          "Registration successful" in proc.stdout)
    content = open(os.path.join(tmp, "users.txt")).read()
    check("[console-txt] users.txt holds ADMIN first, USER second",
          f"{u1} " in content and "ADMIN" in content
          and f"{u2} " in content and content.count("USER") == 1)
    shutil.rmtree(tmp, ignore_errors=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url", default=DB_URL_DEFAULT)
    args = ap.parse_args()
    try:
        import psycopg2  # noqa: F401  (needed for the pg sections)
    except ImportError:
        print("FAIL db_failure_test needs python3-psycopg2 for the pg sections")
        return 2
    try:
        section_cpp_pg(args.database_url)
        section_cpp_txt()
        section_py_txt()
        section_console_pg(args.database_url)
        section_console_txt()
    finally:
        # Never leave the local Postgres stopped, whatever failed.
        pg_start()
    print(f"db_failure_test: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
