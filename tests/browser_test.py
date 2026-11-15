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
    # Test-controlled response delay (seconds). The pins loader
    # checks set this to hold the AI call in flight while they
    # inspect the loader. A route-level sleep cannot do this:
    # time.sleep in a Playwright route handler blocks the sync
    # API's event loop, so no check can run during the delay and
    # the busy window closes before the checks execute. The mock
    # runs on its own thread, so this sleep blocks nothing else.
    delay = 0.0

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        text = body.decode("utf-8", "replace")
        MockGemini.requests.append(text)
        if MockGemini.delay:
            time.sleep(MockGemini.delay)
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


def chart_data(page, selector):
    """Read a Chart.js chart's labels + dataset data from its canvas.

    Returns {"labels": [...], "data": [[...], ...]} or None when the
    canvas has no live chart (Chart.js not loaded, or the section
    rendered an empty state instead). Chart data is available the
    moment the chart is created, so these checks never race the
    chart's entrance animation.
    """
    return page.evaluate("""(sel) => {
        const cv = document.querySelector(sel);
        if (!cv || typeof Chart === 'undefined') return null;
        const ch = Chart.getChart(cv);
        if (!ch) return null;
        return { labels: ch.data.labels,
                 data: ch.data.datasets.map(d => d.data) };
    }""", selector)


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
            check("register hint explains username and password rules",
                  page.is_visible("#regHint")
                  and "no spaces" in page.evaluate("document.getElementById('regHint').textContent")
                  and "8 characters" in page.evaluate("document.getElementById('regHint').textContent"))
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

            # Transaction form: add one, the Delete button appears.
            page.click("button[data-section='finance']")
            page.fill("#txDate", "2026-11-15")
            page.fill("#txCategory", "BrowserTx")
            page.fill("#txAmount", "100")
            page.fill("#txNote", "Browser")
            page.click("#txBtn")
            page.wait_for_timeout(1500)
            check("transaction Delete button present",
                  page.locator("#txList button.btn-danger").count() > 0)
            check("transaction Edit button present",
                  page.locator("#txList button.btn-secondary").count() > 0)

            # Savings form: add a goal, the Edit button appears.
            page.click("button[data-section='savings']")
            page.fill("#svName", "BrowserGoal")
            page.fill("#svTarget", "1000")
            page.click("#svBtn")
            page.wait_for_timeout(1500)
            check("savings Edit button present",
                  page.locator("#svList button.btn-secondary").count() > 0)

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

            # Study Planner upgrade: saved plan via the UI, reload
            # persistence, per-day tick with Smart Revision, countdown
            # plan, validation, delete.
            page.click("button[data-section='study']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'study'")
            page.fill("#spSubject", "BrowserMaths")
            page.fill("#spDays", "3")
            page.fill("#spHours", "2")
            page.click("#spBtn")
            page.wait_for_function("document.getElementById('spList').textContent.includes('BrowserMaths')")
            check("study plan create via UI",
                  "BrowserMaths" in page.evaluate("document.getElementById('spList').textContent")
                  and "0/3 (0%)" in page.evaluate("document.getElementById('spList').textContent"))
            page.reload()
            page.wait_for_function("document.querySelector('section.active')?.id === 'overview'")
            page.click("button[data-section='study']")
            page.wait_for_function("document.getElementById('spList').textContent.includes('BrowserMaths')")
            check("study plan persists after reload",
                  "BrowserMaths" in page.evaluate("document.getElementById('spList').textContent"))
            page.locator("#spList .sp-plan input[type=checkbox]").first.check()
            page.wait_for_function("document.getElementById('spList').textContent.includes('1/6 (17%)')")
            check("study plan tick updates progress",
                  "1/6 (17%)" in page.evaluate("document.getElementById('spList').textContent"))
            check("study plan revisions appear after tick",
                  page.evaluate("document.getElementById('spList').textContent").count("Revision") == 3)
            # Countdown plan: exam 5 days out, 2 topics.
            import datetime as _dt
            _exam = (_dt.date.today() + _dt.timedelta(days=5)).isoformat()
            page.fill("#spSubject", "BrowserPhysics")
            page.fill("#spHours", "3")
            page.fill("#spExamDate", _exam)
            page.locator("#spTopics .ai-opt-input").first.fill("Algebra")
            page.click("#spAddTopic")
            page.locator("#spTopics .ai-opt-input").nth(1).fill("Geometry")
            page.click("#spBtn")
            page.wait_for_function("document.getElementById('spList').textContent.includes('BrowserPhysics')")
            check("study plan countdown via UI",
                  "(countdown plan)" in page.evaluate("document.getElementById('spList').textContent")
                  and _exam in page.evaluate("document.getElementById('spList').textContent"))
            check("study plan countdown 5 days",
                  "0/5 (0%)" in page.evaluate("document.getElementById('spList').textContent"))
            page.click("#spBtn")
            page.wait_for_function("document.getElementById('spMsg').textContent.length > 0")
            check("study plan empty subject error",
                  "subject" in page.evaluate("document.getElementById('spMsg').textContent").lower())
            page.on("dialog", lambda d: d.accept())
            page.locator("#spList .sp-plan button.btn-danger").first.click()
            page.wait_for_function("!document.getElementById('spList').textContent.includes('BrowserMaths')")
            check("study plan delete via UI",
                  "BrowserMaths" not in page.evaluate("document.getElementById('spList').textContent")
                  and "BrowserPhysics" in page.evaluate("document.getElementById('spList').textContent"))

            # Dashboard graphics: seed richer real data, then check
            # every chart renders from it (never sample data).
            # Second task, completed: 1 done + 1 pending of 2.
            page.click("button[data-section='tasks']")
            page.fill("#taskTitle", "BrowserTask2")
            page.fill("#taskUrgency", "5")
            page.fill("#taskImportance", "5")
            page.fill("#taskDeadline", "2026-11-25")
            page.click("#taskAddBtn")
            page.wait_for_function("document.getElementById('taskList').textContent.includes('BrowserTask2')")
            page.locator("#taskList button.btn-primary").nth(1).click()
            page.wait_for_function("document.getElementById('taskList').textContent.includes('Completed')")
            # Transactions: income 5100 total (100 + 5000), expense
            # 1500 (Food 1200, Transport 300), remaining 3600.
            page.click("button[data-section='finance']")
            for typ, cat, amt in [("income", "Salary", "5000"),
                                  ("expense", "Food", "1200"),
                                  ("expense", "Transport", "300")]:
                page.fill("#txDate", "2026-11-15")
                page.select_option("#txType", typ)
                page.fill("#txCategory", cat)
                page.fill("#txAmount", amt)
                page.fill("#txNote", "Graphics")
                page.click("#txBtn")
                page.wait_for_function(f"document.getElementById('txList').textContent.includes('{cat}')")
            # Savings: add 250 to BrowserGoal -> 250/1000 = 25%.
            page.click("button[data-section='savings']")
            page.fill("#svAddName", "BrowserGoal")
            page.fill("#svAddAmount", "250")
            page.click("#svAddBtn")
            page.wait_for_function("document.getElementById('svAddMsg').textContent.includes('250')")
            # Habits: RingHabit on yesterday and 2 days ago -> 3 of
            # the last 7 days, streak 3, 3 active days in 30.
            page.click("button[data-section='habits']")
            page.fill("#hbName", "RingHabit")
            page.fill("#hbDate", (date.today() - timedelta(days=1)).isoformat())
            page.click("#hbBtn")
            page.wait_for_function("document.getElementById('hbRingCaption').textContent.includes('2 active days')")
            page.fill("#hbName", "RingHabit")
            page.fill("#hbDate", (date.today() - timedelta(days=2)).isoformat())
            page.click("#hbBtn")
            page.wait_for_function("document.getElementById('hbRingCaption').textContent.includes('3 active days')")
            # Study: small plan, tick day 1 -> 1/5 (20%) + 3 revisions.
            page.click("button[data-section='study']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'study'")
            page.fill("#spSubject", "BrowserArt")
            page.fill("#spDays", "2")
            page.fill("#spHours", "1")
            page.click("#spBtn")
            page.wait_for_function("document.getElementById('spList').textContent.includes('BrowserArt')")
            page.locator("#spList .sp-plan", has_text="BrowserArt").locator("input[type=checkbox]").first.check()
            page.wait_for_function("document.getElementById('spList').textContent.includes('1/5 (20%)')")

            # Chart.js is vendored locally (never a CDN) and is
            # the real library: the UMD build loads from this
            # server and exposes the global Chart.
            chartjs = page.request.get(base + "/chart.umd.min.js")
            check("chartjs served locally", chartjs.status == 200, str(chartjs.status))
            chartjs_body = chartjs.text()
            check("chartjs is the real library",
                  "Chart.js v4.6.1" in chartjs_body and "MIT License" in chartjs_body)
            check("chartjs local script tag",
                  page.evaluate("!!document.querySelector('script[src=\"chart.umd.min.js\"]')"))
            check("chartjs loaded in page",
                  page.evaluate("typeof Chart === 'function' && Chart.version.indexOf('4.6.1') === 0"),
                  page.evaluate("typeof Chart === 'undefined' ? 'no Chart' : Chart.version"))

            # Overview graphics: donut, task bars, trend.
            page.click("button[data-section='overview']")
            page.wait_for_function("document.getElementById('ovDonut').textContent.includes('3600.00')", timeout=10000)
            page.wait_for_timeout(700)  # chart animations settle
            ovd = page.evaluate("document.getElementById('ovDonut').textContent")
            check("graphics donut remaining 3600.00", "3600.00" in ovd, ovd[:200])
            check("graphics donut spent 29%", "29%" in ovd, ovd[:200])
            check("graphics donut canvas present", page.locator("#ovDonut canvas").count() == 1)
            donut = chart_data(page, "#ovDonut canvas")
            check("graphics donut chart data", donut is not None and donut["data"] == [[1500, 3600]], str(donut))
            ovt = page.evaluate("document.getElementById('ovTasks').textContent")
            check("graphics task bars 1/2 done and pending", ovt.count("1 / 2") == 2, ovt[:200])
            check("graphics task KPI top score 40", "40" in ovt and "BrowserTask" in ovt, ovt[:200])
            check("graphics task KPI deadline 2026-11-20", "2026-11-20" in ovt, ovt[:200])
            check("graphics task canvas present", page.locator("#ovTasks canvas").count() == 1)
            taskch = chart_data(page, "#ovTasks canvas")
            check("graphics task chart data", taskch is not None and taskch["data"] == [[1, 1]], str(taskch))
            check("graphics trend canvas present", page.locator("#ovTrend canvas").count() == 1)
            trend = chart_data(page, "#ovTrend canvas")
            check("graphics trend 6 months", trend is not None and len(trend["labels"]) == 6
                  and trend["labels"][-1] == "Nov 26", str(trend and trend["labels"]))
            check("graphics trend Nov income 5100",
                  trend is not None and trend["data"][0][-1] == 5100, str(trend and trend["data"]))
            check("graphics trend Nov expense 1500",
                  trend is not None and trend["data"][1][-1] == 1500, str(trend and trend["data"]))

            # Expense categories (Budget). Category names live on
            # the canvas (Chart.js axis labels), so the wait is
            # for the canvas, and the values come from the chart.
            page.click("button[data-section='budget']")
            page.wait_for_function("document.querySelector('#budCats canvas') !== null", timeout=10000)
            check("graphics category canvas present", page.locator("#budCats canvas").count() == 1)
            catsch = chart_data(page, "#budCats canvas")
            check("graphics category labels", catsch is not None and catsch["labels"] == ["Food", "Transport"],
                  str(catsch and catsch["labels"]))
            check("graphics category data", catsch is not None and catsch["data"] == [[1200, 300]],
                  str(catsch and catsch["data"]))

            # Habit week bars + heatmap.
            page.click("button[data-section='habits']")
            page.wait_for_function("document.getElementById('hbWeek').textContent.includes('3 / 7 days')", timeout=10000)
            check("graphics week canvas present", page.locator("#hbWeek canvas").count() == 1)
            week = chart_data(page, "#hbWeek canvas")
            check("graphics week 7 days 3 done", week is not None and len(week["labels"]) == 7
                  and week["data"][0].count(1) == 3, str(week and week["data"]))
            check("graphics week 3/7 days", "3 / 7 days" in page.evaluate("document.getElementById('hbWeek').textContent"))
            check("graphics week streak 3", "streak: 3 day(s)" in page.evaluate("document.getElementById('hbWeek').textContent"))
            check("graphics heatmap 30 cells", page.locator("#hbHeat .gx-heat-cell").count() == 30)
            check("graphics heatmap 3 done", page.locator("#hbHeat .gx-heat-cell.on").count() == 3)
            check("graphics heatmap tooltips", page.locator("#hbHeat [data-tip]").count() == 30)

            # Savings ring.
            page.click("button[data-section='savings']")
            page.wait_for_function("document.getElementById('svRings').textContent.includes('25%')", timeout=10000)
            check("graphics savings ring 25%",
                  page.evaluate("document.querySelector('#svRings .gx-ring-item').dataset.pct") == "25")
            check("graphics savings ring goal name",
                  "BrowserGoal" in page.evaluate("document.getElementById('svRings').textContent"))
            check("graphics savings canvas present", page.locator("#svRings canvas").count() == 1)
            svg = chart_data(page, "#svRings canvas")
            check("graphics savings chart data", svg is not None and svg["data"] == [[250, 750]], str(svg))

            # Study progress bar + timeline.
            page.click("button[data-section='study']")
            page.wait_for_function("document.getElementById('spList').textContent.includes('1/5 (20%)')", timeout=10000)
            page.wait_for_timeout(700)
            check("graphics study progress canvases 2", page.locator("#spList .gx-study-canvas").count() == 2)
            artch = page.evaluate("""() => {
                const plans = [...document.querySelectorAll('#spList .sp-plan')];
                const art = plans.find(p => p.textContent.includes('BrowserArt'));
                const cv = art ? art.querySelector('.gx-study-canvas') : null;
                const ch = cv && typeof Chart !== 'undefined' ? Chart.getChart(cv) : null;
                return ch ? ch.data.datasets[0].data : null; }""")
            check("graphics study progress chart 20%", artch == [20], str(artch))
            check("graphics study timeline 10 cells", page.locator("#spList .gx-timeline .cell").count() == 10,
                  str(page.locator("#spList .gx-timeline .cell").count()))
            check("graphics study timeline 1 done", page.locator("#spList .gx-timeline .cell.done").count() == 1)
            check("graphics study timeline 3 revision", page.locator("#spList .gx-timeline .cell.rev").count() == 3)
            check("graphics study timeline today cell", page.locator("#spList .gx-timeline .cell.today").count() >= 1)

            # Design tokens (shadcn design language, plain CSS):
            # the spacing/radii/focus tokens exist on :root.
            check("design token radius-lg 22px",
                  page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--radius-lg').trim()") == "22px")
            check("design token space-4 16px",
                  page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--space-4').trim()") == "16px")
            check("design token focus-ring set",
                  page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--focus-ring').trim()").startswith("0 0 0 3px"))
            # Pins features still intact: all 30 sidebar icons
            # carry their hover-animation span.
            check("pins sidebar icons 30", page.locator(".nav-ic").count() == 30,
                  str(page.locator(".nav-ic").count()))

            # Graphics empty states: a fresh user with no data at all.
            epage = browser.new_page()
            epage.goto(base + "/", timeout=15000)
            epage.click("button[data-section='auth']")
            epage.fill("#regUser", "emptyuser")
            epage.fill("#regPass", "Empty1234")
            epage.fill("#regPassConfirm", "Empty1234")
            epage.click("#regBtn")
            epage.wait_for_function("document.querySelector('#regMsg').textContent.includes('Registered')")
            epage.fill("#loginUser", "emptyuser")
            epage.fill("#loginPass", "Empty1234")
            epage.click("#loginBtn")
            epage.wait_for_function("document.querySelector('section.active').id === 'overview'")
            epage.wait_for_function("document.getElementById('ovDonut').textContent.length > 0", timeout=10000)
            check("graphics empty donut", "No transactions yet" in epage.evaluate("document.getElementById('ovDonut').textContent"))
            check("graphics empty task bars", "No tasks yet" in epage.evaluate("document.getElementById('ovTasks').textContent"))
            check("graphics empty trend", "No transactions in the last 6 months" in epage.evaluate("document.getElementById('ovTrend').textContent"))
            epage.click("button[data-section='budget']")
            epage.wait_for_function("document.getElementById('budCats').textContent.length > 0", timeout=10000)
            check("graphics empty categories", "No expenses yet" in epage.evaluate("document.getElementById('budCats').textContent"))
            epage.click("button[data-section='savings']")
            epage.wait_for_function("document.getElementById('svRings').textContent.length > 0", timeout=10000)
            check("graphics empty savings rings", "No savings goals yet" in epage.evaluate("document.getElementById('svRings').textContent"))
            epage.click("button[data-section='habits']")
            epage.wait_for_function("document.getElementById('hbWeek').textContent.includes('0 / 7 days')", timeout=10000)
            check("graphics empty week 0/7", "0 / 7 days" in epage.evaluate("document.getElementById('hbWeek').textContent"))
            check("graphics empty heatmap 30 cells", epage.locator("#hbHeat .gx-heat-cell").count() == 30)
            epage.close()

            # Dashboard animations: vendored Animate.css, section
            # entrances, staggered cards, count-up numbers, error
            # shake, goal-complete pulse, sidebar indicator.
            # Animate.css is served locally (never a CDN) and is
            # the real library: base class and keyframes exist.
            anim_css = page.request.get(base + "/animate.min.css")
            check("anim css served locally", anim_css.status == 200, str(anim_css.status))
            anim_body = anim_css.text()
            check("anim css is the real library",
                  ".animate__animated" in anim_body and "@keyframes bounce" in anim_body
                  and "@keyframes shakeX" in anim_body)
            check("anim css linked in page",
                  page.evaluate("!!document.querySelector('link[href=\"animate.min.css\"]')"))
            check("anim no cdn stylesheet",
                  page.evaluate("[...document.querySelectorAll('link[rel=\"stylesheet\"]')].every(l => { const h = l.getAttribute('href') || ''; return !h.startsWith('http') && !h.startsWith('//'); })"))
            # Section switch applies the entrance animation.
            # The Overview section still shows the previous
            # visit's render (donut centre already 3600.00) when
            # this section opens, so a plain value wait below can
            # pass on that stale render while the fresh
            # loadOverview is still fetching — the fresh render
            # then restarts the count-ups and the checks read
            # mid-count values. Mark the stale stat cards first
            # and wait for the fresh render (new nodes, no mark).
            page.evaluate("document.querySelector('#overviewCards .stat')?.setAttribute('data-probe', 'stale')")
            page.click("button[data-section='overview']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'overview'")
            page.wait_for_function("document.querySelector('#overviewCards .stat') !== null && document.querySelector('#overviewCards .stat').dataset.probe !== 'stale'", timeout=10000)
            check("anim section entrance",
                  page.evaluate("getComputedStyle(document.querySelector('section#overview')).animationName") == "animSectionIn")
            # Cards stagger in with varied delays (at least 3
            # distinct delays across the 6 stat cards).
            page.wait_for_function("document.getElementById('ovDonut').textContent.includes('3600.00')", timeout=10000)
            # Count-ups run 0.75s; wait for the donut centre to land
            # (the stat/KPI count-ups start in the same frame batch,
            # so they are done by then too) instead of a fixed wait.
            page.wait_for_function("document.querySelector('#ovDonut .gx-donut-center').textContent === '3600.00'", timeout=10000)
            check("anim overview stat cards staggered",
                  page.evaluate("""() => {
                      const cards = [...document.querySelectorAll('#overviewCards .stat')];
                      const delays = cards.map(c => c.style.getPropertyValue('--anim-delay'));
                      return cards.length === 6 && cards.every(c => c.classList.contains('anim-card'))
                          && new Set(delays).size >= 3; }"""))
            # Count-up reaches the real targets (income 5100,
            # expense 1500, balance 3600; top task score 40).
            check("anim count-up balance reaches 3600.00",
                  page.evaluate("[...document.querySelectorAll('#overviewCards .stat .value')][2].textContent") == "3600.00")
            check("anim count-up donut centre reaches 3600.00",
                  page.evaluate("document.querySelector('#ovDonut .gx-donut-center').textContent") == "3600.00")
            check("anim count-up top score reaches 40",
                  page.evaluate("document.querySelector('#ovTasks .gx-kpi .n').textContent") == "40")
            # Error shake: the AI daily empty-input error is
            # client-side (no API call), so it cannot disturb the
            # failed-request accounting at the end of this test.
            page.click("button[data-section='ai-daily']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-daily'")
            page.click("#aiDailyBtn")
            page.wait_for_function("document.getElementById('aiDailyMsg').textContent.length > 0")
            check("anim error message shakes",
                  page.evaluate("document.getElementById('aiDailyMsg').classList.contains('animate__shakeX')"))
            # Success slide-in: a valid priority calculation.
            page.click("button[data-section='priority']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'priority'")
            page.fill("#prUrgency", "8")
            page.fill("#prImportance", "9")
            page.click("#prBtn")
            page.wait_for_function("document.getElementById('prMsg').textContent.includes('Priority Score')")
            check("anim success message slides in",
                  page.evaluate("document.getElementById('prMsg').classList.contains('anim-msg-in')"))
            # Button hover transition includes transform (lift), and
            # a primary button keeps its gradient on hover (the
            # generic .btn:hover pale background must not wash it
            # white — white text on white).
            check("anim button hover transition",
                  "transform" in page.evaluate("getComputedStyle(document.querySelector('#prBtn')).transition"))
            page.hover("#prBtn")
            check("anim primary button keeps gradient on hover",
                  "linear-gradient" in page.evaluate("getComputedStyle(document.querySelector('#prBtn')).backgroundImage"))
            # Sidebar active indicator: the ::before bar is fully
            # grown (scaleY 1) on the active button.
            page.wait_for_timeout(400)  # indicator slide (0.28s) settles
            check("anim sidebar active indicator",
                  page.evaluate("""() => {
                      const b = document.querySelector('nav button[data-section="priority"].active');
                      if (!b) return false;
                      return getComputedStyle(b, '::before').transform === 'matrix(1, 0, 0, 1, 0, 0)'; }"""))
            # Goal-complete pulse: a goal saved in full gets the
            # celebration class and badge.
            page.click("button[data-section='savings']")
            page.fill("#svName", "FullGoal")
            page.fill("#svTarget", "100")
            page.click("#svBtn")
            page.wait_for_function("document.getElementById('svMsg').textContent.includes('Goal added')")
            page.fill("#svAddName", "FullGoal")
            page.fill("#svAddAmount", "100")
            page.click("#svAddBtn")
            page.wait_for_function("document.getElementById('svAddMsg').textContent.includes('100')")
            # Wait for the 100% render, not just the ring item's
            # existence: the item already exists from the add-goal
            # step (at 0%), so an existence wait can match the
            # stale render and the class check below races the
            # re-render after the add.
            page.wait_for_function("document.querySelector('#svRings .gx-ring-item[data-goal=\"FullGoal\"]')?.dataset.pct === '100'")
            check("anim goal-complete class",
                  page.evaluate("document.querySelector('#svRings .gx-ring-item[data-goal=\"FullGoal\"]').classList.contains('goal-complete')"))
            check("anim goal-complete badge",
                  "Goal reached!" in page.evaluate("document.querySelector('#svRings .gx-ring-item[data-goal=\"FullGoal\"]').textContent"))
            # Staggered list rows: task rows fade in with varied delays.
            page.click("button[data-section='tasks']")
            page.wait_for_function("document.getElementById('taskList').textContent.includes('BrowserTask')")
            check("anim task rows staggered",
                  page.evaluate("""() => {
                      const rows = [...document.querySelectorAll('#taskList tr.anim-row')];
                      const delays = rows.map(r => r.style.getPropertyValue('--anim-delay'));
                      return rows.length >= 2 && new Set(delays).size >= 2; }"""))

            # Pinterest features: infinite-loop AI loader, auth
            # button loading state, sidebar icon micro-animations,
            # done-checkmark pops.
            # AI loader: hold the AI call in flight via the mock
            # delay (see MockGemini.delay) so the loader is
            # observable, then check it appears (inline SVG, no
            # img/GIF), the Ask button spins its icon, and both
            # disappear when the reply arrives.
            MockGemini.delay = 2.0
            page.click("button[data-section='ai-daily']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-daily'")
            page.fill("#aiDailyInput", "Should I study maths or physics tonight?")
            page.click("#aiDailyBtn")
            page.wait_for_selector("#aiDailyReply .ai-thinking", timeout=5000)
            check("pins ai loader appears while pending",
                  page.is_visible("#aiDailyReply .loop-loader"))
            check("pins ai loader is inline svg, no img",
                  page.evaluate("document.querySelector('#aiDailyReply .loop-loader') instanceof SVGSVGElement")
                  and page.evaluate("document.querySelector('#aiDailyReply img') === null"))
            check("pins ai ask button busy while pending",
                  page.evaluate("document.getElementById('aiDailyBtn').classList.contains('ai-busy')"))
            check("pins ai ask icon spins while pending",
                  page.evaluate("getComputedStyle(document.querySelector('#aiDailyBtn .ai-btn-ic svg')).animationName") == "icSpin")
            page.wait_for_function("document.getElementById('aiDailyReply').textContent.includes('Mocked AI reply.')", timeout=10000)
            check("pins ai loader disappears after reply",
                  page.evaluate("document.querySelector('#aiDailyReply .ai-thinking') === null"))
            check("pins ai ask button idle after reply",
                  not page.evaluate("document.getElementById('aiDailyBtn').classList.contains('ai-busy')")
                  and page.evaluate("document.querySelector('#aiDailyBtn .ai-btn-label').textContent") == "Ask AI")
            # Leave the input empty: the ai-daily section below
            # clicks Ask with no input and expects the client-side
            # "describe the decision" error.
            page.fill("#aiDailyInput", "")
            MockGemini.delay = 0.0
            # Sidebar icon micro-animations: hovering a nav button
            # animates its icon, each icon has its own variant
            # (30 icons, at least 6 distinct variants), and the
            # active section's icon breathes.
            page.click("button[data-section='overview']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'overview'")
            page.hover("button[data-section='tasks']")
            check("pins sidebar icon animates on hover",
                  page.evaluate("getComputedStyle(document.querySelector('button[data-section=\"tasks\"] .nav-ic')).animationName") == "navBounce")
            check("pins sidebar icons vary by icon",
                  page.evaluate("""() => {
                      const icons = [...document.querySelectorAll('.sidebar .nav-ic')];
                      const anims = new Set(icons.map(i => i.dataset.anim));
                      return icons.length === 30 && anims.size >= 6; }"""))
            check("pins sidebar active icon breathes",
                  page.evaluate("getComputedStyle(document.querySelector('button[data-section=\"overview\"].active .nav-ic')).animationName") == "navIcActive")
            # Load-time icon stagger: when the dashboard first
            # opens (login), every sidebar icon plays its own
            # micro-animation once, staggered down the list with
            # uneven delays. The stagger fires when the full
            # sidebar first becomes visible — the sidebar is
            # hidden until login, so a raw page load shows only
            # Home + Login. It plays once: the class is removed
            # when the wave finishes and section switches do
            # not replay it. On mobile the nav is a closed
            # drawer at login, so the stagger waits for the
            # first drawer open.
            ipage = browser.new_page()
            ipage.goto(base + "/", timeout=15000)
            ipage.click("button[data-section='auth']")
            ipage.fill("#loginUser", "browseruser")
            ipage.fill("#loginPass", "Browser123")
            ipage.click("#loginBtn")
            ipage.wait_for_function("document.getElementById('sidebar').classList.contains('icons-stagger')", timeout=15000)
            check("icons load stagger class appears on login",
                  ipage.evaluate("document.getElementById('sidebar').classList.contains('icons-stagger')"))
            check("icons load stagger delays increase",
                  ipage.evaluate("""() => {
                      const icons = [...document.querySelectorAll('.sidebar .nav-ic')];
                      const delays = icons.map(i => parseFloat(i.style.getPropertyValue('--ic-delay')));
                      return icons.length === 30 && delays.every(d => !isNaN(d))
                          && new Set(delays).size === 30
                          && delays.every((d, j) => j === 0 || d > delays[j - 1]); }"""))
            # The wave finishes on its own (~2.6s); the class is
            # removed and a section switch does not replay it.
            ipage.wait_for_function("!document.getElementById('sidebar').classList.contains('icons-stagger')", timeout=10000)
            check("icons load stagger finishes once",
                  not ipage.evaluate("document.getElementById('sidebar').classList.contains('icons-stagger')"))
            # Continuous idle motion: the same timeout that ends
            # the wave adds .icons-always, and every icon keeps
            # moving forever — infinite iteration, its own cycle
            # length (2.2-4.5s) and its own phase, so the icons
            # never move in sync. The active icon keeps its
            # breathe as its continuous motion; hovering an icon
            # still plays its hover motion (hover wins over idle
            # and, on the active icon, over the breathe).
            ipage.wait_for_function("document.getElementById('sidebar').classList.contains('icons-always')", timeout=10000)
            check("icons continuous class appears after wave",
                  ipage.evaluate("document.getElementById('sidebar').classList.contains('icons-always')"))
            check("icons continuous all infinite",
                  ipage.evaluate("""() => {
                      const icons = [...document.querySelectorAll('.sidebar .nav-ic')];
                      return icons.length === 30 && icons.every(i =>
                          getComputedStyle(i).animationIterationCount === 'infinite'); }"""))
            check("icons continuous cycles vary",
                  ipage.evaluate("""() => {
                      const icons = [...document.querySelectorAll('.sidebar .nav-ic')];
                      const durs = icons.map(i => parseFloat(getComputedStyle(i).animationDuration));
                      return icons.length === 30 && new Set(durs).size === 30
                          && durs.every(d => d >= 2.2 && d <= 4.5); }"""))
            check("icons continuous phases vary",
                  ipage.evaluate("""() => {
                      const icons = [...document.querySelectorAll('.sidebar .nav-ic')];
                      const delays = icons.map(i => parseFloat(getComputedStyle(i).animationDelay));
                      return icons.length === 30 && new Set(delays).size === 30; }"""))
            check("icons continuous idle uses idle keyframes",
                  ipage.evaluate("getComputedStyle(document.querySelector('button[data-section=\"tasks\"] .nav-ic')).animationName") == "navBounceIdle")
            check("icons continuous active icon breathes",
                  ipage.evaluate("getComputedStyle(document.querySelector('button[data-section=\"overview\"].active .nav-ic')).animationName") == "navIcActive")
            ipage.hover("button[data-section='tasks']")
            check("icons continuous hover still works",
                  ipage.evaluate("getComputedStyle(document.querySelector('button[data-section=\"tasks\"] .nav-ic')).animationName") == "navBounce")
            ipage.hover("button[data-section='overview']")
            check("icons continuous hover wins on active icon",
                  ipage.evaluate("getComputedStyle(document.querySelector('button[data-section=\"overview\"].active .nav-ic')).animationName") == "navTilt")
            ipage.click("button[data-section='tasks']")
            ipage.wait_for_function("document.querySelector('section.active')?.id === 'tasks'")
            ipage.wait_for_timeout(500)
            check("icons load stagger does not replay on section switch",
                  not ipage.evaluate("document.getElementById('sidebar').classList.contains('icons-stagger')"))
            ipage.close()
            # Mobile: no stagger while the drawer is closed; the
            # first drawer open plays it.
            dpage = browser.new_page(viewport={"width": 375, "height": 667})
            dpage.goto(base + "/", timeout=15000)
            dpage.evaluate("document.querySelector(\"button[data-section='auth']\").click()")
            dpage.fill("#loginUser", "browseruser")
            dpage.fill("#loginPass", "Browser123")
            dpage.click("#loginBtn")
            dpage.wait_for_function("document.querySelector('section.active').id === 'overview'", timeout=15000)
            dpage.wait_for_timeout(500)
            check("icons mobile no stagger while drawer closed",
                  not dpage.evaluate("document.getElementById('sidebar').classList.contains('icons-stagger')"))
            dpage.click("#menuBtn")
            dpage.wait_for_function("document.getElementById('sidebar').classList.contains('icons-stagger')", timeout=5000)
            check("icons mobile stagger on first drawer open",
                  dpage.evaluate("""() => {
                      const icons = [...document.querySelectorAll('.sidebar .nav-ic')];
                      const delays = icons.map(i => parseFloat(i.style.getPropertyValue('--ic-delay')));
                      return document.getElementById('sidebar').classList.contains('icons-stagger')
                          && icons.length === 30 && delays.every(d => !isNaN(d)); }"""))
            # Mobile: the wave hands over to the continuous idle
            # motion the same way as on desktop.
            dpage.wait_for_function("document.getElementById('sidebar').classList.contains('icons-always')", timeout=10000)
            check("icons mobile continuous after drawer wave",
                  dpage.evaluate("document.getElementById('sidebar').classList.contains('icons-always')")
                  and dpage.evaluate("getComputedStyle(document.querySelector('.sidebar .nav-ic')).animationIterationCount") == "infinite")
            dpage.close()
            # Done checkmark: completing a fresh task pops a green
            # checkmark into its status cell.
            page.click("button[data-section='tasks']")
            page.fill("#taskTitle", "PinTask")
            page.fill("#taskUrgency", "7")
            page.fill("#taskImportance", "7")
            page.fill("#taskDeadline", "2026-11-22")
            page.click("#taskAddBtn")
            page.wait_for_function("document.getElementById('taskList').textContent.includes('PinTask')")
            page.locator("#taskList tr", has_text="PinTask").locator("button", has_text="Complete").click()
            page.wait_for_function("document.querySelector('#taskList .done-mark.done-pop') !== null", timeout=10000)
            check("pins task done checkmark pops",
                  "✓ Completed" in page.evaluate("document.querySelector('#taskList .done-mark.done-pop').textContent"))
            # Done checkmark: recording a fresh habit pops a
            # checkmark beside its row.
            page.click("button[data-section='habits']")
            page.fill("#hbName", "PinHabit")
            page.fill("#hbDate", date.today().isoformat())
            page.click("#hbBtn")
            page.wait_for_function("document.querySelector('#hbList .done-mark.done-pop') !== null", timeout=10000)
            check("pins habit done checkmark pops",
                  page.evaluate("document.querySelector('#hbList .done-mark.done-pop') !== null"))
            # Auth button loading state: on a fresh page, check
            # the login button shows its spinner and is disabled
            # while the login hashes the password server-side
            # (PBKDF2, ~2s — a real in-flight window, so no
            # artificial delay is needed; a sleep in a route
            # handler would block Playwright's event loop and
            # hide the window instead).
            lpage = browser.new_page()
            lpage.goto(base + "/", timeout=15000)
            lpage.click("button[data-section='auth']")
            lpage.fill("#regUser", "pinuser")
            lpage.fill("#regPass", "Pin12345")
            lpage.fill("#regPassConfirm", "Pin12345")
            lpage.click("#regBtn")
            lpage.wait_for_function("document.querySelector('#regMsg').textContent.includes('Registered')")
            lpage.fill("#loginUser", "pinuser")
            lpage.fill("#loginPass", "Pin12345")
            lpage.click("#loginBtn")
            lpage.wait_for_selector("#loginBtn .btn-spinner", timeout=5000)
            check("pins login button loading state",
                  lpage.is_visible("#loginBtn .btn-spinner")
                  and lpage.evaluate("document.getElementById('loginBtn').disabled") is True)
            lpage.wait_for_function("document.querySelector('section.active').id === 'overview'", timeout=15000)
            check("pins login succeeds after loading state",
                  lpage.evaluate("document.querySelector('section.active').id") == "overview"
                  and lpage.evaluate("document.getElementById('loginBtn').textContent") == "Login")
            lpage.close()

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
            page.wait_for_function("document.getElementById('aiDailyReply').textContent.includes('Second line of the reply.')")
            check("ai-daily mock reply shown", "Mocked AI reply." in page.content())
            check("ai-daily mock reply keeps line breaks", "Second line of the reply." in page.content())
            # Typing effect: the reply box ends up with the FULL
            # reply text, byte-identical (line break included) —
            # the wait above already waited for the last line.
            check("anim typing renders full reply",
                  page.evaluate("document.getElementById('aiDailyReply').textContent") == "Mocked AI reply.\nSecond line of the reply.")
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
            page.wait_for_function("document.getElementById('aiTaskReply').textContent.includes('Second line of the reply.')")
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
            page.wait_for_function("document.getElementById('aiStudyReply').textContent.includes('Second line of the reply.')")
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
            page.wait_for_function("document.getElementById('aiProblemReply').textContent.includes('Second line of the reply.')", timeout=15000)
            check("ai-problem Bengali 4000 chars mock reply shown", "Mocked AI reply." in page.content())
            check("ai-problem history id shown", "history #" in page.evaluate("document.getElementById('aiProblemMsg').textContent"))
            check("ai-problem no history-save warning", page.evaluate("document.getElementById('aiProblemWarn').textContent") == "")
            # Newline sanitization: a multi-line problem reaches the
            # mock with newlines as spaces.
            page.fill("#aiProblemDesc", "Fix the printer\nin my office")
            page.click("#aiProblemBtn")
            page.wait_for_function("document.getElementById('aiProblemReply').textContent.includes('Second line of the reply.')", timeout=15000)
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
            page.wait_for_function("document.getElementById('aiBudgetReply').textContent.includes('Second line of the reply.')", timeout=15000)
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
            page.wait_for_function("document.getElementById('aiBudgetReply').textContent.includes('Second line of the reply.')", timeout=15000)
            check("ai-budget expense mock reply shown", "Mocked AI reply." in page.content())
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-budget expense reaches mock", "Food: 1200.00" in sent, sent[:300])
            # Savings goal, all three fields: the goal reaches the
            # mock as "Laptop (target 100000.00, saved 25000.00)".
            page.fill("#aiBudgetGoalName", "Laptop")
            page.fill("#aiBudgetGoalTarget", "100000")
            page.fill("#aiBudgetGoalSaved", "25000")
            page.click("#aiBudgetBtn")
            page.wait_for_function("document.getElementById('aiBudgetReply').textContent.includes('Second line of the reply.')", timeout=15000)
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
            page.wait_for_function("document.getElementById('aiHabitReply').textContent.includes('Second line of the reply.')", timeout=15000)
            check("ai-habit mock reply shown", "Mocked AI reply." in page.content())
            check("ai-habit history id shown", "history #" in page.evaluate("document.getElementById('aiHabitMsg').textContent"))
            check("ai-habit no history-save warning", page.evaluate("document.getElementById('aiHabitWarn').textContent") == "")
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-habit reaches mock", all(x in sent for x in ("Habit: Morning run", "Frequency: daily", "Current streak: 0 days", "Target streak: 30 days")), sent[:300])
            # Weekly frequency: the mock sees weekly figures.
            page.select_option("#aiHabitFrequency", "weekly")
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitReply').textContent.includes('Second line of the reply.')", timeout=15000)
            check("ai-habit weekly mock reply shown", "Mocked AI reply." in page.content())
            sent = MockGemini.requests[-1] if MockGemini.requests else ""
            check("ai-habit weekly reaches mock", all(x in sent for x in ("Frequency: weekly", "Current streak: 0 weeks", "8-week completion rate")), sent[:300])
            # Reference date = today: the mock sees it as the
            # reference date (server date is the same machine's).
            page.select_option("#aiHabitFrequency", "daily")
            page.fill("#aiHabitToday", date.today().isoformat())
            page.click("#aiHabitBtn")
            page.wait_for_function("document.getElementById('aiHabitReply').textContent.includes('Second line of the reply.')", timeout=15000)
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
            # 12 entries in total (daily 2 — the pins loader
            # test call plus the 3.1 success call — task 1,
            # study 1, problem 2, budget 3, habit 3); only successful
            # Gemini calls save history, so the 503/400 calls
            # above added none. Only successful GET/DELETE calls
            # are used here, so the console-error filter below
            # (six 503s + six 400s) is unchanged.
            page.click("button[data-section='ai-history']")
            page.wait_for_function("document.querySelector('section.active')?.id === 'ai-history'")
            check("ai-history section visible after login", page.is_visible("section#ai-history"))
            check("ai-history filter options", page.evaluate("document.querySelectorAll('#aiHistoryFilter option').length") == 7)
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 12", timeout=15000)
            check("ai-history renders 12 entries", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 12)
            first = page.evaluate("document.querySelector('.ai-history-entry').textContent")
            check("ai-history newest first is habit", "Habit" in first and "Morning run" in first, first[:200])
            check("ai-history newest shows mock reply", "Mocked AI reply." in first, first[:200])
            # Filter: daily-decision has 2 entries, habit has 3,
            # all has 12. The filter re-renders without a call.
            page.select_option("#aiHistoryFilter", "daily-decision")
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 2")
            check("ai-history filter daily-decision shows 2", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 2)
            check("ai-history filter daily-decision label", "Daily Decision" in page.evaluate("document.querySelector('.ai-history-entry').textContent"))
            page.select_option("#aiHistoryFilter", "habit")
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 3")
            check("ai-history filter habit shows 3", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 3)
            page.select_option("#aiHistoryFilter", "all")
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 12")
            check("ai-history filter all shows 12", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 12)
            # Delete one entry via the UI (confirm dialog auto-accepted
            # by the handler registered before the study-plan delete
            # above — registering a second one made Playwright raise
            # "Cannot accept dialog which is already handled").
            page.locator(".ai-history-entry .btn-danger").first.click()
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 11")
            check("ai-history delete removes entry", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 11)
            check("ai-history delete message", "Entry deleted" in page.evaluate("document.getElementById('aiHistoryMsg').textContent"))
            # Logout clears the rendered list at once.
            page.click("#logoutBtn")
            page.wait_for_function("document.querySelector('section.active')?.id === 'landing'")
            check("ai-history logout clears list", page.evaluate("document.getElementById('aiHistoryList').innerHTML") == "")
            # Log back in: the list reloads (11 entries left).
            page.click("button[data-section='auth']")
            page.fill("#loginUser", "browseruser")
            page.fill("#loginPass", "Browser123")
            page.click("#loginBtn")
            page.wait_for_function("document.querySelector('section.active')?.id === 'overview'", timeout=10000)
            page.click("button[data-section='ai-history']")
            page.wait_for_function("document.querySelectorAll('.ai-history-entry').length === 11", timeout=15000)
            check("ai-history reloads after re-login", page.evaluate("document.querySelectorAll('.ai-history-entry').length") == 11)
            # Delete the remaining entries via the API (all 200s,
            # so no console error is added), then reload the
            # section: the empty state must show.
            remaining = page.evaluate("""async () => {
                const t = sessionStorage.getItem('pdps_token');
                const r = await fetch('/api/ai/history?limit=50', {headers:{Authorization:'Bearer '+t}});
                const j = await r.json();
                for (const e of j.history) { await fetch('/api/ai/history/' + e.id, {method:'DELETE', headers:{Authorization:'Bearer '+t}}); }
                return j.history.length; }""")
            check("ai-history api deletes remaining", remaining == 11, str(remaining))
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

            # Reduced motion: a fresh page with the OS setting on —
            # every animation collapses to an instant snap (the
            # CSS kill-switch), and the page detects the setting.
            rpage = browser.new_page(reduced_motion="reduce")
            rpage.goto(base + "/", timeout=15000)
            rpage.wait_for_function("document.querySelector('section.active')?.id === 'landing'")
            check("anim reduced motion detected",
                  rpage.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches") is True)
            # Chromium serializes the collapsed 0.01ms duration as
            # "1e-05s", so compare numerically (a normal entrance
            # is 0.38s) instead of matching the string.
            check("anim reduced motion collapses section entrance",
                  rpage.evaluate("parseFloat(getComputedStyle(document.querySelector('section#landing')).animationDuration)") <= 0.001)
            check("anim reduced motion collapses card entrance",
                  rpage.evaluate("parseFloat(getComputedStyle(document.querySelector('#landing .card')).animationDuration)") <= 0.001)
            # Pinterest: the loop loader is static under reduced
            # motion (the kill-switch freezes the runner) but still
            # visible, and the Ask button's icon does not spin.
            rpage.click("button[data-section='auth']")
            rpage.fill("#loginUser", "browseruser")
            rpage.fill("#loginPass", "Browser123")
            rpage.click("#loginBtn")
            rpage.wait_for_function("document.querySelector('section.active').id === 'overview'")
            # Icons: no load stagger under reduced motion — the
            # class is never added and no per-icon delay is set.
            rpage.wait_for_timeout(500)
            check("icons reduced motion no stagger",
                  not rpage.evaluate("document.getElementById('sidebar').classList.contains('icons-stagger')")
                  and rpage.evaluate("document.querySelector('.sidebar .nav-ic').style.getPropertyValue('--ic-delay')") == "")
            # Icons: no continuous motion either — the class is
            # never added and no per-icon cycle is set.
            check("icons reduced motion no continuous",
                  not rpage.evaluate("document.getElementById('sidebar').classList.contains('icons-always')")
                  and rpage.evaluate("document.querySelector('.sidebar .nav-ic').style.getPropertyValue('--ic-cycle')") == "")
            MockGemini.delay = 2.0
            rpage.click("button[data-section='ai-daily']")
            rpage.wait_for_function("document.querySelector('section.active')?.id === 'ai-daily'")
            rpage.fill("#aiDailyInput", "Reduced motion loader check")
            rpage.click("#aiDailyBtn")
            rpage.wait_for_selector("#aiDailyReply .ai-thinking", timeout=5000)
            check("pins reduced motion loader is static",
                  rpage.evaluate("parseFloat(getComputedStyle(document.querySelector('#aiDailyReply .loop-runner')).animationDuration)") <= 0.001
                  and rpage.is_visible("#aiDailyReply .loop-loader"))
            check("pins reduced motion ask icon does not spin",
                  rpage.evaluate("parseFloat(getComputedStyle(document.querySelector('#aiDailyBtn .ai-btn-ic svg')).animationDuration)") <= 0.001)
            rpage.wait_for_function("document.getElementById('aiDailyReply').textContent.includes('Mocked AI reply.')", timeout=10000)
            MockGemini.delay = 0.0
            rpage.close()

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
