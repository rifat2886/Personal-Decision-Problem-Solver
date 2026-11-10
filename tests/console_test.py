#!/usr/bin/env python3
"""Automated console-app regression test.

Runs the console binary in a fresh temporary directory with scripted
stdin, then checks stdout and the data files it wrote. No real
passwords are used; all test accounts live in the temporary directory.

Usage:
    python3 tests/console_test.py --binary path/to/project

Exit code 0 = all checks passed, 1 = at least one check failed.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def run(binary, data_dir, script):
    proc = subprocess.run([binary], input=script, capture_output=True,
                          text=True, cwd=data_dir, timeout=30)
    return proc.returncode, proc.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    args = ap.parse_args()
    # The test runs the binary with a temporary data directory as its
    # working directory, so a relative binary path would not be found
    # there. Resolve it once, up front (this also fixes CI, where the
    # workflow passes ./project / ./project.exe).
    args.binary = os.path.abspath(args.binary)
    tmp = tempfile.mkdtemp(prefix="pdps-console-test-")
    print(f"data dir: {tmp}")
    try:
        # Session 1: register (first user = ADMIN, hashed), login,
        # prioritise a task (persists to tasks.txt), logout via menu 0.
        # Menu numbers are taken from the console main menu; the exact
        # prompt text is not asserted, only the outcomes below.
        script1 = (
            "1\ntestuser\nTestPass123\nTestPass123\n\n\n"   # register (password + confirm)
            "2\ntestuser\nTestPass123\n\n\n"  # login
            "11\n1\nConsoleTask\n8\n8\n2026-11-20\n\n\n"  # prioritise 1 task
            "0\n"
        )
        code, out = run(args.binary, tmp, script1)
        check("console exit 0", code == 0, str(code))
        check("registration successful", "Registration successful" in out)
        check("login successful", "Login successful" in out)
        check("task saved message", "Tasks saved to tasks.txt" in out)
        with open(os.path.join(tmp, "users.txt")) as f:
            users = f.read()
        check("console new account hashed",
              "TestPass123" not in users and "pbkdf2$100000$" in users, users[:60])
        check("console first user ADMIN", "ADMIN" in users)
        with open(os.path.join(tmp, "tasks.txt")) as f:
            tasks = f.read()
        check("console task persisted in dashboard format",
              "1|ConsoleTask|8|8|2026-11-20|Pending" in tasks, tasks)

        # Session 2 (fresh process): Task Status and Deadline Alert
        # must now work WITHOUT running Task Prioritization first —
        # this is the Phase 6 fix. Then password change + re-login.
        script2 = (
            "2\ntestuser\nTestPass123\n\n\n"  # login
            "13\n1\n2\n\n\n"                  # task status: task 1 -> In Progress
            "14\n2026-11-10\n\n\n"             # deadline alert
            "4\nTestPass123\nChanged123\n\n\n"  # password change (menu 4?)
            "0\n"
        )
        code, out = run(args.binary, tmp, script2)
        check("session2 exit 0", code == 0, str(code))
        check("task status in new session", "ConsoleTask" in out and
              "Status updated successfully" in out, out[-500:])
        check("deadline UPCOMING in new session",
              "UPCOMING: ConsoleTask" in out or "In Progress" in out, out[-500:])
        with open(os.path.join(tmp, "tasks.txt")) as f:
            tasks2 = f.read()
        check("task status persisted",
              "1|ConsoleTask|8|8|2026-11-20|In Progress" in tasks2, tasks2)

        # Menu 4 is Change Password (main.cpp); verify by re-login.
        script3 = "2\ntestuser\nChanged123\n\n\n0\n"
        code, out = run(args.binary, tmp, script3)
        check("password change + re-login", "Login successful" in out, out[-300:])

        # Old plaintext account migration via console login.
        with open(os.path.join(tmp, "users.txt"), "a") as f:
            f.write("olduser OldPass123 USER\n")
        code, out = run(args.binary, tmp, "2\nolduser\nOldPass123\n\n\n0\n")
        check("console old-plaintext login", "Login successful" in out)
        with open(os.path.join(tmp, "users.txt")) as f:
            check("console old account migrated",
                  "OldPass123" not in f.read())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nconsole_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
