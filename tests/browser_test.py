#!/usr/bin/env python3
"""Playwright browser test for the dashboard.

Starts the C++ server from the repository root (so its static files
resolve), then drives a real Chromium browser through: landing page,
registration, login, every dashboard section, a form submit, theme
toggle, mobile viewport, and an unauthenticated protected-section
check. Screenshots are saved to the output directory.

Usage:
    python3 tests/browser_test.py --server ./cpp_server --port 8130 \
        --out screenshots

Requires: pip install playwright, plus a Chromium build installed
via `python3 -m playwright install chromium` (or a manually placed
headless-shell build). Exit code 0 = all checks passed.
"""
import argparse
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

PASS = 0
FAIL = 0
ERRORS = []


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# Mock Gemini server (Phase 3.1): the C++ server is started with
# GEMINI_API_BASE_URL pointing here and GEMINI_API_KEY=test-key, so
# no real Gemini API is ever called. The canned reply is multi-line
# on purpose, so the test also proves the UI keeps line breaks.
# If the prompt sent to the mock contains the trigger string
# MOCK-RATE-LIMIT, the mock answers 429, which the server maps to
# 503 "AI request limit reached" — the UI error path.
MOCK_AI_REPLY = "Mocked AI reply.\nSecond line of the reply."


class MockGemini(http.server.BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        text = body.decode("utf-8", "replace")
        MockGemini.requests.append(text)
        if "MOCK-RATE-LIMIT" in text:
            self._send(429, b'{"error":{"message":"quota exceeded"}}')
            return
        canned = json.dumps({"candidates": [{"content": {"parts": [
            {"text": MOCK_AI_REPLY}]}, "finishReason": "STOP"}]}).encode()
        self._send(200, canned)

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="./cpp_server")
    ap.add_argument("--port", type=int, default=8130)
    ap.add_argument("--out", default="screenshots")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    tmp = tempfile.mkdtemp(prefix="pdps-browser-test-")
    outdir = os.path.abspath(args.out)
    os.makedirs(outdir, exist_ok=True)
    base = f"http://127.0.0.1:{args.port}"
    mock = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockGemini)
    mock_port = mock.server_address[1]
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    env = dict(os.environ)
    env["GEMINI_API_KEY"] = "test-key"
    env["GEMINI_API_BASE_URL"] = f"http://127.0.0.1:{mock_port}/v1beta"
    proc = subprocess.Popen([args.server, "--port", str(args.port),
                             "--data-dir", tmp],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=env)
    try:
        for _ in range(30):
            try:
                import urllib.request
                with urllib.request.urlopen(base + "/", timeout=2) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.5)
        else:
            print("FAIL server did not start")
            return 1
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("pageerror", lambda e: ERRORS.append(str(e)))
            page.on("console", lambda m: ERRORS.append(m.text) if m.type == "error" else None)
            failed = []
            page.on("response", lambda r: failed.append(r.url) if r.status >= 400 and "/api/" in r.url else None)

            page.goto(base + "/", timeout=15000)
            check("landing page loads", "Decide better" in page.content())
            page.screenshot(path=os.path.join(outdir, "01-landing.png"))

            # Register: first user becomes ADMIN.
            page.click("button[data-section='auth']")
            page.fill("#regUser", "browseruser")
            page.fill("#regPass", "Browser123")
            page.click("#regBtn")
            # Do NOT use a fixed wait here: the C++ server's PBKDF2
            # (100k iterations, hand-written SHA-256) takes ~1.9s per
            # register/login on this VM, so a fixed 1500ms wait raced
            # with login and made "section auth visible" fail (32/33)
            # even though the product was correct. Wait for the actual
            # registration message instead (same lesson as mobile_test).
            page.wait_for_function("document.querySelector('#regMsg').textContent.includes('Registered')")
            check("registration message", "success" in page.content().lower() or "registered" in page.content().lower())

            # Login.
            page.fill("#loginUser", "browseruser")
            page.fill("#loginPass", "Browser123")
            page.click("#loginBtn")
            page.wait_for_function("document.querySelector('section.active').id === 'overview'")
            check("login leads to overview", page.evaluate("document.querySelector('section.active').id") == "overview")
            page.screenshot(path=os.path.join(outdir, "02-overview.png"))

            # Every section loads (click each nav button, section visible).
            sections = page.eval_on_selector_all(
                "button[data-section]",
                "els => els.map(e => e.dataset.section)")
            print(f"  sections found: {len(sections)}")
            for sec in sections:
                try:
                    page.click(f"button[data-section='{sec}']")
                    page.wait_for_timeout(300)
                    visible = page.is_visible(f"section#{sec}")
                    check(f"section {sec} visible", visible)
                except Exception as e:
                    check(f"section {sec} visible", False, str(e)[:100])
            page.screenshot(path=os.path.join(outdir, "03-tasks.png"))

            # Form submit: create a task, then check it appears.
            page.click("button[data-section='tasks']")
            page.fill("#taskTitle", "BrowserTask")
            page.fill("#taskUrgency", "8")
            page.fill("#taskImportance", "8")
            page.fill("#taskDeadline", "2026-11-20")
            page.click("#taskAddBtn")
            page.wait_for_timeout(1500)
            check("task form submit", "BrowserTask" in page.content())

            # Finance form: budget calculation.
            page.click("button[data-section='budget']")
            page.fill("#budIncome", "5000")
            page.fill("#budExpenses", "1200")
            page.click("#budBtn")
            page.wait_for_timeout(1500)
            check("budget result 3800", "3800" in page.content())

            # AI Daily Decision (Phase 3.1): client-side validation,
            # mock-Gemini success, newline sanitization, 503 and 400.
            page.click("button[data-section='ai-daily']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-daily'")
            check("ai-daily section visible after login", page.is_visible("section#ai-daily"))
            # Empty input -> client-side validation error, no API call.
            page.click("#aiDailyBtn")
            page.wait_for_function("document.getElementById('aiDailyMsg').textContent.length > 0")
            check("ai-daily empty input error", "describe the decision" in page.evaluate("document.getElementById('aiDailyMsg').textContent").lower())
            # Over 4000 BYTES -> error. 4001 ASCII chars is 4001
            # bytes; 1334 Bengali chars is 4002 bytes but only 1334
            # characters, so this also proves the limit counts bytes,
            # not characters.
            page.fill("#aiDailyInput", "x" * 4001)
            page.click("#aiDailyBtn")
            page.wait_for_function("document.getElementById('aiDailyMsg').textContent.includes('4000 bytes')")
            check("ai-daily input over 4000 bytes error", "4000 bytes" in page.evaluate("document.getElementById('aiDailyMsg').textContent"))
            page.fill("#aiDailyInput", "অ" * 1334)
            page.click("#aiDailyBtn")
            page.wait_for_function("document.getElementById('aiDailyMsg').textContent.includes('4000 bytes')")
            check("ai-daily Bengali 1334 chars over 4000 bytes error", "4000 bytes" in page.evaluate("document.getElementById('aiDailyMsg').textContent"))
            # Option over 500 bytes -> error.
            page.fill("#aiDailyInput", "Should I study maths or physics tonight?")
            page.click("#aiDailyAddOpt")
            page.fill("#aiDailyOptions .ai-opt-input", "y" * 501)
            page.click("#aiDailyBtn")
            page.wait_for_function("document.getElementById('aiDailyMsg').textContent.includes('500 bytes')")
            check("ai-daily option over 500 bytes error", "500 bytes" in page.evaluate("document.getElementById('aiDailyMsg').textContent"))
            # Success via the mock Gemini server, with options and a
            # multi-line input: the newlines must reach the mock as
            # spaces (the old JSON helper turns "\n" into "n").
            page.fill("#aiDailyOptions .ai-opt-input", "maths")
            page.click("#aiDailyAddOpt")
            page.locator("#aiDailyOptions .ai-opt-input").nth(1).fill("physics")
            page.fill("#aiDailyInput", "Should I study maths\nor physics tonight?")
            page.click("#aiDailyBtn")
            page.wait_for_function("document.getElementById('aiDailyReply').textContent.includes('Mocked AI reply.')")
            check("ai-daily mock reply shown", "Mocked AI reply." in page.content())
            check("ai-daily mock reply keeps line breaks", "Second line of the reply." in page.content())
            check("ai-daily history id shown", "history #" in page.evaluate("document.getElementById('aiDailyMsg').textContent"))
            check("ai-daily no history-save warning", page.evaluate("document.getElementById('aiDailyWarn').textContent") == "")
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-daily newline sent as space", "maths or physics" in sent and "mathsnor" not in sent, sent[:200])
            check("ai-daily options reach mock", "maths" in sent and "physics" in sent, sent[:200])
            # 503 via the mock rate-limit trigger: the UI shows the
            # server message and clears the stale reply.
            page.fill("#aiDailyInput", "MOCK-RATE-LIMIT test")
            page.click("#aiDailyBtn")
            page.wait_for_function("document.getElementById('aiDailyMsg').textContent.includes('AI request limit reached')")
            check("ai-daily 503 error shown", "AI request limit reached" in page.evaluate("document.getElementById('aiDailyMsg').textContent"))
            check("ai-daily 503 clears stale reply", page.evaluate("document.getElementById('aiDailyReply').textContent") == "")
            # 400 from the server (direct API call from the page: the
            # UI's own validation cannot produce one, by design).
            st = page.evaluate("""async () => {
                const t = sessionStorage.getItem('pdps_token');
                const r = await fetch('/api/ai/daily-decision', {method: 'POST',
                  headers: {Authorization: 'Bearer ' + t, 'Content-Type': 'application/json'},
                  body: JSON.stringify({input: '   '})});
                const j = await r.json().catch(() => ({}));
                return [r.status, j.error || '']; }""")
            check("ai-daily server 400 invalid input", st == [400, "invalid input"], str(st))

            # AI Task Analyzer (Phase 3.2): client-side validation,
            # mock-Gemini success, newline sanitization, 503 and 400.
            page.click("button[data-section='ai-task']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-task'")
            check("ai-task section visible after login", page.is_visible("section#ai-task"))
            # Empty description -> client-side validation error, no API call.
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskMsg').textContent.length > 0")
            check("ai-task empty description error", "describe the task" in page.evaluate("document.getElementById('aiTaskMsg').textContent").lower())
            # Over 4000 BYTES -> error. 4001 ASCII chars is 4001
            # bytes; 1334 Bengali chars is 4002 bytes but only 1334
            # characters, so this also proves the limit counts bytes,
            # not characters. Clear the message first so the wait
            # cannot pass on the stale text from the previous check.
            page.fill("#aiTaskDesc", "x" * 4001)
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskMsg').textContent.includes('4000 bytes')")
            check("ai-task description over 4000 bytes error", "4000 bytes" in page.evaluate("document.getElementById('aiTaskMsg').textContent"))
            page.evaluate("document.getElementById('aiTaskMsg').textContent = ''")
            page.fill("#aiTaskDesc", "অ" * 1334)
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskMsg').textContent.includes('4000 bytes')")
            check("ai-task Bengali 1334 chars over 4000 bytes error", "4000 bytes" in page.evaluate("document.getElementById('aiTaskMsg').textContent"))
            # Title over 500 bytes -> error.
            page.fill("#aiTaskDesc", "Prepare the final report")
            page.fill("#aiTaskTitle", "y" * 501)
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskMsg').textContent.includes('500 bytes')")
            check("ai-task title over 500 bytes error", "500 bytes" in page.evaluate("document.getElementById('aiTaskMsg').textContent"))
            # Urgency out of range (11) and non-integer (8.5) -> error.
            # Clear the message before the second one so the wait
            # cannot pass on the stale "1 to 10" text.
            page.fill("#aiTaskTitle", "")
            page.fill("#aiTaskUrgency", "11")
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskMsg').textContent.includes('1 to 10')")
            check("ai-task urgency 11 error", "1 to 10" in page.evaluate("document.getElementById('aiTaskMsg').textContent"))
            page.evaluate("document.getElementById('aiTaskMsg').textContent = ''")
            page.fill("#aiTaskUrgency", "8.5")
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskMsg').textContent.includes('1 to 10')")
            check("ai-task urgency 8.5 error", "1 to 10" in page.evaluate("document.getElementById('aiTaskMsg').textContent"))
            # Deadline over 100 bytes -> error.
            page.fill("#aiTaskUrgency", "")
            page.fill("#aiTaskDeadline", "z" * 101)
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskMsg').textContent.includes('100 bytes')")
            check("ai-task deadline over 100 bytes error", "100 bytes" in page.evaluate("document.getElementById('aiTaskMsg').textContent"))
            # Success via the mock Gemini server, with all fields and
            # a multi-line description: the newlines must reach the
            # mock as spaces (the old JSON helper turns "\n" into "n").
            page.fill("#aiTaskDeadline", "2026-11-20")
            page.fill("#aiTaskTitle", "Final report")
            page.fill("#aiTaskUrgency", "8")
            page.fill("#aiTaskImportance", "9")
            page.select_option("#aiTaskStatus", "in-progress")
            page.fill("#aiTaskDesc", "Prepare the final\nreport for the project")
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskReply').textContent.includes('Mocked AI reply.')")
            check("ai-task mock reply shown", "Mocked AI reply." in page.content())
            check("ai-task history id shown", "history #" in page.evaluate("document.getElementById('aiTaskMsg').textContent"))
            check("ai-task no history-save warning", page.evaluate("document.getElementById('aiTaskWarn').textContent") == "")
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-task newline sent as space", "final report" in sent and "finalreport" not in sent, sent[:200])
            check("ai-task fields reach mock", all(x in sent for x in ("Final report", "Urgency: 8", "Importance: 9", "Deadline", "2026-11-20", "in-progress")), sent[:300])
            # 503 via the mock rate-limit trigger: the UI shows the
            # server message and clears the stale reply.
            page.fill("#aiTaskDesc", "MOCK-RATE-LIMIT test")
            page.click("#aiTaskBtn")
            page.wait_for_function("document.getElementById('aiTaskMsg').textContent.includes('AI request limit reached')")
            check("ai-task 503 error shown", "AI request limit reached" in page.evaluate("document.getElementById('aiTaskMsg').textContent"))
            check("ai-task 503 clears stale reply", page.evaluate("document.getElementById('aiTaskReply').textContent") == "")
            # 400 from the server (direct API call from the page: the
            # UI's own validation cannot produce one, by design).
            st = page.evaluate("""async () => {
                const t = sessionStorage.getItem('pdps_token');
                const r = await fetch('/api/ai/task-analyzer', {method: 'POST',
                  headers: {Authorization: 'Bearer ' + t, 'Content-Type': 'application/json'},
                  body: JSON.stringify({description: '   '})});
                const j = await r.json().catch(() => ({}));
                return [r.status, j.error || '']; }""")
            check("ai-task server 400 invalid input", st == [400, "invalid input"], str(st))

            # Reports section screenshot, then dark mode.
            page.click("button[data-section='reports']")
            page.wait_for_timeout(800)
            page.screenshot(path=os.path.join(outdir, "04-reports.png"))
            page.click("#themeBtn")
            page.wait_for_timeout(500)
            theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
            check("dark mode toggle", theme == "dark", str(theme))
            page.screenshot(path=os.path.join(outdir, "05-dark-mode.png"))
            page.click("#themeBtn")
            page.wait_for_timeout(300)

            # Mobile viewport: sidebar hamburger, no horizontal overflow.
            mpage = browser.new_page(viewport={"width": 375, "height": 667})
            mpage.goto(base + "/", timeout=15000)
            mpage.click("#menuBtn")
            mpage.wait_for_timeout(500)
            overflow = mpage.evaluate(
                "document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("mobile no horizontal overflow", overflow <= 1, str(overflow))
            mpage.screenshot(path=os.path.join(outdir, "06-mobile.png"))
            mpage.close()

            # Unauthenticated: fresh context, protected API must be 401.
            ctx = browser.new_context()
            anon = ctx.new_page()
            anon.goto(base + "/", timeout=15000)
            status = anon.evaluate(
                "fetch('/api/overview').then(r => r.status)")
            check("unauthenticated overview 401", status == 401, str(status))
            ctx.close()

            # Chromium logs a console error for every failed fetch,
            # including the four intentional AI error calls (a 503 UI
            # test and a direct 400 fetch for each of ai-daily and
            # ai-task). Remove exactly those four expected messages
            # (two 503s, two 400s); any other console error still fails.
            remaining_console = list(ERRORS)
            for expected in ("status of 503", "status of 503", "status of 400", "status of 400"):
                for i, e in enumerate(remaining_console):
                    if "Failed to load resource" in e and expected in e:
                        del remaining_console[i]
                        break
            check("no JS page errors", len(remaining_console) == 0, str(remaining_console[:3]))
            # The intentionally-triggered AI error calls (the 503 UI
            # tests and direct 400 fetches above) are expected
            # failures; anything else is not.
            ai_errors = [u for u in failed if "/api/ai/" in u]
            unexpected = [u for u in failed if "/api/ai/" not in u]
            check("no unexpected failed API requests", len(unexpected) == 0, str(unexpected[:3]))
            check("ai error states recorded (expected)", len(ai_errors) >= 4, str(ai_errors))
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        try:
            mock.shutdown()
        except Exception:
            pass
        mock.server_close()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nbrowser_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
