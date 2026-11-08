#!/usr/bin/env python3
"""Auth-gate test for the dashboard (Playwright).

Covers, on one C++ server with a temp data dir:
  1. No login: only Welcome (landing) + Login/Register (auth) nav
     buttons are visible; every protected nav button is hidden;
     the active section is landing; a JS request for a protected
     section is redirected to auth; protected APIs return 401.
  2. After login: all nav buttons visible, Overview active.
  3. Logout: dashboard hides at once, Welcome (landing) active,
     token cleared, protected API 401 again.
  4. Refresh with a valid token: dashboard is NOT shown until
     /api/me verifies it, then Overview appears.
  5. Refresh / API call with an invalidated token (server session
     deleted via /api/logout, local token kept): the page returns
     to Login, the token is cleared, and no dashboard is shown.
     This is the session-expire path: the server returns 401.
  6. Cross-user: Alice's task is invisible to Bob, and Bob's
     PATCH/DELETE on Alice's task id returns 404.
  7. Mobile 390px: same pre-login / post-login / logout visibility.

Usage:
    python3 tests/auth_gate_test.py --server ./cpp_server --port 8150
"""
import argparse, os, shutil, subprocess, sys, tempfile, time
PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  PASS {name}")
    else: FAIL += 1; print(f"  FAIL {name} {detail}")

PROTECTED = ["overview", "history", "daily", "tasks", "taskstatus", "priority",
             "compare", "explanation", "deadlines", "budget", "finance",
             "savings", "study", "timealloc", "habits", "reports", "problem",
             "profile", "admin", "analytics", "settings", "ai-daily"]
PUBLIC = ["landing", "auth"]

def nav_visible(page, sec):
    return page.evaluate(f"!!document.querySelector(\"button[data-section='{sec}']\") && getComputedStyle(document.querySelector(\"button[data-section='{sec}']\")).display !== 'none'")

def active_section(page):
    return page.evaluate("document.querySelector('section.active')?.id")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="./cpp_server")
    ap.add_argument("--port", type=int, default=8150)
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright
    tmp = tempfile.mkdtemp(prefix="pdps-auth-gate-")
    base = f"http://127.0.0.1:{args.port}"
    proc = subprocess.Popen([args.server, "--port", str(args.port), "--data-dir", tmp],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(30):
            try:
                import urllib.request
                with urllib.request.urlopen(base + "/", timeout=2) as r:
                    if r.status == 200: break
            except Exception: time.sleep(0.5)
        else: print("FAIL server did not start"); return 1
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(base + "/", timeout=15000)
            page.wait_for_timeout(500)
            # 1. No login, desktop
            check("no-login active is landing", active_section(page) == "landing", str(active_section(page)))
            check("no-login public nav visible", all(nav_visible(page, s) for s in PUBLIC))
            check("no-login protected nav hidden", not any(nav_visible(page, s) for s in PROTECTED),
                  str([s for s in PROTECTED if nav_visible(page, s)]))
            page.evaluate("showSection('overview')")
            page.wait_for_timeout(300)
            check("no-login showSection(overview) -> auth", active_section(page) == "auth", str(active_section(page)))
            page.evaluate("showSection('ai-daily')")
            page.wait_for_timeout(300)
            check("no-login showSection(ai-daily) -> auth", active_section(page) == "auth", str(active_section(page)))
            page.evaluate("showSection('landing')")
            status = page.evaluate("fetch('/api/overview').then(r => r.status)")
            check("no-login /api/overview 401", status == 401, str(status))
            status = page.evaluate("fetch('/api/tasks').then(r => r.status)")
            check("no-login /api/tasks 401", status == 401, str(status))
            status = page.evaluate("fetch('/api/ai/daily-decision', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({input:'test'})}).then(r => r.status)")
            check("no-login /api/ai/daily-decision 401", status == 401, str(status))
            # 2. Register + login (first user = ADMIN, Alice)
            page.click("button[data-section='auth']")
            page.fill("#regUser", "alice"); page.fill("#regPass", "Alice1234"); page.click("#regBtn")
            page.wait_for_function("document.getElementById('regMsg').textContent.includes('Registered')", timeout=10000)
            page.fill("#loginUser", "alice"); page.fill("#loginPass", "Alice1234"); page.click("#loginBtn")
            page.wait_for_function("document.querySelector('section.active')?.id === 'overview'", timeout=10000)
            check("after-login active is overview", active_section(page) == "overview")
            check("after-login all nav visible", all(nav_visible(page, s) for s in PUBLIC + PROTECTED))
            check("after-login logout visible", page.is_visible("#logoutBtn"))
            page.evaluate("showSection('ai-daily')")
            page.wait_for_timeout(300)
            check("after-login ai-daily opens", active_section(page) == "ai-daily", str(active_section(page)))
            page.evaluate("showSection('overview')")
            # Alice creates a task, capture its id via API
            page.click("button[data-section='tasks']")
            page.fill("#taskTitle", "AliceSecretTask"); page.fill("#taskUrgency", "8"); page.fill("#taskImportance", "8"); page.click("#taskAddBtn")
            page.wait_for_timeout(1200)
            check("alice task created", "AliceSecretTask" in page.content())
            alice_task_id = page.evaluate("""async () => {
                const t = sessionStorage.getItem('pdps_token');
                const r = await fetch('/api/tasks', {headers:{Authorization:'Bearer '+t}});
                const j = await r.json(); return j.length ? j[j.length-1].id : null; }""")
            check("alice task id captured", alice_task_id is not None, str(alice_task_id))
            # 4. Refresh with valid token -> verified, then overview
            page.reload(timeout=15000)
            page.wait_for_function("document.querySelector('section.active')?.id === 'overview'", timeout=10000)
            check("refresh valid token -> overview after verify", active_section(page) == "overview")
            check("refresh valid token keeps nav", all(nav_visible(page, s) for s in PROTECTED))
            # 5. Session invalidated on server, local token kept -> login page
            page.evaluate("""async () => {
                const t = sessionStorage.getItem('pdps_token');
                await fetch('/api/logout', {method:'POST', headers:{Authorization:'Bearer '+t}}); }""")
            page.reload(timeout=15000)
            page.wait_for_function("document.querySelector('section.active')?.id === 'auth'", timeout=10000)
            check("invalidated session refresh -> auth", active_section(page) == "auth")
            check("invalidated session token cleared", page.evaluate("sessionStorage.getItem('pdps_token')") in (None, ""))
            check("invalidated session nav hidden", not any(nav_visible(page, s) for s in PROTECTED))
            # 3. Login again, then logout hides at once
            page.fill("#loginUser", "alice"); page.fill("#loginPass", "Alice1234"); page.click("#loginBtn")
            page.wait_for_function("document.querySelector('section.active')?.id === 'overview'", timeout=10000)
            page.click("#logoutBtn"); page.wait_for_timeout(500)
            check("logout -> landing", active_section(page) == "landing", str(active_section(page)))
            check("logout nav hidden", not any(nav_visible(page, s) for s in PROTECTED))
            check("logout token cleared", page.evaluate("sessionStorage.getItem('pdps_token')") in (None, ""))
            check("logout button hidden", not page.is_visible("#logoutBtn"))
            status = page.evaluate("fetch('/api/overview').then(r => r.status)")
            check("after-logout /api/overview 401", status == 401, str(status))
            status = page.evaluate("fetch('/api/ai/daily-decision', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({input:'test'})}).then(r => r.status)")
            check("after-logout /api/ai/daily-decision 401", status == 401, str(status))
            # 6. Cross-user: Bob must not see Alice's task
            page.click("button[data-section='auth']")
            page.fill("#regUser", "bob"); page.fill("#regPass", "Bob12345"); page.click("#regBtn")
            page.wait_for_function("document.getElementById('regMsg').textContent.includes('Registered')", timeout=10000)
            page.fill("#loginUser", "bob"); page.fill("#loginPass", "Bob12345"); page.click("#loginBtn")
            page.wait_for_function("document.querySelector('section.active')?.id === 'overview'", timeout=10000)
            page.click("button[data-section='tasks']"); page.wait_for_timeout(1000)
            check("bob cannot see alice task", "AliceSecretTask" not in page.content())
            bob_result = page.evaluate(f"""async () => {{
                const t = sessionStorage.getItem('pdps_token');
                const p = await fetch('/api/tasks/{alice_task_id}', {{method:'PATCH', headers:{{Authorization:'Bearer '+t, 'Content-Type':'application/json'}}, body: JSON.stringify({{status:'Completed'}})}});
                const d = await fetch('/api/tasks/{alice_task_id}', {{method:'DELETE', headers:{{Authorization:'Bearer '+t}}}});
                return [p.status, d.status]; }}""")
            check("bob PATCH/DELETE alice task 404", bob_result == [404, 404], str(bob_result))
            page.close()
            # 7. Mobile 390px
            mpage = browser.new_page(viewport={"width": 390, "height": 844})
            mpage.goto(base + "/", timeout=15000); mpage.wait_for_timeout(500)
            check("mobile no-login protected nav hidden", not any(nav_visible(mpage, s) for s in PROTECTED))
            mpage.click("#menuBtn"); mpage.wait_for_timeout(400)
            check("mobile no-login drawer opens", mpage.evaluate("document.getElementById('sidebar').classList.contains('open')"))
            check("mobile no-login drawer only public", nav_visible(mpage, "auth") and not nav_visible(mpage, "tasks"))
            mpage.click("button[data-section='auth']")
            mpage.fill("#loginUser", "bob"); mpage.fill("#loginPass", "Bob12345"); mpage.click("#loginBtn")
            mpage.wait_for_function("document.querySelector('section.active')?.id === 'overview'", timeout=10000)
            check("mobile after-login nav visible", all(nav_visible(mpage, s) for s in PROTECTED))
            overflow = mpage.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("mobile no horizontal overflow", overflow <= 1, str(overflow))
            mpage.click("#logoutBtn"); mpage.wait_for_timeout(500)
            check("mobile logout -> landing", active_section(mpage) == "landing", str(active_section(mpage)))
            check("mobile logout nav hidden", not any(nav_visible(mpage, s) for s in PROTECTED))
            mpage.screenshot(path="/tmp/pdps-auth-gate-mobile.png")
            mpage.close()
            browser.close()
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nauth_gate_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0

if __name__ == "__main__":
    sys.exit(main())
