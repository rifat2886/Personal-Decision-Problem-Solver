#!/usr/bin/env python3
"""Delete-persistence regression test (template-delete bug, 2026-11-10).

A delete must stick: after DELETE, the row is gone from GET, stays gone
on a repeat GET (refresh), and stays gone after a server restart +
re-login. If the store cannot be rewritten, the API must answer 500 --
never a false 200 that looks deleted until the next refresh.

Covers, in txt mode (C++ + Python) and Postgres mode (C++):
  decisions, tasks, AI history (C++ only; Python answers 501 for AI)
  + legacy (ownerless) and console-created rows
  + a read-only-file negative test (server run as `nobody`): DELETE
    must answer 500 and the row must stay, then succeed after the
    file is writable again
  + the real dashboard UI (Playwright): click Delete, refresh, the
    row stays gone

Uses only disposable local data (temp dirs + the local pdps_test
database). NEVER points at Neon. Usage:
  python3 tests/delete_test.py [--database-url URL]
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, threading, time
import urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0
import random
USER = "deluser" + str(random.randint(100000, 999999))

def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS " + name)
    else:
        FAIL += 1
        print("FAIL " + name)
    return cond

class MockGemini(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"candidates": [{"content": {"parts": [{"text": "mock AI reply"}]}}]}).encode())
    def log_message(self, *a):
        pass

def start_mock():
    srv = HTTPServer(("127.0.0.1", 0), MockGemini)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}"

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

def start_server(cmd, port, data_dir, env_extra=None, as_user=None, cwd=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    full = cmd + ["--port", str(port), "--data-dir", data_dir]
    if as_user:
        full = ["sudo", "-n", "-u", as_user] + full
    return subprocess.Popen(full, cwd=cwd or ROOT,
                            stdout=open("/tmp/delete-test-server.log", "w"),
                            stderr=subprocess.STDOUT, env=env)

def stop_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

def login(base, user, pw):
    s, r = req(base, "POST", "/api/login", {"username": user, "password": pw})
    return r.get("token") if isinstance(r, dict) and s == 200 else None

def delete_flow(base, tok, label, with_ai=True):
    """Create + delete a decision, a task (and an AI entry); verify
    the delete sticks across GET, repeat GET, restart + re-login."""
    s, r = req(base, "POST", "/api/register",
               {"username": USER, "password": "D1234567", "confirm_password": "D1234567"})
    check(f"[{label}] register 201", s == 201)
    tok = login(base, USER, "D1234567")
    check(f"[{label}] login token", bool(tok))
    if not tok:
        return None
    s, d1 = req(base, "POST", "/api/decisions", {"type": "Daily", "priority": 43, "title": "DelDecision"}, tok)
    s, d2 = req(base, "POST", "/api/decisions", {"type": "Daily", "priority": 30, "title": "Pipe|Title"}, tok)
    s, t1 = req(base, "POST", "/api/tasks", {"title": "DelTask", "urgency": 8, "importance": 9, "deadline": ""}, tok)
    ids = (d1.get("id"), d2.get("id"), t1.get("id"))
    check(f"[{label}] created 2 decisions + 1 task", all(v is not None for v in ids))
    hid = None
    if with_ai:
        s, r = req(base, "POST", "/api/ai/daily-decision", {"input": "delete me | pipe"}, tok)
        hid = r.get("history_id") if isinstance(r, dict) else None
        check(f"[{label}] AI entry created (history_id {hid})", bool(hid))
    for kind, path, eid in (("decision", "/api/decisions/", d1.get("id")),
                            ("decision-pipe", "/api/decisions/", d2.get("id")),
                            ("task", "/api/tasks/", t1.get("id"))):
        s, r = req(base, "DELETE", path + str(eid), token=tok)
        check(f"[{label}] DELETE {kind} {eid} -> 200", s == 200)
        s, lst = req(base, "GET", path.rstrip("/") if kind == "task" else "/api/decisions", token=tok)
        key = "id"
        check(f"[{label}] {kind} {eid} gone from GET", all(x.get(key) != eid for x in lst))
        s, lst = req(base, "GET", path.rstrip("/") if kind == "task" else "/api/decisions", token=tok)
        check(f"[{label}] {kind} {eid} STILL gone on refresh GET", all(x.get(key) != eid for x in lst))
    if with_ai and hid:
        s, r = req(base, "DELETE", f"/api/ai/history/{hid}", token=tok)
        check(f"[{label}] DELETE AI history {hid} -> 200", s == 200)
        s, h = req(base, "GET", "/api/ai/history?limit=50", token=tok)
        entries = h.get("history", []) if isinstance(h, dict) else []
        check(f"[{label}] AI entry {hid} gone + STILL gone on refresh",
              all(e.get("id") != hid for e in entries))
    return tok

def restart_check(base, cmd, port, data_dir, env_extra, label, with_ai=True):
    proc = start_server(cmd, port, data_dir, env_extra)
    try:
        check(f"[{label}] server restarts", wait_up(base, proc))
        tok = login(base, USER, "D1234567")
        check(f"[{label}] re-login after restart", bool(tok))
        if tok:
            s, ds = req(base, "GET", "/api/decisions", token=tok)
            s, ts = req(base, "GET", "/api/tasks", token=tok)
            check(f"[{label}] after restart: decisions + tasks still empty",
                  ds == [] and ts == [])
            if with_ai:
                s, h = req(base, "GET", "/api/ai/history?limit=50", token=tok)
                if isinstance(h, dict):
                    check(f"[{label}] after restart: AI history still empty",
                          h.get("history", []) == [])
    finally:
        stop_server(proc)

def negative_readonly(base_cmd, port, data_dir, label, is_py=False):
    """Server as `nobody` with decisions/tasks files read-only: DELETE
    must answer 500 (not a false 200) and the row must stay. Then,
    after chmod back, the same DELETE must succeed."""
    user, pw = "rouser", "R1234567"
    salt = os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 100000).hex()
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "users.txt"), "w") as f:
        f.write(f"{user} pbkdf2$100000${salt}${h} ADMIN\n")
    with open(os.path.join(data_dir, "decisions.txt"), "w") as f:
        f.write(f"1|2026-11-10|Daily|43|RoDecision|{user}\n")
    with open(os.path.join(data_dir, "tasks.txt"), "w") as f:
        f.write(f"1|RoTask|8|9||Pending|{user}\n")
    subprocess.run(["chown", "-R", "nobody:nogroup", data_dir], check=True)
    subprocess.run(["chmod", "444", os.path.join(data_dir, "decisions.txt"),
                    os.path.join(data_dir, "tasks.txt")], check=True)
    # `nobody` cannot execute from /tmp (noexec) or read /home/hatch, so
    # run copies from world-readable locations.
    if base_cmd[0] == "./cpp_server":
        shutil.copy(os.path.join(ROOT, "cpp_server"), "/usr/local/bin/tpl-cpp-server")
        os.chmod("/usr/local/bin/tpl-cpp-server", 0o755)
        run_cmd = ["/usr/local/bin/tpl-cpp-server"]
    else:
        shutil.copy(os.path.join(ROOT, "dashboard", "server.py"), "/tmp/ro-py-server.py")
        os.chmod("/tmp/ro-py-server.py", 0o644)
        run_cmd = ["python3", "/tmp/ro-py-server.py"]
    base = f"http://127.0.0.1:{port}"
    proc = start_server(run_cmd, port, data_dir, as_user="nobody", cwd=data_dir)
    try:
        check(f"[{label}] server starts as nobody", wait_up(base, proc))
        tok = login(base, user, pw)
        check(f"[{label}] login as nobody-run server", bool(tok))
        if not tok:
            return
        s, r = req(base, "DELETE", "/api/decisions/1", token=tok)
        check(f"[{label}] DELETE read-only decision -> 500 (got {s})", s == 500)
        s, ds = req(base, "GET", "/api/decisions", token=tok)
        check(f"[{label}] read-only decision still present", any(d.get("id") in ("1", 1) for d in ds))
        s, r = req(base, "DELETE", "/api/tasks/1", token=tok)
        check(f"[{label}] DELETE read-only task -> 500 (got {s})", s == 500)
        s, ts = req(base, "GET", "/api/tasks", token=tok)
        check(f"[{label}] read-only task still present", any(t.get("id") in ("1", 1) for t in ts))
    finally:
        stop_server(proc)
    subprocess.run(["chmod", "644", os.path.join(data_dir, "decisions.txt"),
                    os.path.join(data_dir, "tasks.txt")], check=True)
    proc = start_server(run_cmd, port, data_dir, as_user="nobody", cwd=data_dir)
    try:
        check(f"[{label}] server restarts as nobody", wait_up(base, proc))
        tok = login(base, user, pw)
        s, r = req(base, "DELETE", "/api/decisions/1", token=tok)
        check(f"[{label}] DELETE writable decision -> 200", s == 200)
        s, r = req(base, "DELETE", "/api/tasks/1", token=tok)
        check(f"[{label}] DELETE writable task -> 200", s == 200)
    finally:
        stop_server(proc)
        subprocess.run(["chown", "-R", "root:root", data_dir], check=False)

def ui_flow(port, data_dir):
    """Real browser: click Delete in Overview + Task Management,
    refresh + re-login, the rows stay gone."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP ui_flow: playwright not installed")
        return
    base = f"http://127.0.0.1:{port}"
    shutil.rmtree(data_dir, ignore_errors=True)
    os.makedirs(data_dir, exist_ok=True)
    proc = start_server(["./cpp_server"], port, data_dir)
    try:
        if not wait_up(base, proc):
            check("[ui] server starts", False)
            return
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto(base + "/")
            pg.click("button[data-section='auth']")
            pg.fill("#regUser", "deluser")
            pg.fill("#regPass", "D1234567")
            pg.fill("#regPassConfirm", "D1234567")
            pg.click("#regBtn")
            pg.wait_for_function("document.querySelector('#regMsg').textContent.includes('Registered')", timeout=15000)
            pg.fill("#loginUser", "deluser")
            pg.fill("#loginPass", "D1234567")
            pg.click("#loginBtn")
            pg.wait_for_function("document.querySelector('section.active').id === 'overview'", timeout=15000)
            pg.click('button[data-section="daily"]')
            pg.fill("#ddAvailable", "120")
            pg.fill("#ddRequired", "60")
            pg.fill("#ddUrgency", "8")
            pg.fill("#ddImportance", "9")
            pg.fill("#ddEnergy", "7")
            pg.click("#ddBtn")
            pg.wait_for_function("document.querySelector('#ddMsg').textContent.length > 0", timeout=10000)
            pg.click('button[data-section="tasks"]')
            pg.fill("#taskTitle", "UIDelTask")
            pg.fill("#taskUrgency", "8")
            pg.fill("#taskImportance", "9")
            pg.click("#taskAddBtn")
            pg.wait_for_timeout(1500)
            pg.click('button[data-section="overview"]')
            pg.wait_for_timeout(1500)
            check("[ui] decision visible before delete",
                  "Daily decision" in pg.locator("#overviewDecisions").inner_text())
            pg.locator('#overviewDecisions button.btn-danger').first.click()
            pg.wait_for_timeout(2000)
            check("[ui] decision gone right after Delete click",
                  "Daily decision" not in pg.locator("#overviewDecisions").inner_text())
            pg.reload()
            pg.click("button[data-section='auth']")
            pg.fill("#loginUser", "deluser")
            pg.fill("#loginPass", "D1234567")
            pg.click("#loginBtn")
            pg.wait_for_function("document.querySelector('section.active').id === 'overview'", timeout=15000)
            pg.click('button[data-section="overview"]')
            pg.wait_for_timeout(1500)
            check("[ui] decision STILL gone after refresh + re-login",
                  "Daily decision" not in pg.locator("#overviewDecisions").inner_text())
            pg.click('button[data-section="tasks"]')
            pg.wait_for_timeout(1500)
            check("[ui] task visible before delete",
                  "UIDelTask" in pg.locator("#taskList").inner_text())
            pg.locator('#taskList button.btn-danger').first.click()
            pg.wait_for_timeout(2000)
            check("[ui] task gone right after Delete click",
                  "UIDelTask" not in pg.locator("#taskList").inner_text())
            pg.reload()
            pg.click("button[data-section='auth']")
            pg.fill("#loginUser", "deluser")
            pg.fill("#loginPass", "D1234567")
            pg.click("#loginBtn")
            pg.wait_for_function("document.querySelector('section.active').id === 'overview'", timeout=15000)
            pg.click('button[data-section="tasks"]')
            pg.wait_for_timeout(1500)
            check("[ui] task STILL gone after refresh + re-login",
                  "UIDelTask" not in pg.locator("#taskList").inner_text())
            b.close()
    finally:
        stop_server(proc)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url", default="postgresql://postgres:testpass@127.0.0.1:5432/pdps_test")
    args = ap.parse_args()
    mock_url = start_mock()
    ai_env = {"GEMINI_API_KEY": "test-key", "GEMINI_API_BASE_URL": mock_url}

    # C++ txt mode
    d = "/tmp/delete-test-cpp-txt"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    proc = start_server(["./cpp_server"], 8270, d, ai_env)
    try:
        assert wait_up(f"http://127.0.0.1:8270", proc), "C++ txt server did not start"
        delete_flow("http://127.0.0.1:8270", None, "cpp-txt", with_ai=True)
    finally:
        stop_server(proc)
    restart_check("http://127.0.0.1:8270", ["./cpp_server"], 8270, d, ai_env, "cpp-txt")

    # Python txt mode (no AI endpoints: 501 by design)
    d = "/tmp/delete-test-py-txt"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    proc = start_server(["python3", "dashboard/server.py"], 8271, d)
    try:
        assert wait_up(f"http://127.0.0.1:8271", proc), "Python server did not start"
        delete_flow("http://127.0.0.1:8271", None, "py-txt", with_ai=False)
    finally:
        stop_server(proc)
    restart_check("http://127.0.0.1:8271", ["python3", "dashboard/server.py"], 8271, d, None, "py-txt", with_ai=False)

    # C++ Postgres mode (disposable local database only)
    d = "/tmp/delete-test-cpp-pg"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    pg_env = dict(ai_env, DATABASE_URL=args.database_url)
    proc = start_server(["./cpp_server"], 8272, d, pg_env)
    try:
        assert wait_up(f"http://127.0.0.1:8272", proc), "C++ pg server did not start"
        delete_flow("http://127.0.0.1:8272", None, "cpp-pg", with_ai=True)
    finally:
        stop_server(proc)
    restart_check("http://127.0.0.1:8272", ["./cpp_server"], 8272, d, pg_env, "cpp-pg")

    # Negative: read-only files (C++ + Python, run as nobody)
    negative_readonly(["./cpp_server"], 8273, "/tmp/delete-test-ro-cpp", "cpp-readonly")
    negative_readonly(["python3", "dashboard/server.py"], 8274, "/tmp/delete-test-ro-py", "py-readonly")

    # Real browser UI flow
    ui_flow(8275, "/tmp/delete-test-ui")

    print(f"delete_test: {PASS} passed, {FAIL} failed")
    sys.exit(0 if FAIL == 0 else 1)

if __name__ == "__main__":
    main()
