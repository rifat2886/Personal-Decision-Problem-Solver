#!/usr/bin/env python3
"""
Personal Decision & Problem Solver — dashboard API server.

This is the real backend for dashboard/index.html. It is NOT a mock:
every endpoint reads or writes the same plain-text files the C++
console app uses, in the same formats, so the console app and the
dashboard can share one data directory.

Run from the repository root (so the data files are the same ones
the C++ app reads):

    python3 dashboard/server.py
    # then open http://127.0.0.1:8000

Options:
    --host 127.0.0.1   (default; bind to localhost only)
    --port 8000        (default)
    --data-dir PATH    (default: current working directory)

Data files and formats (identical to the C++ app):
    users.txt        username password ROLE        (space separated)
    decisions.txt    id|date|type|priority|title
    transactions.txt date|type|category|amount|note   (type: income/expense)
    savings_goals.txt name|target|saved
    habit_log.txt    habit|date                     (date: YYYY-MM-DD)
    tasks.txt        id|title|urgency|importance|deadline|status
        (shared by the dashboard and, since the task-persistence
         fix, the C++ console app too: console Task Prioritization
         appends here, Task Status and Deadline Alert load here.)

Security notes, stated honestly:
- Passwords: new accounts store only a PBKDF2-HMAC-SHA256 hash
  (format pbkdf2$100000$salt-hex$hash-hex, identical to the C++
  password_hash.h format). Old plaintext accounts still log in, and
  on a successful login their credential is immediately rewritten
  as a hash (upgrade on login). After migration, no plaintext
  remains. Do NOT expose this server to the internet; it is for
  local use only, on localhost, behind your own machine's security.
- Sessions are in-memory bearer tokens (random UUIDs). They are
  NOT passwords and are never written to a file.
- No username or password is ever written to error_log.txt.
Route 2, Phase 1 note: this Python server stays txt-only. It is
the local fallback, NOT the Render target (the C++ server is).
Its data formats are identical to the PostgreSQL schema in
dashboard/schema.sql, and the migration tool in tools/ moves txt
data into that schema; see docs/route2-phase1.md for the
compatibility check. A full Python Postgres mode was deliberately
NOT duplicated in Phase 1 (see that doc, "incomplete work").
- Only Python's standard library is used; there are no dependencies
  to install.
"""

import argparse
import datetime
import hashlib
import time
import json
import os
import re
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOCK = threading.Lock()
SESSIONS = {}  # token -> (username, expiry); expiry = now + 12h
SESSION_TTL = 12 * 60 * 60
LOGIN_FAILS = {}  # username -> (count, window_start)
LOGIN_FAIL_WINDOW = 300
LOGIN_FAIL_LIMIT = 5


def hash_password(password):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return "pbkdf2$100000$" + salt.hex() + "$" + dk.hex()


def verify_password(password, stored):
    # Google-only accounts (NULL password_hash) and the txt sentinel
    # must never authenticate: refuse an empty or sentinel credential.
    if not stored or stored == "!":
        return False
    if not stored.startswith("pbkdf2$"):
        return password == stored
    try:
        _, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
        return dk.hex() == hash_hex
    except Exception:
        return False


class FileLock:
    """Cross-platform lock on <datafile>.lock, same protocol as the
    C++ server: flock on POSIX, msvcrt.locking on Windows. Re-entrant
    per thread, so nested helper calls (e.g. append_decision) are safe.
    The in-process LOCK already serialises this server's own requests;
    this lock additionally protects against the console app and the
    C++ server writing the same files at the same time."""

    _counts = threading.local()

    def __init__(self, data_dir, name):
        self.data_dir = data_dir
        self.name = name
        self.handle = None

    def __enter__(self):
        counts = getattr(self._counts, "counts", None)
        if counts is None:
            counts = {}
            self._counts.counts = counts
        if counts.get(self.name, 0) > 0:
            counts[self.name] += 1
            return self
        counts[self.name] = 1
        path = os.path.join(self.data_dir, self.name + ".lock")
        self.handle = open(path, "a+b")
        try:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        except ImportError:
            import msvcrt
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        return self

    def __exit__(self, *exc):
        counts = getattr(self._counts, "counts", {})
        counts[self.name] -= 1
        if counts[self.name] > 0:
            return False
        try:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except ImportError:
            import msvcrt
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        self.handle.close()
        self.handle = None
        return False

# ---------------------------------------------------------------- helpers

def today_str():
    return datetime.date.today().isoformat()


def sanitize(value):
    """Mirror decision_store.h: '|' and newlines must not break a record."""
    return str(value).replace("|", "/").replace("\n", " ").replace("\r", " ")


def valid_date(value):
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return value[4] == "-" and value[7] == "-"


def valid_month(value):
    return isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}", value or "") is not None


def int_in(value, lo, hi):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if lo <= number <= hi else None


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_lines(data_dir, name):
    path = os.path.join(data_dir, name)
    if not os.path.exists(path):
        return []
    with FileLock(data_dir, name):
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return [line.rstrip("\n") for line in handle if line.strip() != ""]


def write_lines(data_dir, name, lines):
    path = os.path.join(data_dir, name)
    with FileLock(data_dir, name):
        with open(path, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")


def append_line(data_dir, name, line):
    path = os.path.join(data_dir, name)
    with FileLock(data_dir, name):
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


# ---------------------------------------------------------------- data access

# C1/C2 fix (2026-11-10): a missing users.txt means genuinely no
# users yet ({} — the first registrant becomes ADMIN). An existing
# but unreadable users.txt raises OSError instead of returning {};
# callers must treat that as an error (register answers 500), never
# as "no users yet" (which would grant ADMIN after a store failure).
def load_users(data_dir):
    users = {}
    for line in read_lines(data_dir, "users.txt"):
        parts = line.split()
        if len(parts) >= 3:
            users[parts[0]] = {"password": parts[1], "role": parts[2]}
    return users


def owner_visible(owner, user, data_dir):
    # Per-user isolation (Issue 2): owner field is the last pipe field.
    # Legacy records (no owner) are never deleted or silently assigned;
    # they are visible only when users.txt has exactly one user and
    # that user is the requester. ADMIN does NOT see other users' data.
    if owner == user:
        return True
    if owner:
        return False
    users = load_users(data_dir)
    return len(users) == 1 and user in users


def load_decisions(data_dir):
    out = []
    for line in read_lines(data_dir, "decisions.txt"):
        parts = line.split("|")
        if len(parts) < 5:
            continue
        try:
            priority = int(parts[3])
        except ValueError:
            continue
        out.append({"id": parts[0], "date": parts[1], "type": parts[2],
                    "priority": priority, "title": parts[4],
                    "owner": parts[5] if len(parts) >= 6 else ""})
    return out


def append_decision(data_dir, dtype, priority, title, owner=""):
    # Hold the decisions lock for the whole count-then-append, so a
    # concurrent console/C++ write cannot duplicate an id.
    with FileLock(data_dir, "decisions.txt"):
        return _append_decision_locked(data_dir, dtype, priority, title, owner)


def _append_decision_locked(data_dir, dtype, priority, title, owner=""):
    decisions = load_decisions(data_dir)
    next_id = 1
    for item in decisions:
        try:
            next_id = max(next_id, int(item["id"]) + 1)
        except ValueError:
            pass
    record = {"id": str(next_id), "date": today_str(), "type": sanitize(dtype),
              "priority": priority, "title": sanitize(title), "owner": owner}
    append_line(data_dir, "decisions.txt",
                "|".join([record["id"], record["date"], record["type"],
                          str(record["priority"]), record["title"], record["owner"]]))
    return record


def load_transactions(data_dir):
    out = []
    for line in read_lines(data_dir, "transactions.txt"):
        parts = line.split("|")
        if len(parts) < 5:
            continue
        try:
            amount = float(parts[3])
        except ValueError:
            continue
        out.append({"date": parts[0], "type": parts[1], "category": parts[2],
                    "amount": amount, "note": parts[4],
                    "owner": parts[5] if len(parts) >= 6 else ""})
    return out


def load_savings(data_dir):
    out = []
    for line in read_lines(data_dir, "savings_goals.txt"):
        parts = line.split("|")
        if len(parts) < 3:
            continue
        try:
            out.append({"name": parts[0], "target": float(parts[1]),
                        "saved": float(parts[2]),
                        "owner": parts[3] if len(parts) >= 4 else ""})
        except ValueError:
            continue
    return out


def save_savings(data_dir, goals):
    write_lines(data_dir, "savings_goals.txt",
                ["|".join([sanitize(g["name"]), str(g["target"]), str(g["saved"]),
                           sanitize(g.get("owner", ""))])
                 for g in goals])


def load_tasks(data_dir):
    out = []
    for line in read_lines(data_dir, "tasks.txt"):
        parts = line.split("|")
        if len(parts) < 6:
            continue
        try:
            out.append({"id": parts[0], "title": parts[1],
                        "urgency": int(parts[2]), "importance": int(parts[3]),
                        "deadline": parts[4], "status": parts[5],
                        "owner": parts[6] if len(parts) >= 7 else ""})
        except ValueError:
            continue
    out.sort(key=lambda t: (-(t["urgency"] * 2 + t["importance"] * 3), t["id"]))
    for task in out:
        task["score"] = task["urgency"] * 2 + task["importance"] * 3
    return out


def save_tasks(data_dir, tasks):
    write_lines(data_dir, "tasks.txt",
                ["|".join([sanitize(t["id"]), sanitize(t["title"]),
                           str(t["urgency"]), str(t["importance"]),
                           sanitize(t["deadline"]), sanitize(t["status"]),
                           sanitize(t.get("owner", ""))])
                 for t in tasks])


def habit_streak(data_dir, habit, user=None):
    dates = set()
    total = 0
    for line in read_lines(data_dir, "habit_log.txt"):
        parts = line.split("|")
        owner = parts[2] if len(parts) >= 3 else ""
        if user is not None and not owner_visible(owner, user, data_dir):
            continue
        if len(parts) >= 2 and parts[0] == habit and valid_date(parts[1]):
            total += 1
            dates.add(parts[1])
    if not dates:
        return {"habit": habit, "total": 0, "streak": 0, "latest": None}
    ordered = sorted(dates)
    streak = 1
    current = datetime.date.fromisoformat(ordered[-1])
    for i in range(len(ordered) - 2, -1, -1):
        previous = datetime.date.fromisoformat(ordered[i])
        if (current - previous).days == 1:
            streak += 1
            current = previous
        else:
            break
    return {"habit": habit, "total": total, "streak": streak,
            "latest": ordered[-1]}


def priority_level(score):
    if score >= 40:
        return "VERY HIGH"
    if score >= 30:
        return "HIGH"
    if score >= 20:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------- HTTP handler

class Handler(BaseHTTPRequestHandler):
    data_dir = "."
    static_dir = os.path.dirname(os.path.abspath(__file__))

    def log_message(self, *args):  # keep stdout clean
        pass

    def cors_origin(self):
        # CORS (Route 2, Phase 1): opt-in, exact origins only from
        # CORS_ORIGINS; "*" is ignored, as in the C++ server.
        origin = self.headers.get("Origin") or ""
        allowed = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",")]
        return origin if origin and origin in allowed else ""

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        origin = self.cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json(status, {"error": message})

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1048576:
            return None
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return None

    def current_user(self):
        auth = self.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            entry = SESSIONS.get(auth[7:])
            if entry is None:
                return None
            username, expiry = entry
            if expiry < time.time():
                SESSIONS.pop(auth[7:], None)
                return None
            return username
        return None

    def require_auth(self):
        user = self.current_user()
        if not user:
            self.send_error_json(401, "Please log in first.")
            return None
        return user

    # -- static files -------------------------------------------------
    def serve_static(self, path):
        if path in ("/", "/index.html"):
            name = "index.html"
        else:
            name = path.lstrip("/")
        if name not in ("index.html", "style.css", "app.js"):
            self.send_error_json(404, "Not found.")
            return
        full = os.path.join(self.static_dir, name)
        ctype = {"index.html": "text/html", "style.css": "text/css",
                 "app.js": "application/javascript"}[name]
        try:
            with open(full, "rb") as handle:
                body = handle.read()
        except OSError:
            self.send_error_json(404, "File not found.")
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routing ------------------------------------------------------
    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def do_PATCH(self):
        self.route()

    def do_DELETE(self):
        self.route()

    def do_OPTIONS(self):
        # Preflight for /api only, same rules as the C++ server.
        if self.path.startswith("/api/"):
            origin = self.cors_origin()
            if origin:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Max-Age", "86400")
                self.send_header("Vary", "Origin")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_error_json(403, "Origin not allowed.")
        else:
            self.send_error_json(404, "Not found.")

    def route(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        method = self.command
        if not path.startswith("/api/"):
            if method == "GET":
                self.serve_static(path)
            else:
                self.send_error_json(404, "Not found.")
            return

        with LOCK:
            self.route_api(method, path, query)

    def route_api(self, method, path, query):
        data_dir = self.data_dir

        # -- health (public, no data; Render health check) ------------
        if path == "/api/health" and method == "GET":
            return self.send_json(200, {"ok": True, "backend": "Python", "storage": "txt"})

        # -- auth (no token needed) -----------------------------------
        if path == "/api/register" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            username = body.get("username") or ""
            password = body.get("password") or ""
            # Security (public launch review, 2026-11-05): see the same
            # comment in dashboard/cpp_server.cpp. A username with a
            # newline (via a JSON "\n" escape, which json.loads turns into
            # a real newline) would split users.txt and overwrite another
            # user's line (account takeover in txt mode, verified before
            # this fix). Reject whitespace, control characters and '|'.
            if not username or any(ord(c) <= 32 or c == "|" for c in username):
                return self.send_error_json(400, "Username must not be empty or contain spaces, control characters, or '|'.")
            if len(password) < 8 or not any(c.isalpha() for c in password) \
                    or not any(c.isdigit() for c in password):
                return self.send_error_json(400, "Password must be 8+ characters with a letter and a digit.")
            # Auth fix (2026-11-09): see dashboard/cpp_server.cpp — when
            # confirm_password is supplied it must match the password.
            confirm = body.get("confirm_password") or ""
            if confirm and confirm != password:
                return self.send_error_json(400, "Passwords do not match.")
            # C1/C2 fix (2026-11-10): the user store could not be
            # read (users.txt exists but is unreadable). Answer 500
            # and create nothing — never treat the failure as "no
            # users yet" and grant ADMIN. The real error goes to
            # stderr only, never to the client.
            try:
                users = load_users(data_dir)
            except OSError as exc:
                print(f"[register] could not read user store: {exc}",
                      file=sys.stderr)
                return self.send_error_json(
                    500, "Could not create the account. Please try again later.")
            if username in users:
                return self.send_error_json(400, "Username already exists.")
            role = "ADMIN" if not users else "USER"
            append_line(data_dir, "users.txt", f"{username} {hash_password(password)} {role}")
            return self.send_json(201, {"username": username, "role": role})

        if path == "/api/login" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            username_in = body.get("username") or ""
            password_in = body.get("password") or ""
            now = time.time()
            count, window = LOGIN_FAILS.get(username_in, (0, now))
            if now - window > LOGIN_FAIL_WINDOW:
                count, window = 0, now
            if count >= LOGIN_FAIL_LIMIT:
                return self.send_error_json(429, "Too many failed logins. Try again later.")
            users = load_users(data_dir)
            user = users.get(username_in)
            if not user or not verify_password(password_in, user["password"]):
                LOGIN_FAILS[username_in] = (count + 1, window)
                return self.send_error_json(401, "Invalid username or password.")
            LOGIN_FAILS.pop(username_in, None)
            if not user["password"].startswith("pbkdf2$"):
                # Backward-compatible migration: plaintext that just
                # matched is rewritten as a hash.
                lines = [f"{u} {hash_password(password_in) if u == username_in else v['password']} {v['role']}" for u, v in users.items()]
                write_lines(data_dir, "users.txt", lines)
            token = secrets.token_hex(16)
            SESSIONS[token] = (body["username"], time.time() + SESSION_TTL)
            return self.send_json(200, {"username": body["username"],
                                        "role": user["role"], "token": token})

        if path == "/api/logout" and method == "POST":
            user = self.current_user()
            auth = self.headers.get("Authorization") or ""
            if auth.startswith("Bearer "):
                SESSIONS.pop(auth[7:], None)
            return self.send_json(200, {"ok": True, "username": user})

        # -- everything below needs a login ----------------------------
        user = self.require_auth()
        if not user:
            return
        users = load_users(data_dir)
        role = users.get(user, {}).get("role", "USER")

        # Gemini AI (Phase 2.1): the Python server never calls
        # Gemini and never handles the key; AI needs the C++ server.
        if path.startswith("/api/ai/"):
            return self.send_error_json(501, "AI requires the C++ server")

        # Google Sign-In (Phase 3): the Python server has no
        # token verification (no OpenSSL/JWKS support) and no
        # Google account storage; Google auth needs the C++
        # server. This sits after require_auth(), like the AI
        # 501 above, so an unauthenticated call still gets 401.
        if path.startswith("/api/auth/google") or path == "/api/auth/set-password":
            return self.send_error_json(501, "Google sign-in requires the C++ server")

        if path == "/api/me" and method == "GET":
            return self.send_json(200, {"username": user, "role": role})

        if path == "/api/overview" and method == "GET":
            decisions = [d for d in load_decisions(data_dir) if owner_visible(d.get("owner", ""), user, data_dir)]
            transactions = [x for x in load_transactions(data_dir) if owner_visible(x.get("owner", ""), user, data_dir)]
            savings = [g for g in load_savings(data_dir) if owner_visible(g.get("owner", ""), user, data_dir)]
            tasks = [x for x in load_tasks(data_dir) if owner_visible(x.get("owner", ""), user, data_dir)]
            income = sum(t["amount"] for t in transactions if t["type"] == "income")
            expense = sum(t["amount"] for t in transactions if t["type"] == "expense")
            habits = {}
            for line in read_lines(data_dir, "habit_log.txt"):
                parts = line.split("|")
                owner = parts[2] if len(parts) >= 3 else ""
                if len(parts) >= 2 and owner_visible(owner, user, data_dir):
                    habits[parts[0]] = habits.get(parts[0], 0) + 1
            return self.send_json(200, {
                "username": user, "role": role,
                "decisions": len(decisions),
                "tasks": len(tasks),
                "tasksPending": sum(1 for t in tasks if t["status"] == "Pending"),
                "income": income, "expense": expense, "balance": income - expense,
                "savingsGoals": len(savings),
                "savingsTarget": sum(g["target"] for g in savings),
                "savingsSaved": sum(g["saved"] for g in savings),
                "habits": habits,
            })

        if path == "/api/decisions" and method == "GET":
            decisions = [d for d in load_decisions(data_dir) if owner_visible(d.get("owner", ""), user, data_dir)]
            search = (query.get("search") or [""])[0].lower()
            dtype = (query.get("type") or [""])[0]
            if search:
                decisions = [d for d in decisions
                             if search in d["title"].lower() or search in d["type"].lower()]
            if dtype:
                decisions = [d for d in decisions if d["type"] == dtype]
            return self.send_json(200, decisions)

        if path == "/api/decisions" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            dtype = body.get("type") or "Daily"
            priority = int_in(body.get("priority"), 0, 1000)
            title = (body.get("title") or "").strip()
            if priority is None or not title:
                return self.send_error_json(400, "A decision needs a title and a numeric priority.")
            return self.send_json(201, append_decision(data_dir, dtype, priority, title, user))

        if path.startswith("/api/decisions/") and method == "DELETE":
            decision_id = path.rsplit("/", 1)[-1]
            lines = read_lines(data_dir, "decisions.txt")
            kept, found = [], False
            for line in lines:
                parts = line.split("|")
                owner = parts[5] if len(parts) >= 6 else ""
                if parts[0] == decision_id and owner_visible(owner, user, data_dir):
                    found = True
                    continue
                kept.append(line)
            if not found:
                return self.send_error_json(404, "Decision ID not found.")
            # Never report a delete the store did not carry out
            # (template-delete bug, 2026-11-10): a failed write must
            # answer 500, not a false 200.
            try:
                write_lines(data_dir, "decisions.txt", kept)
            except OSError:
                return self.send_error_json(500, "Could not delete the decision. Please try again later.")
            return self.send_json(200, {"deleted": decision_id})

        if path == "/api/daily-decision" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            available = int_in(body.get("availableTime"), 1, 1440)
            required = int_in(body.get("requiredTime"), 1, 100000)
            urgency = int_in(body.get("urgency"), 1, 10)
            importance = int_in(body.get("importance"), 1, 10)
            energy = int_in(body.get("energy"), 1, 10)
            if None in (available, required, urgency, importance, energy):
                return self.send_error_json(400, "Check the ranges: time 1-1440, urgency/importance/energy 1-10.")
            # Exact logic from daily_decision.cpp.
            if required > available:
                suggestion = "Divide the task into smaller parts."
            elif urgency >= 8 and importance >= 8:
                suggestion = "Complete this task first."
            elif importance >= 8 and energy <= 4:
                suggestion = "Take a short break, then do this task."
            elif urgency >= 7:
                suggestion = "Complete this task soon."
            else:
                suggestion = "Schedule this task for later."
            score = urgency * 2 + importance * 3
            record = append_decision(data_dir, "Daily", score,
                                     "Daily decision: " + suggestion, user)
            return self.send_json(200, {"suggestion": suggestion, "score": score,
                                        "record": record})

        if path == "/api/multi-task" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            energy_budget = int_in(body.get("availableEnergy"), 1, 100)
            time_budget = int_in(body.get("availableTime"), 1, 1440)
            tasks = body.get("tasks") or []
            if energy_budget is None or time_budget is None or not tasks or len(tasks) > 20:
                return self.send_error_json(400, "Give 1-20 tasks, energy 1-100, time 1-1440.")
            cleaned = []
            for task in tasks:
                urgency = int_in(task.get("deadlineUrgency"), 1, 10)
                energy = int_in(task.get("energy"), 1, 10)
                minutes = int_in(task.get("time"), 1, 1440)
                name = (task.get("name") or "").strip()
                if None in (urgency, energy, minutes) or not name:
                    return self.send_error_json(400, "Each task needs a name, urgency 1-10, energy 1-10, time 1-1440.")
                cleaned.append({"name": name, "deadlineUrgency": urgency,
                                "energy": energy, "time": minutes})
            # Same algorithm as multi_task_decision.cpp: stable sort by
            # deadline urgency descending, accept while both budgets fit.
            ordered = sorted(cleaned, key=lambda t: -t["deadlineUrgency"])
            recommended, skipped = [], []
            remaining_energy, remaining_time = energy_budget, time_budget
            for task in ordered:
                if task["energy"] <= remaining_energy and task["time"] <= remaining_time:
                    remaining_energy -= task["energy"]
                    remaining_time -= task["time"]
                    recommended.append(task)
                    append_decision(data_dir, "MultiTask", task["deadlineUrgency"] * 5,
                                    "Multi-task: " + task["name"], user)
                else:
                    skipped.append(task)
            return self.send_json(200, {"recommended": recommended, "skipped": skipped,
                                        "remainingEnergy": remaining_energy,
                                        "remainingTime": remaining_time})

        if path == "/api/priority" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            urgency = int_in(body.get("urgency"), 1, 10)
            importance = int_in(body.get("importance"), 1, 10)
            if urgency is None or importance is None:
                return self.send_error_json(400, "Urgency and importance must be 1-10.")
            score = urgency * 2 + importance * 3
            return self.send_json(200, {"score": score, "max": 50,
                                        "level": priority_level(score)})

        if path == "/api/tasks" and method == "GET":
            return self.send_json(200, [x for x in load_tasks(data_dir) if owner_visible(x.get("owner", ""), user, data_dir)])

        if path == "/api/tasks" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            urgency = int_in(body.get("urgency"), 1, 10)
            importance = int_in(body.get("importance"), 1, 10)
            title = (body.get("title") or "").strip()
            deadline = body.get("deadline") or ""
            if urgency is None or importance is None or not title:
                return self.send_error_json(400, "A task needs a title, urgency 1-10, importance 1-10.")
            if deadline and not valid_date(deadline):
                return self.send_error_json(400, "Deadline must be a real YYYY-MM-DD date, or blank.")
            tasks = load_tasks(data_dir)
            next_id = 1
            for task in tasks:
                try:
                    next_id = max(next_id, int(task["id"]) + 1)
                except ValueError:
                    pass
            task = {"id": str(next_id), "title": title, "urgency": urgency,
                    "importance": importance, "deadline": deadline, "status": "Pending",
                    "owner": user}
            tasks.append(task)
            save_tasks(data_dir, tasks)
            task["score"] = urgency * 2 + importance * 3
            return self.send_json(201, task)

        if path.startswith("/api/tasks/") and method in ("PATCH", "DELETE"):
            task_id = path.rsplit("/", 1)[-1]
            tasks = load_tasks(data_dir)
            found = None
            for task in tasks:
                if task["id"] == task_id and owner_visible(task.get("owner", ""), user, data_dir):
                    found = task
                    break
            if not found:
                return self.send_error_json(404, "Task not found.")
            if method == "DELETE":
                # Never report a delete the store did not carry out
                # (template-delete bug, 2026-11-10).
                try:
                    save_tasks(data_dir, [t for t in tasks if t["id"] != task_id])
                except OSError:
                    return self.send_error_json(500, "Could not delete the task. Please try again later.")
                return self.send_json(200, {"deleted": task_id})
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            status = body.get("status")
            if status not in ("Pending", "In Progress", "Completed"):
                return self.send_error_json(400, "Status must be Pending, In Progress, or Completed.")
            found["status"] = status
            if not found.get("owner"):
                found["owner"] = user
            save_tasks(data_dir, tasks)
            return self.send_json(200, found)

        if path == "/api/budget" and method == "GET":
            income = number((query.get("income") or [""])[0])
            expenses = number((query.get("expenses") or [""])[0])
            if income is None or expenses is None or income < 0 or expenses < 0:
                return self.send_error_json(400, "Income and expenses must be numbers >= 0.")
            remaining = income - expenses
            # Same decisions as budgetDecision() in budget.cpp.
            decision = ("Reduce expenses." if remaining < 0 else
                        "Income equals expenses." if remaining == 0 else
                        "Save money for the future.")
            return self.send_json(200, {"income": income, "expenses": expenses,
                                        "remaining": remaining, "decision": decision})

        if path == "/api/transactions" and method == "GET":
            return self.send_json(200, [x for x in load_transactions(data_dir) if owner_visible(x.get("owner", ""), user, data_dir)])

        if path == "/api/transactions" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            date = body.get("date") or ""
            ttype = body.get("type") or ""
            category = (body.get("category") or "").strip()
            amount = number(body.get("amount"))
            note = body.get("note") or ""
            if not valid_date(date) or ttype not in ("income", "expense") \
                    or not category or amount is None or amount < 0:
                return self.send_error_json(400, "Need a real date, type income/expense, a category, and an amount >= 0.")
            append_line(data_dir, "transactions.txt",
                        "|".join([date, ttype, sanitize(category),
                                  str(amount), sanitize(note), user]))
            return self.send_json(201, {"date": date, "type": ttype,
                                        "category": category, "amount": amount, "note": note})

        if path == "/api/savings" and method == "GET":
            return self.send_json(200, [g for g in load_savings(data_dir) if owner_visible(g.get("owner", ""), user, data_dir)])

        if path == "/api/savings" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            name = (body.get("name") or "").strip()
            target = number(body.get("target"))
            if not name or target is None or target <= 0:
                return self.send_error_json(400, "A goal needs a name and a target > 0.")
            goals = load_savings(data_dir)
            if any(g["name"] == name and owner_visible(g.get("owner", ""), user, data_dir) for g in goals):
                return self.send_error_json(400, "A goal with that name already exists.")
            goals.append({"name": name, "target": target, "saved": 0, "owner": user})
            save_savings(data_dir, goals)
            return self.send_json(201, {"name": name, "target": target, "saved": 0})

        if path == "/api/savings/add" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            name = body.get("name") or ""
            amount = number(body.get("amount"))
            if amount is None or amount <= 0:
                return self.send_error_json(400, "Amount must be > 0.")
            goals = load_savings(data_dir)
            for goal in goals:
                if goal["name"] == name and owner_visible(goal.get("owner", ""), user, data_dir):
                    if not goal.get("owner"):
                        goal["owner"] = user
                    goal["saved"] += amount
                    save_savings(data_dir, goals)
                    return self.send_json(200, goal)
            return self.send_error_json(404, "Goal not found.")

        if path == "/api/habits" and method == "GET":
            habits = {}
            for line in read_lines(data_dir, "habit_log.txt"):
                parts = line.split("|")
                owner = parts[2] if len(parts) >= 3 else ""
                if len(parts) >= 2 and owner_visible(owner, user, data_dir):
                    habits.setdefault(parts[0], []).append(parts[1])
            return self.send_json(200, [{"habit": name, "dates": sorted(dates)}
                                        for name, dates in sorted(habits.items())])

        if path == "/api/habits" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            habit = (body.get("habit") or "").strip()
            date = body.get("date") or today_str()
            if not habit or not valid_date(date):
                return self.send_error_json(400, "Need a habit name and a real YYYY-MM-DD date.")
            append_line(data_dir, "habit_log.txt", f"{sanitize(habit)}|{date}|{user}")
            return self.send_json(201, habit_streak(data_dir, habit, user))

        if path == "/api/habits/streak" and method == "GET":
            habit = (query.get("habit") or [""])[0]
            if not habit:
                return self.send_error_json(400, "Give a habit name, for example ?habit=Reading.")
            return self.send_json(200, habit_streak(data_dir, habit, user))

        if path == "/api/reports" and method == "GET":
            transactions = [x for x in load_transactions(data_dir) if owner_visible(x.get("owner", ""), user, data_dir)]
            month = (query.get("month") or [""])[0]
            week_end = (query.get("week_end") or [""])[0]
            if month:
                if not valid_month(month):
                    return self.send_error_json(400, "Month must be YYYY-MM.")
                selected = [t for t in transactions if t["date"].startswith(month)]
                label = f"Monthly report for {month}"
            elif week_end:
                if not valid_date(week_end):
                    return self.send_error_json(400, "Week end must be a real YYYY-MM-DD date.")
                end = datetime.date.fromisoformat(week_end)
                selected = []
                for t in transactions:
                    if not valid_date(t["date"]):
                        continue
                    delta = (end - datetime.date.fromisoformat(t["date"])).days
                    if 0 <= delta <= 6:
                        selected.append(t)
                label = f"Weekly report ending {week_end}"
            else:
                return self.send_error_json(400, "Give ?month=YYYY-MM or ?week_end=YYYY-MM-DD.")
            income = sum(t["amount"] for t in selected if t["type"] == "income")
            expense = sum(t["amount"] for t in selected if t["type"] == "expense")
            return self.send_json(200, {"label": label, "transactions": selected,
                                        "income": income, "expense": expense,
                                        "balance": income - expense,
                                        "count": len(selected)})

        if path == "/api/backup" and method == "POST":
            # Per-user backup (same redesign as cpp_server.cpp): keep
            # other users' (and hidden legacy) backup rows, then append
            # only the caller's current visible rows. Format unchanged,
            # so old backups stay readable.
            lines = [ln for ln in read_lines(data_dir, "decisions.txt") if owner_visible((ln.split("|")[5] if len(ln.split("|")) >= 6 else ""), user, data_dir)]
            # Mirror backup_restore.cpp: refuse to create an empty
            # backup when there is no source file at all.
            if not os.path.exists(os.path.join(data_dir, "decisions.txt")):
                return self.send_error_json(400, "No decision file found to back up.")
            kept_backup = []
            if os.path.exists(os.path.join(data_dir, "decisions_backup.txt")):
                kept_backup = [ln for ln in read_lines(data_dir, "decisions_backup.txt") if not owner_visible((ln.split("|")[5] if len(ln.split("|")) >= 6 else ""), user, data_dir)]
            write_lines(data_dir, "decisions_backup.txt", kept_backup + lines)
            return self.send_json(200, {"backedUp": len(lines)})

        if path == "/api/restore" and method == "POST":
            body = self.read_json()
            if not isinstance(body, dict) or body.get("confirm") is not True:
                return self.send_error_json(400, "Restore requires confirm:true in the request body. This replaces your current decisions with your backup.")
            if not os.path.exists(os.path.join(data_dir, "decisions_backup.txt")):
                return self.send_error_json(400, "No backup file found.")
            lines = [ln for ln in read_lines(data_dir, "decisions_backup.txt") if owner_visible((ln.split("|")[5] if len(ln.split("|")) >= 6 else ""), user, data_dir)]
            if not lines:
                return self.send_error_json(400, "No backup found for this user. Nothing was changed.")
            current = read_lines(data_dir, "decisions.txt")
            kept = [ln for ln in current if not owner_visible((ln.split("|")[5] if len(ln.split("|")) >= 6 else ""), user, data_dir)]
            kept_ids = {ln.split("|")[0] for ln in kept if ln.split("|")}
            restored, skipped = [], 0
            for ln in lines:
                parts = ln.split("|")
                if len(parts) < 5 or not parts[0].isdigit() or not valid_date(parts[1]) or parts[0] in kept_ids:
                    skipped += 1
                    continue
                restored.append(ln)
            write_lines(data_dir, "decisions.txt", kept + restored)
            return self.send_json(200, {"restored": len(restored), "skipped": skipped})

        # ---- new sections (mirror the console modules of the same name) ----
        if path == "/api/info" and method == "GET":
            return self.send_json(200, {"backend": "Python", "server": "server.py (fallback)",
                                        "dataFiles": ["users.txt", "decisions.txt", "tasks.txt", "transactions.txt", "savings_goals.txt", "habit_log.txt"]})
        if path == "/api/users" and method == "GET":
            if role != "ADMIN":
                return self.send_error_json(403, "Only an ADMIN can list users.")
            users = load_users(data_dir)
            return self.send_json(200, [{"username": u, "role": v["role"]} for u, v in users.items()])
        if path == "/api/change-password" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            users = load_users(data_dir)
            if user not in users or not verify_password(body.get("currentPassword") or "", users[user]["password"]):
                return self.send_error_json(400, "Wrong current password.")
            new_pw = body.get("newPassword", "")
            if len(new_pw) < 8 or not any(c.isalpha() for c in new_pw) or not any(c.isdigit() for c in new_pw):
                return self.send_error_json(400, "Password must be 8+ characters with a letter and a digit.")
            lines = [f"{u} {hash_password(new_pw) if u == user else v['password']} {v['role']}" for u, v in users.items()]
            write_lines(data_dir, "users.txt", lines)
            return self.send_json(200, {"ok": True})
        if path == "/api/study-planner" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            subject = (body.get("subject") or "").strip()
            days, hours = body.get("days"), body.get("hours")
            if not subject or not isinstance(days, int) or not isinstance(hours, int) or not 1 <= days <= 365 or not 1 <= hours <= 24:
                return self.send_error_json(400, "A plan needs a subject, days 1-365, hours 1-24.")
            return self.send_json(200, {"subject": subject, "days": days, "hoursPerDay": hours, "totalHours": days * hours,
                                        "plan": [{"day": d, "text": f"Day {d}: {subject} - {hours} hour(s)"} for d in range(1, days + 1)]})
        if path == "/api/time-allocation" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            vals = {}
            for k in ("sleep", "study", "work", "other"):
                v = body.get(k)
                if not isinstance(v, int) or not 0 <= v <= 24:
                    return self.send_error_json(400, "Each value must be 0-24 hours.")
                vals[k] = v
            total = sum(vals.values())
            return self.send_json(200, {**vals, "total": total,
                                        "remaining": None if total > 24 else 24 - total,
                                        "warning": "Total exceeds 24 hours!" if total > 24 else None})
        if path == "/api/decision-explanation" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            urgency, importance = body.get("urgency"), body.get("importance")
            if not isinstance(urgency, int) or not isinstance(importance, int) or not 1 <= urgency <= 10 or not 1 <= importance <= 10:
                return self.send_error_json(400, "Urgency and importance must be 1-10.")
            score = urgency * 2 + importance * 3
            if score >= 40:
                level, rec = "Very high priority.", "Complete this task first."
            elif score >= 30:
                level, rec = "High priority.", "Schedule it soon."
            elif score >= 20:
                level, rec = "Medium priority.", "Plan it after higher-priority tasks."
            else:
                level, rec = "Low priority based on this score.", "Schedule it when time is available."
            return self.send_json(200, {"urgency": urgency, "importance": importance, "score": score,
                                        "formula": "Formula: (Urgency x 2) + (Importance x 3)",
                                        "calculation": f"Calculation: ({urgency} x 2) + ({importance} x 3) = {score}/50",
                                        "explanation": level, "recommendation": rec})
        if path == "/api/deadlines" and method == "GET":
            today = (query.get("today") or [datetime.date.today().isoformat()])[0]
            if not valid_date(today):
                return self.send_error_json(400, "Today must be a real YYYY-MM-DD date.")
            out = []
            for t in [x for x in load_tasks(data_dir) if owner_visible(x.get("owner", ""), user, data_dir)]:
                if t["status"] == "Completed":
                    continue
                dl = t["deadline"]
                if len(dl) != 10 or dl[4] != "-" or dl[7] != "-":
                    alert = "CHECK"
                elif dl < today:
                    alert = "OVERDUE"
                elif dl == today:
                    alert = "DUE TODAY"
                else:
                    alert = "UPCOMING"
                out.append({"id": t["id"], "title": t["title"], "deadline": dl, "status": t["status"], "alert": alert})
            return self.send_json(200, out)

        # ---- team-completion endpoints (mirror the console modules) ----
        if path == "/api/compare-options" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            try:
                n1, n2 = (body.get("name1") or "").strip(), (body.get("name2") or "").strip()
                b1, c1, r1 = body["benefit1"], body["cost1"], body["risk1"]
                b2, c2, r2 = body["benefit2"], body["cost2"], body["risk2"]
            except Exception:
                return self.send_error_json(400, "Two options need names and benefit/cost/risk 1-10.")
            if not n1 or not n2 or any(not isinstance(v, int) or not 1 <= v <= 10 for v in (b1, c1, r1, b2, c2, r2)):
                return self.send_error_json(400, "Two options need names and benefit/cost/risk 1-10.")
            s1, s2 = b1 * 3 - c1 - r1, b2 * 3 - c2 - r2
            return self.send_json(200, {"name1": n1, "score1": s1, "name2": n2, "score2": s2,
                                        "suggested": n1 if s1 > s2 else n2 if s2 > s1 else None, "equal": s1 == s2})
        if path == "/api/admin" and method == "GET":
            if role != "ADMIN":
                return self.send_error_json(403, "Only an ADMIN can view the admin panel.")
            users = load_users(data_dir)
            admins = sum(1 for v in users.values() if v["role"] == "ADMIN")
            return self.send_json(200, {"total": len(users), "admins": admins, "users": len(users) - admins,
                                        "list": [{"username": u, "role": v["role"]} for u, v in users.items()]})
        if path == "/api/export" and method == "GET":
            fmt = (query.get("format") or ["txt"])[0]
            if fmt not in ("txt", "csv"):
                return self.send_error_json(400, "Format must be txt or csv.")
            import os as _os
            if not _os.path.exists(_os.path.join(data_dir, "transactions.txt")):
                return self.send_error_json(400, "No transactions file found to export.")
            lines = [ln for ln in read_lines(data_dir, "transactions.txt") if owner_visible((ln.split("|")[5] if len(ln.split("|")) >= 6 else ""), user, data_dir)]
            if fmt == "txt":
                content = "PERSONAL FINANCIAL REPORT\n========================\n\n" + "".join(l + "\n" for l in lines)
                with open(_os.path.join(data_dir, "financial_report.txt"), "w", encoding="utf-8") as f:
                    f.write(content)
                filename = "financial_report.txt"
            else:
                out = ["Date,Type,Category,Amount,Note"]
                for l in lines:
                    parts = l.split("|")
                    if len(parts) >= 5:
                        out.append(f"{parts[0]},{parts[1]},{parts[2]},{parts[3]},\"{parts[4]}\"")
                content = "\n".join(out) + "\n"
                with open(_os.path.join(data_dir, "financial_report.csv"), "w", encoding="utf-8") as f:
                    f.write(content)
                filename = "financial_report.csv"
            return self.send_json(200, {"format": fmt, "filename": filename, "content": content})
        if path == "/api/problem-solver" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            problem = (body.get("problem") or "").strip()
            difficulty, time_m = body.get("difficulty"), body.get("time")
            if not problem or not isinstance(difficulty, int) or not 1 <= difficulty <= 5 or not isinstance(time_m, int) or time_m <= 0:
                return self.send_error_json(400, "A problem needs a name, difficulty 1-5, and time > 0 minutes.")
            if difficulty <= 2 and time_m >= 15:
                suggestion = "Solve the problem step by step."
            elif difficulty >= 4:
                suggestion = "Divide the problem into smaller tasks."
            elif time_m < 15:
                suggestion = "Make a short and simple plan."
            else:
                suggestion = "Plan your work and start solving."
            rec = append_decision(data_dir, "Problem", difficulty, f"Problem: {problem} - {suggestion}", user)
            return self.send_json(200, {"suggestion": suggestion, "record": rec})
        if path == "/api/daily-summary" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            income, expenses = body.get("income"), body.get("expenses")
            completed, planned = body.get("habitsCompleted"), body.get("habitsPlanned")
            if (not isinstance(income, (int, float)) or income < 0 or not isinstance(expenses, (int, float)) or expenses < 0
                    or not isinstance(completed, int) or completed < 0 or not isinstance(planned, int) or planned <= 0 or completed > planned):
                return self.send_error_json(400, "Need income/expenses >= 0, planned > 0, and completed 0..planned.")
            balance = income - expenses
            rate = completed * 100.0 / planned
            line = f"User: {user}, Income: {income:.2f}, Expenses: {expenses:.2f}, Balance: {balance:.2f}, Habit completion: {rate:.2f}%"
            append_line(data_dir, "daily_report.txt", line)
            return self.send_json(200, {"income": income, "expenses": expenses, "balance": balance, "habitRate": rate})
        if path == "/api/habit-decision" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            completed, planned = body.get("completed"), body.get("planned")
            if not isinstance(planned, int) or planned <= 0 or not isinstance(completed, int) or completed < 0 or completed > planned:
                return self.send_error_json(400, "Need planned > 0 and completed 0..planned.")
            pct = completed * 100.0 / planned
            msg = ("Excellent! You completed all planned habits." if completed == planned else
                   "Good progress! Keep going." if pct >= 50 else "Try making a simpler plan tomorrow.")
            return self.send_json(200, {"percentage": pct, "message": msg})
        if path == "/api/habit-streak-calc" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            prev, today = body.get("previousDays"), body.get("completedToday")
            if not isinstance(prev, int) or prev < 0 or today not in (0, 1):
                return self.send_error_json(400, "Need previousDays >= 0 and completedToday 0 or 1.")
            streak = prev + 1 if today == 1 else 0
            return self.send_json(200, {"streak": streak, "message": "" if today == 1 else "Start a new streak tomorrow!"})
        if path == "/api/savings-calculator" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            target, current, monthly = body.get("target"), body.get("current"), body.get("monthly")
            if (not isinstance(target, (int, float)) or target <= 0 or not isinstance(current, (int, float)) or current < 0
                    or not isinstance(monthly, (int, float)) or monthly <= 0):
                return self.send_error_json(400, "Need target > 0, current >= 0, monthly > 0.")
            if current >= target:
                return self.send_json(200, {"remaining": 0, "months": 0, "message": "Congratulations! Your goal is complete."})
            remaining = target - current
            months = int((remaining + monthly - 0.01) / monthly)
            return self.send_json(200, {"remaining": remaining, "months": months, "message": ""})
        if path == "/api/error-log" and method == "GET":
            return self.send_json(200, read_lines(data_dir, "error_log.txt"))

        return self.send_error_json(404, "Unknown API endpoint.")


def main():
    parser = argparse.ArgumentParser(description="Dashboard API server")
    parser.add_argument("--host", default="127.0.0.1")
    # Render sets PORT; an explicit --port still wins over it.
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--data-dir", default=os.getcwd())
    args = parser.parse_args()

    Handler.data_dir = os.path.abspath(args.data_dir)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Dashboard: http://{args.host}:{args.port}/", flush=True)
    print(f"Data directory (same files as the C++ app): {Handler.data_dir}", flush=True)
    if args.host in ("127.0.0.1", "localhost"):
        print("Press Ctrl+C to stop. This server binds to localhost only.", flush=True)
    else:
        print("WARNING: LAN mode. Use only on a trusted Wi-Fi network, stop the server when done, and NEVER port-forward it to the public internet.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
