# Website Dashboard

A modern, responsive dashboard for the Personal Decision & Problem Solver,
built with plain HTML, CSS, and JavaScript — no build step, no CDN, no
external dependencies. The frontend is served by `server.py` on the same
origin, so it works offline on localhost.

## What is real, and what is not

**Real:** every button in the dashboard calls `server.py`, and `server.py`
reads and writes the same plain-text files the C++ console app uses, in
the same formats (see "Data files" below). A decision created in the
dashboard appears in the C++ app's Search/Filter/Sort/Backup/Delete, and
a transaction created in the C++ app appears in the dashboard's balance
and reports. This was tested both ways (see "Tested" below).

**Not claimed:** this is not a hosted, production web service. The C++
program itself has no HTTP server, so the dashboard does not talk to
the compiled C++ binary over HTTP — it talks to the same data files
through `server.py`. That is the honest architecture for a file-based
console app, and it is documented here rather than presented as
something else.

**Security warning:** the C++ app stores passwords in `users.txt` in
plain text, and this server keeps that format so existing users keep
working. Do NOT expose this server to the internet. Run it on
localhost only, for local use.

## How to run

From the repository root (important: the data files live in the
directory you run from, exactly like the C++ app):

```bash
python3 dashboard/server.py
# Dashboard: http://127.0.0.1:8000/
# Data directory (same files as the C++ app): <repo root>
```

Then open http://127.0.0.1:8000/ in a browser. Register (the first user
becomes ADMIN, like the C++ app), log in, and use the sections.

Options:

```bash
python3 dashboard/server.py --port 8001 --data-dir /path/to/data
python3 dashboard/server.py --help
```

Python 3.8+ is enough; only the standard library is used.

## Architecture

```
Browser (dashboard/index.html + style.css + app.js)
        │  fetch() to same origin, Bearer token in sessionStorage
        ▼
dashboard/server.py  (Python stdlib ThreadingHTTPServer, localhost only)
        │  reads / writes plain-text files
        ▼
users.txt, decisions.txt, transactions.txt, savings_goals.txt,
habit_log.txt, tasks.txt        ← also read/written by the C++ app
```

- Sessions are in-memory random tokens, never written to a file and
  never derived from a password.
- Validation mirrors the C++ rules: usernames without spaces, passwords
  8+ characters with a letter and a digit, urgency/importance/energy
  1–10, time 1–1440, real calendar dates, amounts ≥ 0.
- The Daily Decision, Priority, Budget, and Multi-Task calculations
  copy the C++ formulas exactly (see server.py comments).

## Dashboard sections

Login/Register, Overview (with decision history, backup, restore,
delete), Daily Decision (including Multi-Task Daily Decision, menu 43),
Task Management, Priority, Budget, Income/Expense, Savings, Habit
Tracker, Reports (weekly and monthly).

## API endpoints (all under the same origin; all except register/login need a Bearer token)

| Method | Endpoint | What it does |
|---|---|---|
| POST | /api/register | Create user (first user ADMIN) |
| POST | /api/login | Log in, returns a session token |
| POST | /api/logout | Invalidate the token |
| GET | /api/me, /api/overview | Who you are; totals for the overview cards |
| GET/POST/DELETE | /api/decisions | List, add, delete decision records |
| POST | /api/daily-decision | C++ Daily Decision logic + saves a Daily record |
| POST | /api/multi-task | C++ Multi-Task algorithm + saves MultiTask records |
| POST | /api/priority | Score = urgency×2 + importance×3, level thresholds as in C++ |
| GET/POST/PATCH/DELETE | /api/tasks | Task CRUD, sorted by score |
| GET | /api/budget?income=&expenses= | Remaining balance + C++ budget decision |
| GET/POST | /api/transactions | List / add transactions |
| GET/POST | /api/savings, POST /api/savings/add | Goals and adding savings |
| GET/POST | /api/habits, GET /api/habits/streak | Mark habit done; total + true consecutive streak |
| GET | /api/reports?month= / ?week_end= | Monthly / weekly transaction reports |
| POST | /api/backup, /api/restore | Copy decisions to/from decisions_backup.txt |

## Data files

| File | Format | Shared with C++? |
|---|---|---|
| users.txt | `username password ROLE` | Yes, identical |
| decisions.txt | `id\|date\|type\|priority\|title` | Yes, identical (dashboard uses today's date; C++ uses `-` when it has no date — both parse) |
| transactions.txt | `date\|type\|category\|amount\|note` | Yes, identical |
| savings_goals.txt | `name\|target\|saved` | Yes, identical |
| habit_log.txt | `habit\|date` | Yes, identical |
| tasks.txt | `id\|title\|urgency\|importance\|deadline\|status` | Dashboard extension — the C++ task list is in-memory only, so the dashboard needs its own persistent file. The C++ app ignores it. |

## Tested

Tested against a throwaway data directory (not the repo's real files):
every endpoint above was called with curl, including invalid inputs
(weak password, duplicate user, wrong login, invalid urgency, impossible
date, unknown goal, missing backup), and the resulting files were read
back and opened with the compiled C++ app — its Search, Balance,
Savings, and Habit Streak screens showed the dashboard's data. The
dashboard pages themselves were fetched from the running server
(index.html, style.css, app.js all return 200).

## Known limits (not hidden)

- One user at a time per browser tab is fine; concurrent writes from
  the C++ app and the dashboard at the exact same moment are guarded
  only by a server-side lock for API writes, not by file locking
  against the C++ process. Do not run both against the same files
  simultaneously for the same record.
- Passwords remain plain text (inherited from the C++ format).
- There is no email verification, password reset, or admin user
  management in the dashboard beyond what users.txt already allows.
