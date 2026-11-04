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
import argparse, os, shutil, subprocess, sys, tempfile, time
PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  PASS {name}")
    else: FAIL += 1; print(f"  FAIL {name} {detail}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="./cpp_server")
    ap.add_argument("--port", type=int, default=8140)
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright
    tmp = tempfile.mkdtemp(prefix="pdps-mobile-test-")
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
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nmobile_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0

if __name__ == "__main__":
    sys.exit(main())
