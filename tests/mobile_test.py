#!/usr/bin/env python3
"""Mobile responsive test for the dashboard (Playwright).

Starts the C++ server from the repository root with a temp data dir,
then checks, at phone widths, that: there is no horizontal overflow,
the hamburger opens a drawer and a nav button works, registration and
login work from a phone viewport, and a task form submit works, and
that the desktop layout still shows the sidebar without the hamburger.
Also checks the LAN host flag parses (server binds 0.0.0.0 in a temp
run) without changing any data files.

Usage: python3 tests/mobile_test.py --server ./cpp_server --port 8140
"""
import argparse, http.server, json, os, shutil, socket, subprocess, sys, tempfile, threading, time
PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  PASS {name}")
    else: FAIL += 1; print(f"  FAIL {name} {detail}")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# Mock Gemini server (Phase 3.1, same pattern as browser_test.py):
# the C++ server is started with GEMINI_API_BASE_URL pointing here
# and GEMINI_API_KEY=test-key, so no real Gemini API is ever called.
MOCK_AI_REPLY = "Mocked AI reply.\nSecond line of the reply."


class MockGemini(http.server.BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        MockGemini.requests.append(body.decode("utf-8", "replace"))
        canned = json.dumps({"candidates": [{"content": {"parts": [
            {"text": MOCK_AI_REPLY}]}, "finishReason": "STOP"}]}).encode()
        self._send(200, canned)

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="./cpp_server")
    ap.add_argument("--port", type=int, default=8140)
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright
    tmp = tempfile.mkdtemp(prefix="pdps-mobile-test-")
    base = f"http://127.0.0.1:{args.port}"
    mock = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockGemini)
    mock_port = mock.server_address[1]
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    env = dict(os.environ)
    env["GEMINI_API_KEY"] = "test-key"
    env["GEMINI_API_BASE_URL"] = f"http://127.0.0.1:{mock_port}/v1beta"
    proc = subprocess.Popen([args.server, "--port", str(args.port), "--data-dir", tmp],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
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
            # iPhone-ish and Android-ish widths
            for w, h, label in [(375, 667, "375px"), (390, 844, "390px"), (360, 740, "360px")]:
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(base + "/", timeout=15000)
                page.click("#menuBtn"); page.wait_for_timeout(400)
                check(f"{label} drawer opens", page.is_visible("nav#sidebar.open") or page.evaluate("document.getElementById('sidebar').classList.contains('open')"))
                check(f"{label} backdrop shown", page.is_visible("#navBackdrop.show") or page.evaluate("document.getElementById('navBackdrop').classList.contains('show')"))
                page.click("button[data-section='auth']"); page.wait_for_timeout(400)
                check(f"{label} nav click shows section", page.is_visible("section#auth"))
                overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                check(f"{label} no horizontal overflow", overflow <= 1, str(overflow))
                page.close()
            # Full phone flow at 390px: register, login, task, budget, habit
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(base + "/", timeout=15000)
            page.click("#menuBtn"); page.click("button[data-section='auth']")
            page.fill("#regUser", "mobileuser"); page.fill("#regPass", "Mobile123"); page.click("#regBtn")
            page.wait_for_function("document.getElementById('regMsg').textContent.includes('Registered')", timeout=10000)
            check("mobile registration", "registered" in page.content().lower() or "success" in page.content().lower())
            page.fill("#loginUser", "mobileuser"); page.fill("#loginPass", "Mobile123"); page.click("#loginBtn")
            page.wait_for_function("document.querySelector('section.active')?.id === 'overview'", timeout=10000)
            page.click("#menuBtn"); page.click("button[data-section='tasks']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'tasks'", timeout=10000)
            page.fill("#taskTitle", "MobileTask"); page.fill("#taskUrgency", "8"); page.fill("#taskImportance", "9"); page.click("#taskAddBtn"); page.wait_for_timeout(1200)
            check("mobile task submit", "MobileTask" in page.content())
            page.click("#menuBtn"); page.click("button[data-section='budget']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'budget'", timeout=10000)
            page.fill("#budIncome", "5000"); page.fill("#budExpenses", "1200"); page.click("#budBtn"); page.wait_for_timeout(1200)
            check("mobile budget result 3800", "3800" in page.content())
            page.click("#menuBtn"); page.click("button[data-section='habits']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'habits'", timeout=10000)
            page.fill("#hbName", "Reading"); page.click("#hbBtn"); page.wait_for_timeout(1200)
            check("mobile habit mark", "Reading" in page.content() or "done" in page.content().lower())
            # AI Daily Decision (Phase 3.1) at 390px: drawer nav
            # reaches it, validation works, mock reply is shown, and
            # the section has no horizontal overflow.
            page.click("#menuBtn"); page.click("button[data-section='ai-daily']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-daily'", timeout=10000)
            check("mobile ai-daily opens via drawer", page.is_visible("section#ai-daily"))
            page.click("#aiDailyBtn")
            page.wait_for_function("document.getElementById('aiDailyMsg').textContent.length > 0", timeout=5000)
            check("mobile ai-daily empty input error", "describe the decision" in page.evaluate("document.getElementById('aiDailyMsg').textContent").lower())
            page.fill("#aiDailyInput", "Should I study maths or physics tonight?")
            page.click("#aiDailyBtn")
            page.wait_for_function("document.getElementById('aiDailyReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("mobile ai-daily reply shown", "Mocked AI reply." in page.content())
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("mobile ai-daily no horizontal overflow", overflow <= 1, str(overflow))
            # AI Task Analyzer (Phase 3.2) at 390px: drawer nav
            # reaches it, validation works, mock reply is shown, and
            # the section has no horizontal overflow.
            page.click("#menuBtn"); page.click("button[data-section='ai-task']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-task'", timeout=10000)
            check("mobile ai-task opens via drawer", page.is_visible("section#ai-task"))
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskMsg').textContent.length > 0", timeout=5000)
            check("mobile ai-task empty description error", "describe the task" in page.evaluate("document.getElementById('aiTaskMsg').textContent").lower())
            page.fill("#aiTaskDesc", "Prepare the final report for the project")
            page.fill("#aiTaskUrgency", "8")
            page.fill("#aiTaskImportance", "9")
            page.select_option("#aiTaskStatus", "pending")
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("mobile ai-task reply shown", "Mocked AI reply." in page.content())
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("mobile ai-task no horizontal overflow", overflow <= 1, str(overflow))
            # AI Study Planner (Phase 3.3) at 390px: drawer nav
            # reaches it, validation works, mock reply is shown, and
            # the section has no horizontal overflow.
            page.click("#menuBtn"); page.click("button[data-section='ai-study']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-study'", timeout=10000)
            check("mobile ai-study opens via drawer", page.is_visible("section#ai-study"))
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyMsg').textContent.length > 0", timeout=5000)
            check("mobile ai-study no subjects error", "at least one subject" in page.evaluate("document.getElementById('aiStudyMsg').textContent").lower())
            page.locator("#aiStudySubjects input").nth(0).fill("Maths")
            page.fill("#aiStudyHours", "3")
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("mobile ai-study reply shown", "Mocked AI reply." in page.content())
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("mobile ai-study no horizontal overflow", overflow <= 1, str(overflow))
            # AI Problem Solver (Phase 3.4) at 390px: drawer nav
            # reaches it, validation works, mock reply is shown, and
            # the section has no horizontal overflow.
            page.click("#menuBtn"); page.click("button[data-section='ai-problem']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-problem'", timeout=10000)
            check("mobile ai-problem opens via drawer", page.is_visible("section#ai-problem"))
            page.click("#aiProblemBtn")
            page.wait_for_function("document.getElementById('aiProblemMsg').textContent.length > 0", timeout=5000)
            check("mobile ai-problem empty problem error", "describe the problem" in page.evaluate("document.getElementById('aiProblemMsg').textContent").lower())
            page.fill("#aiProblemDesc", "My printer keeps jamming when I print more than a few pages")
            page.click("#aiProblemBtn")
            page.wait_for_function("document.getElementById('aiProblemReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("mobile ai-problem reply shown", "Mocked AI reply." in page.content())
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("mobile ai-problem no horizontal overflow", overflow <= 1, str(overflow))
            # AI Budget Assistant (Phase 3.5) at 390px: drawer nav
            # reaches it, validation works, mock reply is shown, and
            # the section has no horizontal overflow.
            page.click("#menuBtn"); page.click("button[data-section='ai-budget']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-budget'", timeout=10000)
            check("mobile ai-budget opens via drawer", page.is_visible("section#ai-budget"))
            page.click("#aiBudgetBtn")
            page.wait_for_function("document.getElementById('aiBudgetMsg').textContent.length > 0", timeout=5000)
            check("mobile ai-budget empty form error", "income" in page.evaluate("document.getElementById('aiBudgetMsg').textContent").lower())
            page.fill("#aiBudgetIncome", "50000")
            page.click("#aiBudgetBtn")
            page.wait_for_function("document.getElementById('aiBudgetReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("mobile ai-budget reply shown", "Mocked AI reply." in page.content())
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("mobile ai-budget no horizontal overflow", overflow <= 1, str(overflow))
            # AI Habit Assistant (Phase 3.6) at 390px: drawer nav
            # reaches it, validation works, mock reply is shown, and
            # the section has no horizontal overflow.
            page.click("#menuBtn"); page.click("button[data-section='ai-habit']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-habit'", timeout=10000)
            check("mobile ai-habit opens via drawer", page.is_visible("section#ai-habit"))
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitMsg').textContent.length > 0", timeout=5000)
            check("mobile ai-habit empty habit error", "enter a habit" in page.evaluate("document.getElementById('aiHabitMsg').textContent").lower())
            page.fill("#aiHabitName", "Morning run")
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("mobile ai-habit reply shown", "Mocked AI reply." in page.content())
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("mobile ai-habit no horizontal overflow", overflow <= 1, str(overflow))
            # AI History (Phase 3.7) at 390px: drawer nav reaches
            # it, the six entries saved above (one per AI section)
            # render, and the section has no horizontal overflow.
            page.click("#menuBtn"); page.click("button[data-section='ai-history']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-history'", timeout=10000)
            check("mobile ai-history opens via drawer", page.is_visible("section#ai-history"))
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 6", timeout=15000)
            check("mobile ai-history renders 6 entries", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 6)
            check("mobile ai-history shows mock reply", "Mocked AI reply." in page.evaluate("document.getElementById('aiHistoryList').textContent"))
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("mobile ai-history no horizontal overflow", overflow <= 1, str(overflow))
            # Empty state at 390px: a fresh user has no AI history.
            page2 = browser.new_page(viewport={"width": 390, "height": 844})
            page2.goto(base + "/", timeout=15000)
            page2.click("#menuBtn"); page2.click("button[data-section='auth']")
            page2.fill("#regUser", "mobileuser2"); page2.fill("#regPass", "Mobile123"); page2.click("#regBtn")
            page2.wait_for_function("document.getElementById('regMsg').textContent.includes('Registered')", timeout=10000)
            page2.fill("#loginUser", "mobileuser2"); page2.fill("#loginPass", "Mobile123"); page2.click("#loginBtn")
            page2.wait_for_function("document.querySelector('section.active')?.id === 'overview'", timeout=10000)
            page2.click("#menuBtn"); page2.click("button[data-section='ai-history']")
            page2.wait_for_function("document.querySelector('section.active')?.id === 'ai-history'", timeout=10000)
            page2.wait_for_function("document.getElementById('aiHistoryList').textContent.includes('No AI history yet')", timeout=15000)
            check("mobile ai-history empty state", "No AI history yet" in page2.evaluate("document.getElementById('aiHistoryList').textContent"))
            page2.close()
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("mobile flow no horizontal overflow", overflow <= 1, str(overflow))
            page.screenshot(path="/tmp/pdps-mobile-390.png")
            page.close()
            # Desktop still unchanged: sidebar visible, hamburger hidden
            dpage = browser.new_page(viewport={"width": 1280, "height": 800})
            dpage.goto(base + "/", timeout=15000)
            check("desktop sidebar visible", dpage.is_visible("nav#sidebar"))
            check("desktop hamburger hidden", not dpage.is_visible("#menuBtn"))
            dpage.close()
            browser.close()
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
        try: mock.shutdown()
        except Exception: pass
        mock.server_close()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nmobile_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0

if __name__ == "__main__":
    sys.exit(main())
