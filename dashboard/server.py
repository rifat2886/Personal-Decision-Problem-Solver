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
        (dashboard extension: the C++ task list is in-memory only,
         so the dashboard persists tasks in this new file. The C++
         app ignores it; it does not break any existing file.)

Security notes, stated honestly:
- Passwords are stored in users.txt exactly as the C++ app stores
  them (plain text, space-separated). This server does NOT change
  that format, because changing it would break existing C++ users.
  Do NOT expose this server to the internet; it is for local use
  only, on localhost, behind your own machine's security.
- Sessions are in-memory bearer tokens (random UUIDs). They are
  NOT passwords and are never written to a file.
- No username or password is ever written to error_log.txt.
- Only Python's standard library is used; there are no dependencies
  to install.
"""

import argparse
import datetime
import json
import os
import re
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOCK = threading.Lock()
SESSIONS = {}  # token -> username

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
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return [line.rstrip("\n") for line in handle if line.strip() != ""]


def write_lines(data_dir, name, lines):
    path = os.path.join(data_dir, name)
    with open(path, "w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")


def append_line(data_dir, name, line):
    path = os.path.join(data_dir, name)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


# ---------------------------------------------------------------- data access

def load_users(data_dir):
    users = {}
    for line in read_lines(data_dir, "users.txt"):
        parts = line.split()
        if len(parts) >= 3:
            users[parts[0]] = {"password": parts[1], "role": parts[2]}
    return users


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
                    "priority": priority, "title": "|".join(parts[4:])})
    return out


def append_decision(data_dir, dtype, priority, title):
    decisions = load_decisions(data_dir)
    next_id = 1
    for item in decisions:
        try:
            next_id = max(next_id, int(item["id"]) + 1)
        except ValueError:
            pass
    record = {"id": str(next_id), "date": today_str(), "type": sanitize(dtype),
              "priority": priority, "title": sanitize(title)}
    append_line(data_dir, "decisions.txt",
                "|".join([record["id"], record["date"], record["type"],
                          str(record["priority"]), record["title"]]))
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
                    "amount": amount, "note": "|".join(parts[4:])})
    return out


def load_savings(data_dir):
    out = []
    for line in read_lines(data_dir, "savings_goals.txt"):
        parts = line.split("|")
        if len(parts) < 3:
            continue
        try:
            out.append({"name": parts[0], "target": float(parts[1]),
                        "saved": float(parts[2])})
        except ValueError:
            continue
    return out


def save_savings(data_dir, goals):
    write_lines(data_dir, "savings_goals.txt",
                ["|".join([sanitize(g["name"]), str(g["target"]), str(g["saved"])])
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
                        "deadline": parts[4], "status": parts[5]})
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
                           sanitize(t["deadline"]), sanitize(t["status"])])
                 for t in tasks])


def habit_streak(data_dir, habit):
    dates = set()
    total = 0
    for line in read_lines(data_dir, "habit_log.txt"):
        parts = line.split("|")
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

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json(status, {"error": message})

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return None

    def current_user(self):
        auth = self.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            return SESSIONS.get(auth[7:])
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

        # -- auth (no token needed) -----------------------------------
        if path == "/api/register" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            username = body.get("username") or ""
            password = body.get("password") or ""
            if not username or " " in username:
                return self.send_error_json(400, "Username must not be empty or contain spaces.")
            if len(password) < 8 or not any(c.isalpha() for c in password) \
                    or not any(c.isdigit() for c in password):
                return self.send_error_json(400, "Password must be 8+ characters with a letter and a digit.")
            users = load_users(data_dir)
            if username in users:
                return self.send_error_json(400, "Username already exists.")
            role = "ADMIN" if not users else "USER"
            append_line(data_dir, "users.txt", f"{username} {password} {role}")
            return self.send_json(201, {"username": username, "role": role})

        if path == "/api/login" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            users = load_users(data_dir)
            user = users.get(body.get("username") or "")
            if not user or user["password"] != (body.get("password") or ""):
                return self.send_error_json(401, "Invalid username or password.")
            token = secrets.token_hex(16)
            SESSIONS[token] = body["username"]
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

        if path == "/api/me" and method == "GET":
            return self.send_json(200, {"username": user, "role": role})

        if path == "/api/overview" and method == "GET":
            decisions = load_decisions(data_dir)
            transactions = load_transactions(data_dir)
            savings = load_savings(data_dir)
            tasks = load_tasks(data_dir)
            income = sum(t["amount"] for t in transactions if t["type"] == "income")
            expense = sum(t["amount"] for t in transactions if t["type"] == "expense")
            habits = {}
            for line in read_lines(data_dir, "habit_log.txt"):
                parts = line.split("|")
                if len(parts) >= 2:
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
            decisions = load_decisions(data_dir)
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
            return self.send_json(201, append_decision(data_dir, dtype, priority, title))

        if path.startswith("/api/decisions/") and method == "DELETE":
            decision_id = path.rsplit("/", 1)[-1]
            lines = read_lines(data_dir, "decisions.txt")
            kept, found = [], False
            for line in lines:
                if line.split("|", 1)[0] == decision_id:
                    found = True
                    continue
                kept.append(line)
            if not found:
                return self.send_error_json(404, "Decision ID not found.")
            write_lines(data_dir, "decisions.txt", kept)
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
                                     "Daily decision: " + suggestion)
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
                                    "Multi-task: " + task["name"])
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
            return self.send_json(200, load_tasks(data_dir))

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
                    "importance": importance, "deadline": deadline, "status": "Pending"}
            tasks.append(task)
            save_tasks(data_dir, tasks)
            task["score"] = urgency * 2 + importance * 3
            return self.send_json(201, task)

        if path.startswith("/api/tasks/") and method in ("PATCH", "DELETE"):
            task_id = path.rsplit("/", 1)[-1]
            tasks = load_tasks(data_dir)
            found = None
            for task in tasks:
                if task["id"] == task_id:
                    found = task
                    break
            if not found:
                return self.send_error_json(404, "Task not found.")
            if method == "DELETE":
                save_tasks(data_dir, [t for t in tasks if t["id"] != task_id])
                return self.send_json(200, {"deleted": task_id})
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            status = body.get("status")
            if status not in ("Pending", "In Progress", "Completed"):
                return self.send_error_json(400, "Status must be Pending, In Progress, or Completed.")
            found["status"] = status
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
            return self.send_json(200, load_transactions(data_dir))

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
                                  str(amount), sanitize(note)]))
            return self.send_json(201, {"date": date, "type": ttype,
                                        "category": category, "amount": amount, "note": note})

        if path == "/api/savings" and method == "GET":
            return self.send_json(200, load_savings(data_dir))

        if path == "/api/savings" and method == "POST":
            body = self.read_json()
            if body is None:
                return self.send_error_json(400, "Invalid JSON.")
            name = (body.get("name") or "").strip()
            target = number(body.get("target"))
            if not name or target is None or target <= 0:
                return self.send_error_json(400, "A goal needs a name and a target > 0.")
            goals = load_savings(data_dir)
            if any(g["name"] == name for g in goals):
                return self.send_error_json(400, "A goal with that name already exists.")
            goals.append({"name": name, "target": target, "saved": 0})
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
                if goal["name"] == name:
                    goal["saved"] += amount
                    save_savings(data_dir, goals)
                    return self.send_json(200, goal)
            return self.send_error_json(404, "Goal not found.")

        if path == "/api/habits" and method == "GET":
            habits = {}
            for line in read_lines(data_dir, "habit_log.txt"):
                parts = line.split("|")
                if len(parts) >= 2:
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
            append_line(data_dir, "habit_log.txt", f"{sanitize(habit)}|{date}")
            return self.send_json(201, habit_streak(data_dir, habit))

        if path == "/api/habits/streak" and method == "GET":
            habit = (query.get("habit") or [""])[0]
            if not habit:
                return self.send_error_json(400, "Give a habit name, for example ?habit=Reading.")
            return self.send_json(200, habit_streak(data_dir, habit))

        if path == "/api/reports" and method == "GET":
            transactions = load_transactions(data_dir)
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
            lines = read_lines(data_dir, "decisions.txt")
            # Mirror backup_restore.cpp: refuse to create an empty
            # backup when there is no source file at all.
            if not os.path.exists(os.path.join(data_dir, "decisions.txt")):
                return self.send_error_json(400, "No decision file found to back up.")
            write_lines(data_dir, "decisions_backup.txt", lines)
            return self.send_json(200, {"backedUp": len(lines)})

        if path == "/api/restore" and method == "POST":
            if not os.path.exists(os.path.join(data_dir, "decisions_backup.txt")):
                return self.send_error_json(400, "No backup file found.")
            lines = read_lines(data_dir, "decisions_backup.txt")
            write_lines(data_dir, "decisions.txt", lines)
            return self.send_json(200, {"restored": len(lines)})

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
            if user not in users or users[user]["password"] != body.get("currentPassword"):
                return self.send_error_json(400, "Wrong current password.")
            new_pw = body.get("newPassword", "")
            if len(new_pw) < 8 or not any(c.isalpha() for c in new_pw) or not any(c.isdigit() for c in new_pw):
                return self.send_error_json(400, "Password must be 8+ characters with a letter and a digit.")
            lines = [f"{u} {new_pw if u == user else v['password']} {v['role']}" for u, v in users.items()]
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
            for t in load_tasks(data_dir):
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

        return self.send_error_json(404, "Unknown API endpoint.")


def main():
    parser = argparse.ArgumentParser(description="Dashboard API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default=os.getcwd())
    args = parser.parse_args()

    Handler.data_dir = os.path.abspath(args.data_dir)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Dashboard: http://{args.host}:{args.port}/", flush=True)
    print(f"Data directory (same files as the C++ app): {Handler.data_dir}", flush=True)
    print("Press Ctrl+C to stop. This server binds to localhost only.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
