#!/usr/bin/env python3
"""Per-user backup/restore test (public-launch redesign, 2026-11-05).

The 2026-11-05 review proved the old global backup was unsafe: Alice
backed up, Bob backed up, the single backup set was overwritten, and
Alice's restore returned 0 and deleted Alice's decision. This test
reproduces that exact scenario and requires the fixed behaviour:

- Alice backs up 1 decision, Bob backs up 1 decision: both backups
  survive, each user restores only their own rows.
- After Alice restores, Bob's current decision is untouched, and
  vice versa.
- Restore without {"confirm": true} is rejected (400) and changes
  nothing.
- Restore with no backup for the user is rejected (400) and changes
  nothing (it must not wipe the user's current decisions).
- A malformed backup row is skipped (counted in "skipped"), never
  written into decisions.txt.
- Compatibility: a backup file written in the OLD format (one user
  overwriting the whole file, no per-user logic) is still readable:
  restore filters it by owner, so the old file's rows for other
  users are not restored to the caller.

Usage:
    python3 tests/backup_test.py --server-cmd "./cpp_server" --port 8230
    python3 tests/backup_test.py --server-cmd "python3 dashboard/server.py" --port 8231
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

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


def req(port, method, path, token=None, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read() or b"{}"
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def register_login(port, username, password):
    status, body = req(port, "POST", "/api/register",
                       body={"username": username, "password": password})
    assert status in (200, 201), (username, body)
    status, body = req(port, "POST", "/api/login",
                       body={"username": username, "password": password})
    assert status == 200, (username, body)
    return body["token"]


def add_decision(port, token, title):
    status, body = req(port, "POST", "/api/decisions", token=token,
                       body={"date": "2026-11-05", "type": "Daily",
                             "priority": 5, "title": title})
    assert status in (200, 201), body
    return body


def list_titles(port, token):
    status, body = req(port, "GET", "/api/decisions", token=token)
    assert status == 200, body
    if isinstance(body, list):
        return [d.get("title") for d in body]
    return [d.get("title") for d in body.get("decisions", [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-cmd", required=True)
    ap.add_argument("--port", type=int, default=8230)
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="pdps-backup-test-")
    cmd = args.server_cmd.split() + ["--port", str(args.port),
                                     "--data-dir", tmp]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            status, _ = req(args.port, "GET", "/api/health")
            if status != 0:
                break
            time.sleep(0.2)
        alice = register_login(args.port, "alice", "Alice12345")
        bob = register_login(args.port, "bob", "Bob12345")
        carol = register_login(args.port, "carol", "Carol12345")

        # --- The exact 2026-11-05 failure scenario, now fixed ---
        add_decision(args.port, alice, "AliceDecision")
        add_decision(args.port, bob, "BobDecision")
        s, b = req(args.port, "POST", "/api/backup", token=alice, body={})
        check("alice backup", s == 200 and b.get("backedUp") == 1, str(b))
        s, b = req(args.port, "POST", "/api/backup", token=bob, body={})
        check("bob backup after alice", s == 200 and b.get("backedUp") == 1, str(b))
        # Alice's backup must still be on disk after Bob's backup.
        with open(os.path.join(tmp, "decisions_backup.txt")) as f:
            backup_text = f.read()
        check("both backups survive in one file",
              "AliceDecision" in backup_text and "BobDecision" in backup_text,
              backup_text)
        # Both create a temporary decision, then both restore.
        add_decision(args.port, alice, "AliceTemp")
        add_decision(args.port, bob, "BobTemp")
        s, b = req(args.port, "POST", "/api/restore", token=alice,
                   body={"confirm": True})
        check("alice restore", s == 200 and b.get("restored") == 1, str(b))
        check("alice restored only her decision",
              list_titles(args.port, alice) == ["AliceDecision"],
              str(list_titles(args.port, alice)))
        check("bob untouched by alice restore",
              "BobDecision" in list_titles(args.port, bob) and
              "BobTemp" in list_titles(args.port, bob),
              str(list_titles(args.port, bob)))
        s, b = req(args.port, "POST", "/api/restore", token=bob,
                   body={"confirm": True})
        check("bob restore", s == 200 and b.get("restored") == 1, str(b))
        check("bob restored only his decision",
              list_titles(args.port, bob) == ["BobDecision"],
              str(list_titles(args.port, bob)))
        check("alice still intact after bob restore",
              list_titles(args.port, alice) == ["AliceDecision"],
              str(list_titles(args.port, alice)))

        # --- Restore confirmation is mandatory ---
        add_decision(args.port, alice, "AliceSecond")
        s, b = req(args.port, "POST", "/api/restore", token=alice, body={})
        check("restore without confirm rejected",
              s == 400, str(b))
        check("restore without confirm changed nothing",
              "AliceSecond" in list_titles(args.port, alice),
              str(list_titles(args.port, alice)))
        s, b = req(args.port, "POST", "/api/restore", token=alice,
                   body={"confirm": False})
        check("restore with confirm:false rejected", s == 400, str(b))

        # --- Restore with no backup for the user must not wipe data ---
        s, b = req(args.port, "POST", "/api/restore", token=carol,
                   body={"confirm": True})
        check("restore with no backup rejected", s == 400, str(b))
        add_decision(args.port, carol, "CarolDecision")
        s, b = req(args.port, "POST", "/api/restore", token=carol,
                   body={"confirm": True})
        check("carol data survives no-backup restore",
              s == 400 and "CarolDecision" in list_titles(args.port, carol),
              str(b))

        # --- Malformed backup row is skipped, not written ---
        with open(os.path.join(tmp, "decisions_backup.txt"), "a") as f:
            f.write("not-a-decision-line\n")
            f.write("99|bad-date|Daily|5|AliceBad|alice\n")
        s, b = req(args.port, "POST", "/api/restore", token=alice,
                   body={"confirm": True})
        check("malformed backup rows skipped",
              s == 200 and b.get("skipped", 0) >= 1, str(b))
        check("no malformed row in decisions",
              all("AliceBad" not in t and "not-a-decision" not in t
                  for t in list_titles(args.port, alice)),
              str(list_titles(args.port, alice)))

        # --- Compatibility: old-format backup file still readable ---
        # An old backup written by the pre-redesign code (whole file
        # overwritten with one user's rows) must restore only the
        # caller's rows, not the other user's rows in the same file.
        with open(os.path.join(tmp, "decisions_backup.txt"), "w") as f:
            f.write("1|2026-11-05|Daily|5|OldAlice|alice\n")
            f.write("2|2026-11-05|Daily|5|OldBob|bob\n")
        s, b = req(args.port, "POST", "/api/restore", token=alice,
                   body={"confirm": True})
        check("old-format backup restores caller only",
              s == 200 and b.get("restored") == 1 and
              list_titles(args.port, alice) == ["OldAlice"],
              str(b))
        check("old-format backup did not leak bob to alice",
              "OldBob" not in list_titles(args.port, alice),
              str(list_titles(args.port, alice)))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"backup_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
