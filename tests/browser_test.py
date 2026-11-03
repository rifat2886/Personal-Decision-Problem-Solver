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
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

PASS = 0
FAIL = 0
ERRORS = []


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
    proc = subprocess.Popen([args.server, "--port", str(args.port),
                             "--data-dir", tmp],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)
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
            page.wait_for_timeout(1500)
            check("registration message", "success" in page.content().lower() or "registered" in page.content().lower())

            # Login.
            page.fill("#loginUser", "browseruser")
            page.fill("#loginPass", "Browser123")
            page.click("#loginBtn")
            page.wait_for_timeout(1500)
            check("login leads to overview", page.url.startswith(base))
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

            check("no JS page errors", len(ERRORS) == 0, str(ERRORS[:3]))
            check("no failed API requests", len(failed) == 0, str(failed[:3]))
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nbrowser_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
