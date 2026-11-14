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
from datetime import date, timedelta

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
            page.fill("#regPassConfirm", "Browser123")
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

            # Habit ring (Panze style): 0% on an empty log, then 3%
            # after marking one habit done today (1 of 30 days).
            page.click("button[data-section='habits']")
            page.wait_for_function("document.getElementById('hbRingCaption').textContent.length > 0")
            check("habit ring 0% on empty log", page.evaluate("document.getElementById('hbRingPct').textContent") == "0%")
            page.fill("#hbName", "RingHabit")
            page.fill("#hbDate", time.strftime("%Y-%m-%d", time.localtime()))
            page.click("#hbBtn")
            page.wait_for_function("document.getElementById('hbRingPct').textContent === '3%'")
            check("habit ring 3% after one day", page.evaluate("document.getElementById('hbRingPct').textContent") == "3%")
            check("habit ring caption 1 active day", "1 active day in the last 30 days" in page.evaluate("document.getElementById('hbRingCaption').textContent"))

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

            # AI Study Planner (Phase 3.3): client-side validation,
            # mock-Gemini success, subject dedup, newline
            # sanitization, 503 and 400.
            page.click("button[data-section='ai-study']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-study'")
            check("ai-study section visible after login", page.is_visible("section#ai-study"))
            # No subjects -> client-side validation error, no API call.
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyMsg').textContent.length > 0")
            check("ai-study no subjects error", "at least one subject" in page.evaluate("document.getElementById('aiStudyMsg').textContent").lower())
            # Subject over 200 bytes -> error.
            page.locator("#aiStudySubjects input").nth(0).fill("x" * 201)
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyMsg').textContent.includes('200 bytes')")
            check("ai-study subject over 200 bytes error", "200 bytes" in page.evaluate("document.getElementById('aiStudyMsg').textContent"))
            # Hours missing / 0 / 25 / exponent -> error. Clear the
            # message before each repeat so the wait cannot pass on
            # the stale "0.5 to 24" text from the previous check.
            page.locator("#aiStudySubjects input").nth(0).fill("Maths")
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyMsg').textContent.includes('0.5 to 24')")
            check("ai-study hours missing error", "0.5 to 24" in page.evaluate("document.getElementById('aiStudyMsg').textContent"))
            page.evaluate("document.getElementById('aiStudyMsg').textContent = ''")
            page.fill("#aiStudyHours", "0")
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyMsg').textContent.includes('0.5 to 24')")
            check("ai-study hours 0 error", "0.5 to 24" in page.evaluate("document.getElementById('aiStudyMsg').textContent"))
            page.evaluate("document.getElementById('aiStudyMsg').textContent = ''")
            page.fill("#aiStudyHours", "25")
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyMsg').textContent.includes('0.5 to 24')")
            check("ai-study hours 25 error", "0.5 to 24" in page.evaluate("document.getElementById('aiStudyMsg').textContent"))
            page.evaluate("document.getElementById('aiStudyMsg').textContent = ''")
            page.fill("#aiStudyHours", "1e3")
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyMsg').textContent.includes('0.5 to 24')")
            check("ai-study hours exponent error", "0.5 to 24" in page.evaluate("document.getElementById('aiStudyMsg').textContent"))
            # Past exam date -> error (yesterday, by the local date).
            page.fill("#aiStudyHours", "4")
            past = (date.today() - timedelta(days=1)).isoformat()
            page.fill("#aiStudyExam", past)
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyMsg').textContent.includes('today or in the future')")
            check("ai-study past exam date error", "today or in the future" in page.evaluate("document.getElementById('aiStudyMsg').textContent"))
            # Success via the mock Gemini server: duplicate subjects
            # are deduped client-side, hours sent as a number, exam
            # date and a multi-line description reach the mock.
            future = (date.today() + timedelta(days=30)).isoformat()
            page.click("#aiStudyAddSubject")
            page.click("#aiStudyAddSubject")
            page.locator("#aiStudySubjects input").nth(0).fill("Maths")
            page.locator("#aiStudySubjects input").nth(1).fill("maths")
            page.locator("#aiStudySubjects input").nth(2).fill("Physics")
            page.fill("#aiStudyExam", future)
            page.fill("#aiStudyDesc", "Plan my revision\nfor the exam")
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyReply').textContent.includes('Mocked AI reply.')")
            check("ai-study mock reply shown", "Mocked AI reply." in page.content())
            check("ai-study history id shown", "history #" in page.evaluate("document.getElementById('aiStudyMsg').textContent"))
            check("ai-study 2 unique subjects shown", "(2 subjects)" in page.evaluate("document.getElementById('aiStudyMsg').textContent"))
            check("ai-study duplicate note shown", "duplicate" in page.evaluate("document.getElementById('aiStudyWarn').textContent").lower())
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-study newline sent as space", "revision for the exam" in sent and "revisionfor" not in sent, sent[:200])
            # The mock body is JSON-encoded, so the prompt's quotes
            # arrive escaped (\"Maths\"); match the bare subject
            # names, as the 3.1/3.2 checks do.
            check("ai-study subjects deduped in prompt", sent.count('Maths') == 1 and 'Physics' in sent, sent[:300])
            check("ai-study fields reach mock", all(x in sent for x in ("Hours per day: 4", "Exam date:", future)), sent[:300])
            # 503 via the mock rate-limit trigger: the UI shows the
            # server message and clears the stale reply.
            page.fill("#aiStudyDesc", "MOCK-RATE-LIMIT test")
            page.click("#aiStudyBtn")
            page.wait_for_function("document.getElementById('aiStudyMsg').textContent.includes('AI request limit reached')")
            check("ai-study 503 error shown", "AI request limit reached" in page.evaluate("document.getElementById('aiStudyMsg').textContent"))
            check("ai-study 503 clears stale reply", page.evaluate("document.getElementById('aiStudyReply').textContent") == "")
            # 400 from the server (direct API call from the page: the
            # UI's own validation cannot produce one, by design).
            st = page.evaluate("""async () => {
                const t = sessionStorage.getItem('pdps_token');
                const r = await fetch('/api/ai/study-planner', {method: 'POST',
                  headers: {Authorization: 'Bearer ' + t, 'Content-Type': 'application/json'},
                  body: JSON.stringify({})});
                const j = await r.json().catch(() => ({}));
                return [r.status, j.error || '']; }""")
            check("ai-study server 400 invalid input", st == [400, "invalid input"], str(st))

            # AI Problem Solver (Phase 3.4): client-side validation,
            # mock-Gemini success, newline sanitization, 503 and 400.
            # The limit counts UTF-8 CODE POINTS, not bytes: 4000
            # Bengali chars is about 12000 bytes and must still pass.
            page.click("button[data-section='ai-problem']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-problem'")
            check("ai-problem section visible after login", page.is_visible("section#ai-problem"))
            # Empty problem -> client-side validation error, no API call.
            page.click("#aiProblemBtn")
            page.wait_for_function("document.getElementById('aiProblemMsg').textContent.length > 0")
            check("ai-problem empty problem error", "describe the problem" in page.evaluate("document.getElementById('aiProblemMsg').textContent").lower())
            # Over 4000 CODE POINTS -> error. 4001 ASCII chars is 4001
            # code points; 4001 Bengali chars is 4001 code points but
            # about 12003 bytes, so this also proves the limit counts
            # characters, not bytes. Clear the message first so the
            # wait cannot pass on stale text from the previous check.
            page.fill("#aiProblemDesc", "x" * 4001)
            page.click("#aiProblemBtn")
            page.wait_for_function("document.getElementById('aiProblemMsg').textContent.includes('4000 characters')")
            check("ai-problem problem over 4000 code points error", "4000 characters" in page.evaluate("document.getElementById('aiProblemMsg').textContent"))
            page.evaluate("document.getElementById('aiProblemMsg').textContent = ''")
            page.fill("#aiProblemDesc", "অ" * 4001)
            page.click("#aiProblemBtn")
            page.wait_for_function("document.getElementById('aiProblemMsg').textContent.includes('4000 characters')")
            check("ai-problem Bengali 4001 chars over 4000 code points error", "4000 characters" in page.evaluate("document.getElementById('aiProblemMsg').textContent"))
            # 4000 Bengali chars (about 12000 bytes) is VALID and must
            # reach the mock — this is the code-point proof. The
            # success message shows the history id, no warning.
            page.fill("#aiProblemDesc", "অ" * 4000)
            page.click("#aiProblemBtn")
            page.wait_for_function("document.getElementById('aiProblemReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("ai-problem Bengali 4000 chars mock reply shown", "Mocked AI reply." in page.content())
            check("ai-problem history id shown", "history #" in page.evaluate("document.getElementById('aiProblemMsg').textContent"))
            check("ai-problem no history-save warning", page.evaluate("document.getElementById('aiProblemWarn').textContent") == "")
            # Newline sanitization: a multi-line problem reaches the
            # mock with newlines as spaces.
            page.fill("#aiProblemDesc", "Fix the printer\nin my office")
            page.click("#aiProblemBtn")
            page.wait_for_function("document.getElementById('aiProblemReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("ai-problem mock reply shown", "Mocked AI reply." in page.content())
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-problem newline sent as space", "printer in my office" in sent and "printerin" not in sent, sent[:200])
            check("ai-problem fields reach mock", "Fix the printer in my office" in sent, sent[:300])
            # 503 via the mock rate-limit trigger: the UI shows the
            # server message and clears the stale reply.
            page.fill("#aiProblemDesc", "MOCK-RATE-LIMIT test")
            page.click("#aiProblemBtn")
            page.wait_for_function("document.getElementById('aiProblemMsg').textContent.includes('AI request limit reached')")
            check("ai-problem 503 error shown", "AI request limit reached" in page.evaluate("document.getElementById('aiProblemMsg').textContent"))
            check("ai-problem 503 clears stale reply", page.evaluate("document.getElementById('aiProblemReply').textContent") == "")
            # 400 from the server (direct API call from the page: the
            # UI's own validation cannot produce one, by design).
            st = page.evaluate("""async () => {
                const t = sessionStorage.getItem('pdps_token');
                const r = await fetch('/api/ai/problem-solver', {method: 'POST',
                  headers: {Authorization: 'Bearer ' + t, 'Content-Type': 'application/json'},
                  body: JSON.stringify({problem: '   '})});
                const j = await r.json().catch(() => ({}));
                return [r.status, j.error || '']; }""")
            check("ai-problem server 400 invalid input", st == [400, "invalid input"], str(st))

            # AI Budget Assistant (Phase 3.5): client-side validation,
            # mock-Gemini success, income 0 counts, goal all-three
            # rule, 503 and 400. Numbers are sent as JSON numbers.
            page.click("button[data-section='ai-budget']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-budget'")
            check("ai-budget section visible after login", page.is_visible("section#ai-budget"))
            # Empty form -> client-side validation error, no API call.
            page.click("#aiBudgetBtn")
            page.wait_for_function("document.getElementById('aiBudgetMsg').textContent.length > 0")
            check("ai-budget empty form error", "income" in page.evaluate("document.getElementById('aiBudgetMsg').textContent").lower())
            # Savings goal with only the name -> all-three error.
            page.fill("#aiBudgetGoalName", "Laptop")
            page.click("#aiBudgetBtn")
            page.wait_for_function("document.getElementById('aiBudgetMsg').textContent.includes('all three')")
            check("ai-budget goal partial error", "all three" in page.evaluate("document.getElementById('aiBudgetMsg').textContent"))
            page.fill("#aiBudgetGoalName", "")
            # Income 0 alone is meaningful and must reach the mock:
            # the server computes "Total income: 0.00" from it.
            page.fill("#aiBudgetIncome", "0")
            page.click("#aiBudgetBtn")
            page.wait_for_function("document.getElementById('aiBudgetReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("ai-budget income 0 mock reply shown", "Mocked AI reply." in page.content())
            check("ai-budget history id shown", "history #" in page.evaluate("document.getElementById('aiBudgetMsg').textContent"))
            check("ai-budget no history-save warning", page.evaluate("document.getElementById('aiBudgetWarn').textContent") == "")
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-budget income 0 reaches mock", "Total income: 0.00" in sent, sent[:300])
            # One expense row: category + amount reach the mock as
            # "Food: 1200.00" in the server-computed prompt.
            page.locator("#aiBudgetExpenses .ai-exp-category").nth(0).fill("Food")
            page.locator("#aiBudgetExpenses .ai-exp-amount").nth(0).fill("1200")
            page.click("#aiBudgetBtn")
            page.wait_for_function("document.getElementById('aiBudgetReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("ai-budget expense mock reply shown", "Mocked AI reply." in page.content())
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-budget expense reaches mock", "Food: 1200.00" in sent, sent[:300])
            # Savings goal, all three fields: the goal reaches the
            # mock as "Laptop (target 100000.00, saved 25000.00)".
            page.fill("#aiBudgetGoalName", "Laptop")
            page.fill("#aiBudgetGoalTarget", "100000")
            page.fill("#aiBudgetGoalSaved", "25000")
            page.click("#aiBudgetBtn")
            page.wait_for_function("document.getElementById('aiBudgetReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("ai-budget goal mock reply shown", "Mocked AI reply." in page.content())
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-budget goal reaches mock", "Laptop (target 100000.00, saved 25000.00)" in sent, sent[:300])
            # 503 via the mock rate-limit trigger: the UI shows the
            # server message and clears the stale reply.
            page.fill("#aiBudgetInput", "MOCK-RATE-LIMIT test")
            page.click("#aiBudgetBtn")
            page.wait_for_function("document.getElementById('aiBudgetMsg').textContent.includes('AI request limit reached')")
            check("ai-budget 503 error shown", "AI request limit reached" in page.evaluate("document.getElementById('aiBudgetMsg').textContent"))
            check("ai-budget 503 clears stale reply", page.evaluate("document.getElementById('aiBudgetReply').textContent") == "")
            # 400 from the server (direct API call from the page: the
            # UI's own validation cannot produce one, by design).
            st = page.evaluate("""async () => {
                const t = sessionStorage.getItem('pdps_token');
                const r = await fetch('/api/ai/budget', {method: 'POST',
                  headers: {Authorization: 'Bearer ' + t, 'Content-Type': 'application/json'},
                  body: JSON.stringify({})});
                const j = await r.json().catch(() => ({}));
                return [r.status, j.error || '']; }""")
            check("ai-budget server 400 invalid input", st == [400, "invalid input"], str(st))

            # AI Habit Assistant (Phase 3.6): client-side validation,
            # mock-Gemini success, daily/weekly streaks, reference
            # date, 503 and 400. The server computes the streak from
            # the caller's own (empty, in this fresh test) habit log.
            page.click("button[data-section='ai-habit']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-habit'")
            check("ai-habit section visible after login", page.is_visible("section#ai-habit"))
            # Empty habit -> client-side validation error, no API call.
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitMsg').textContent.length > 0")
            check("ai-habit empty habit error", "enter a habit" in page.evaluate("document.getElementById('aiHabitMsg').textContent").lower())
            # Habit with | -> client-side error (the server rejects it).
            page.fill("#aiHabitName", "Run|Swim")
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitMsg').textContent.includes('|')")
            check("ai-habit pipe error", "|" in page.evaluate("document.getElementById('aiHabitMsg').textContent"))
            # Target streak 0 -> error; 366 -> error; 2.5 -> error.
            page.fill("#aiHabitName", "Morning run")
            page.fill("#aiHabitTarget", "0")
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitMsg').textContent.includes('1 to 365')")
            check("ai-habit target 0 error", "1 to 365" in page.evaluate("document.getElementById('aiHabitMsg').textContent"))
            page.fill("#aiHabitTarget", "366")
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitMsg').textContent.includes('1 to 365')")
            check("ai-habit target 366 error", "1 to 365" in page.evaluate("document.getElementById('aiHabitMsg').textContent"))
            page.fill("#aiHabitTarget", "2.5")
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitMsg').textContent.includes('1 to 365')")
            check("ai-habit target 2.5 error", "1 to 365" in page.evaluate("document.getElementById('aiHabitMsg').textContent"))
            # Habit over 100 characters -> error.
            page.fill("#aiHabitTarget", "")
            page.fill("#aiHabitName", "x" * 101)
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitMsg').textContent.includes('100 characters')")
            check("ai-habit name too long error", "100 characters" in page.evaluate("document.getElementById('aiHabitMsg').textContent"))
            # Daily habit, target 30: mock reply; the server-computed
            # figures reach the mock (fresh log: streak 0 days).
            page.fill("#aiHabitName", "Morning run")
            page.fill("#aiHabitTarget", "30")
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("ai-habit mock reply shown", "Mocked AI reply." in page.content())
            check("ai-habit history id shown", "history #" in page.evaluate("document.getElementById('aiHabitMsg').textContent"))
            check("ai-habit no history-save warning", page.evaluate("document.getElementById('aiHabitWarn').textContent") == "")
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-habit reaches mock", all(x in sent for x in ("Habit: Morning run", "Frequency: daily", "Current streak: 0 days", "Target streak: 30 days")), sent[:300])
            # Weekly frequency: the mock sees weekly figures.
            page.select_option("#aiHabitFrequency", "weekly")
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("ai-habit weekly mock reply shown", "Mocked AI reply." in page.content())
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-habit weekly reaches mock", all(x in sent for x in ("Frequency: weekly", "Current streak: 0 weeks", "8-week completion rate")), sent[:300])
            # Reference date = today: the mock sees it as the
            # reference date (server date is the same machine's).
            page.select_option("#aiHabitFrequency", "daily")
            page.fill("#aiHabitToday", date.today().isoformat())
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitReply').textContent.includes('Mocked AI reply.')", timeout=15000)
            check("ai-habit today mock reply shown", "Mocked AI reply." in page.content())
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-habit today reaches mock", ("Reference date: " + date.today().isoformat()) in sent, sent[:300])
            # Reference date 3 days away -> client-side error.
            page.fill("#aiHabitToday", (date.today() + timedelta(days=3)).isoformat())
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitMsg').textContent.includes('within 2 days')")
            check("ai-habit today too far error", "within 2 days" in page.evaluate("document.getElementById('aiHabitMsg').textContent"))
            page.fill("#aiHabitToday", "")
            # 503 via the mock rate-limit trigger: the UI shows the
            # server message and clears the stale reply.
            page.fill("#aiHabitInput", "MOCK-RATE-LIMIT test")
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitMsg').textContent.includes('AI request limit reached')")
            check("ai-habit 503 error shown", "AI request limit reached" in page.evaluate("document.getElementById('aiHabitMsg').textContent"))
            check("ai-habit 503 clears stale reply", page.evaluate("document.getElementById('aiHabitReply').textContent") == "")
            # 400 from the server (direct API call from the page: the
            # UI's own validation cannot produce one, by design).
            st = page.evaluate("""async () => {
                const t = sessionStorage.getItem('pdps_token');
                const r = await fetch('/api/ai/habit', {method: 'POST',
                  headers: {Authorization: 'Bearer ' + t, 'Content-Type': 'application/json'},
                  body: JSON.stringify({habit: '   '})});
                const j = await r.json().catch(() => ({}));
                return [r.status, j.error || '']; }""")
            check("ai-habit server 400 invalid input", st == [400, "invalid input"], str(st))

            # AI History (Phase 3.7): list renders newest-first,
            # filter narrows it, delete removes an entry (with a
            # confirm dialog), logout clears the list, re-login
            # reloads it, and the empty state shows once all
            # entries are gone. The six AI sections above saved
            # 11 entries in total (daily 1, task 1, study 1,
            # problem 2, budget 3, habit 3); only successful
            # Gemini calls save history, so the 503/400 calls
            # above added none. Only successful GET/DELETE calls
            # are used here, so the console-error filter below
            # (six 503s + six 400s) is unchanged.
            page.click("button[data-section='ai-history']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-history'")
            check("ai-history section visible after login", page.is_visible("section#ai-history"))
            check("ai-history filter options", page.evaluate("document.querySelectorAll('#aiHistoryFilter option').length") == 7)
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 11", timeout=15000)
            check("ai-history renders 11 entries", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 11)
            first = page.evaluate("document.querySelector('.ai-history-entry').textContent")
            check("ai-history newest first is habit", "Habit" in first and "Morning run" in first, first[:200])
            check("ai-history newest shows mock reply", "Mocked AI reply." in first, first[:200])
            # Filter: daily-decision has 1 entry, habit has 3,
            # all has 11. The filter re-renders without a call.
            page.select_option("#aiHistoryFilter", "daily-decision")
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 1")
            check("ai-history filter daily-decision shows 1", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 1)
            check("ai-history filter daily-decision label", "Daily Decision" in page.evaluate("document.querySelector('.ai-history-entry').textContent"))
            page.select_option("#aiHistoryFilter", "habit")
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 3")
            check("ai-history filter habit shows 3", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 3)
            page.select_option("#aiHistoryFilter", "all")
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 11")
            check("ai-history filter all shows 11", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 11)
            # Delete one entry via the UI (confirm dialog auto-accepted).
            page.on("dialog", lambda d: d.accept())
            page.locator(".ai-history-entry .btn-danger").first.click()
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 10")
            check("ai-history delete removes entry", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 10)
            check("ai-history delete message", "Entry deleted" in page.evaluate("document.getElementById('aiHistoryMsg').textContent"))
            # Logout clears the rendered list at once.
            page.click("#logoutBtn")
            page.wait_for_function("document.querySelector('section.active')?.id === 'landing'")
            check("ai-history logout clears list", page.evaluate("document.getElementById('aiHistoryList').innerHTML") == "")
            # Log back in: the list reloads (10 entries left).
            page.click("button[data-section='auth']")
            page.fill("#loginUser", "browseruser")
            page.fill("#loginPass", "Browser123")
            page.click("#loginBtn")
            page.wait_for_function("document.querySelector('section.active')?.id === 'overview'", timeout=10000)
            page.click("button[data-section='ai-history']")
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 10", timeout=15000)
            check("ai-history reloads after re-login", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 10)
            # Delete the remaining entries via the API (all 200s,
            # so no console error is added), then reload the
            # section: the empty state must show.
            remaining = page.evaluate("""async () => {
                const t = sessionStorage.getItem('pdps_token');
                const r = await fetch('/api/ai/history?limit=50', {headers:{Authorization:'Bearer '+t}});
                const j = await r.json();
                for (const e of j.history) { await fetch('/api/ai/history/' + e.id, {method:'DELETE', headers:{Authorization:'Bearer '+t}}); }
                return j.history.length; }""")
            check("ai-history api deletes remaining", remaining == 10, str(remaining))
            page.click("button[data-section='ai-history']")
            page.wait_for_function("document.getElementById('aiHistoryList').textContent.includes('No AI history yet')", timeout=15000)
            check("ai-history empty state", "No AI history yet" in page.evaluate("document.getElementById('aiHistoryList').textContent"))

            # Reports section screenshot, then theme toggle.
            # The Panze redesign makes light the default theme, so
            # a fresh context starts light: one toggle click goes
            # to dark, a second click back to light.
            page.click("button[data-section='reports']")
            page.wait_for_timeout(800)
            page.screenshot(path=os.path.join(outdir, "04-reports.png"))
            check("default theme is light", page.evaluate("document.documentElement.getAttribute('data-theme')") == "light", str(page.evaluate("document.documentElement.getAttribute('data-theme')")))
            page.click("#themeBtn")
            page.wait_for_timeout(500)
            theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
            check("theme toggle to dark", theme == "dark", str(theme))
            page.screenshot(path=os.path.join(outdir, "05-theme-toggle.png"))
            page.click("#themeBtn")
            page.wait_for_timeout(300)
            theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
            check("theme toggle back to light", theme == "light", str(theme))

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
            # including the twelve intentional AI error calls (a 503 UI
            # test and a direct 400 fetch for each of ai-daily,
            # ai-task, ai-study, ai-problem, ai-budget and ai-habit).
            # Remove exactly those twelve expected messages (six
            # 503s, six 400s); any other console error still fails.
            remaining_console = list(ERRORS)
            for expected in ("status of 503", "status of 503", "status of 503", "status of 503", "status of 503", "status of 503", "status of 400", "status of 400", "status of 400", "status of 400", "status of 400", "status of 400"):
                for i, e in enumerate(remaining_console):
                    if "Failed to load resource" in e and expected in e:
                        del remaining_console[i]
                        break
            # Google Sign-In (Phase 3): the page loads the optional
            # Google Identity Services script from
            # accounts.google.com. In an offline or proxy-blocked
            # environment the tunnel to Google fails and Chromium
            # logs "Failed to load resource:
            # net::ERR_TUNNEL_CONNECTION_FAILED" for that script.
            # That is an expected, handled degradation — the page
            # hides the Google buttons when the script never
            # arrives — not a page error. Remove exactly that
            # proxy-failure message (the local test server is
            # localhost, so no other resource can produce it).
            remaining_console = [e for e in remaining_console
                                 if "ERR_TUNNEL_CONNECTION_FAILED" not in e]
            check("no JS page errors", len(remaining_console) == 0, str(remaining_console[:3]))
            # The intentionally-triggered AI error calls (the 503 UI
            # tests and direct 400 fetches above) are expected
            # failures; anything else is not.
            ai_errors = [u for u in failed if "/api/ai/" in u]
            unexpected = [u for u in failed if "/api/ai/" not in u]
            check("no unexpected failed API requests", len(unexpected) == 0, str(unexpected[:3]))
            check("ai error states recorded (expected)", len(ai_errors) >= 12, str(ai_errors))
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
