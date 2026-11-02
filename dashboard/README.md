# Website Dashboard

A modern, responsive dashboard for the Personal Decision & Problem Solver,
built with plain HTML, CSS, and JavaScript — no build step, no CDN, no
external dependencies. The frontend is served by the backend server on
the same origin, so it works offline on localhost.

## Which backend? (teacher requirement: C++ backend is mandatory)

**Primary backend: C++ (`cpp_server.cpp`).** The dashboard is served
and answered by C++ code: build it and run it, and every dashboard
button talks to a C++ HTTP server over `/api/*`. This is a genuine
C++ API layer, not just "the same text file".

**Why the earlier Python server alone was not enough:** sharing the
same text files is shared-file integration, not a C++ backend. A
teacher checking for a C++ backend would rightly not accept it on its
own. That is why `cpp_server.cpp` was added. The Python server
(`server.py`) is kept only as a fallback/reference with the identical
API; if both are present, use the C++ one.

**What the C++ server reuses, and what it does not:** the console
app's modules are interactive `cin`/`cout` functions, not a library,
so they cannot be called over HTTP as-is. `cpp_server.cpp` therefore
implements the same API, the same validation, the same formulas, and
the same file formats as those modules (each is commented with the
C++ module it mirrors), and it reads/writes the same files. A future
refactor could extract the console modules into a shared library that
both the console app and this server link against; that refactor is
listed under "Known limits" and was deliberately not done here, because
rewriting all console modules would risk breaking the tested console
app for no user-visible gain.

## What is real, and what is not

**Real:** every button in the dashboard calls the backend API, and the
backend reads and writes the same plain-text files the C++ console app
uses, in the same formats (see "Data files" below). A decision created
in the dashboard appears in the C++ app's Search/Filter/Sort/Backup/
Delete, and a transaction created in the C++ app appears in the
dashboard's balance and reports. This was tested both ways (see
"Tested" below), including concurrently (see "Concurrency").

**Not claimed:** this is not a hosted, production web service. There
is no HTTPS, no rate limiting, no password hashing (see "Security"),
and no hosted deployment. It is a localhost dashboard for a local,
file-based project.

**Security warning:** the C++ app stores passwords in `users.txt` in
plain text, and this server keeps that format so existing users keep
working. Do NOT expose this server to the internet. Run it on
localhost only, for local use.

## Architecture

```
Browser (index.html + style.css + app.js, no CDN, no build step)
        │  HTTP, same origin, localhost only
        ▼
┌──────────────────────────── PRIMARY BACKEND ────────────────────────────┐
│  C++ server: dashboard/cpp_server.cpp  ──►  /api/*  ──►  data files     │
│  (POSIX sockets on Linux, Winsock on Windows; see "Windows 11")        │
└──────────────────────────────────────────────────────────────────────────┘
        │  same files, same formats, same file-lock protocol
        ▼
C++ console app (main.cpp + modules)  ◄──►  users.txt, decisions.txt,
tasks.txt, transactions.txt, savings_goals.txt, habit_log.txt
        │
        └─►  FALLBACK ONLY: dashboard/server.py (Python stdlib, same API).
             Use it only if you cannot build the C++ server. It is NOT
             the primary backend, and it does NOT join the file-lock
             protocol for console-app writes (see "Concurrency").
```

Sections and their real backend endpoints: Overview (`/api/overview`,
`/api/decisions`), Search & History (`/api/decisions?search=&type=`),
Daily Decision (`/api/daily-decision`, `/api/multi-task`), Task
Management and Task Status (`/api/tasks`, PATCH status
Pending/In Progress/Completed), Priority (`/api/priority`), Decision
Explanation (`/api/decision-explanation`), Deadline Alerts
(`/api/deadlines`), Budget (`/api/budget`), Income/Expense
(`/api/transactions`), Savings (`/api/savings`, `/api/savings/add`),
Study Planner (`/api/study-planner`, calculated, not saved — like the
console module), Time Allocation (`/api/time-allocation`), Habit
Tracker (`/api/habits`, `/api/habits/streak`), Reports
(`/api/reports`), Profile (`/api/me`, ADMIN-only `/api/users`),
Settings (`/api/info`, `/api/change-password`, theme in browser only).
No section is a mock: every button either calls one of these
endpoints or, for theme only, changes the browser's own appearance.

## How to run — C++ backend (recommended)

From the repository root (important: the data files live in the
directory you run from, exactly like the C++ app):

```bash
g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server dashboard/cpp_server.cpp
./cpp_server
# Dashboard (C++ backend): http://127.0.0.1:8000/
# Data directory (same files as the C++ app): <repo root>
```

Then open http://127.0.0.1:8000/ in a browser. Register (the first user
becomes ADMIN, like the C++ app), log in, and use the sections.

Options: `./cpp_server --port 8001 --data-dir /path/to/data`,
`./cpp_server --help`. The server binds to 127.0.0.1 only, never
0.0.0.0, and serves only index.html, style.css, and app.js as static
files — data files such as users.txt are never served.

## Windows 11 — native build (no WSL required)

The C++ server and `file_lock.h` are cross-platform C++17. On
Windows 11, the POSIX parts are replaced at compile time:
sockets become Winsock (`WSAStartup`, `closesocket`, `ws2_32`),
`flock` becomes `LockFileEx`, `localtime_r` becomes `localtime_s`,
and session tokens use `random_device` instead of `/dev/urandom`.
The rest of the console app is standard C++17, so it builds the
same way.

**Option A — MinGW-w64 (recommended on Windows, free):**
install MSYS2, then in a MinGW-w64 terminal, from the repo root:

```bat
g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server.exe dashboard/cpp_server.cpp -lws2_32
cpp_server.exe
g++ -std=c++17 -Wall -Wextra -o project.exe *.cpp
```

**Option B — Visual Studio (MSVC):** open a "Developer Command
Prompt for VS", from the repo root:

```bat
cl /std:c++17 /EHsc dashboard\cpp_server.cpp ws2_32.lib
cpp_server.exe
cl /std:c++17 /EHsc *.cpp /Fe:project.exe
```

Then open http://127.0.0.1:8000/ in a browser. The data files are
the same ones the console app reads, in the same directory you run
from, exactly as on Linux.

**Honest build status:** the Windows build was verified by
cross-compiling both programs for x86-64 Windows with MinGW-w64
GCC 13 on Linux: `cpp_server.exe` and `project.exe` both build
with 0 warnings and are valid PE32+ executables. They were NOT
run on a physical Windows 11 machine in this development
environment (no Windows machine is available there), so the
first run on real Windows 11 should be checked with the steps
above before it is called "tested on Windows 11" in a report.
WSL is NOT required — it is only a fallback if neither MinGW
nor MSVC is available.

**Windows notes:** use a path without non-ASCII characters for
the data directory (the lock code uses the ANSI `CreateFileA`
path); the lock is `LockFileEx` on `<file>.lock`, the same
protocol as Linux `flock`, so a Windows console app and a
Windows C++ server protect each other the same way. A Linux
binary and a Windows binary cannot share one directory's locks
— they are different operating systems, not a code bug.

## How to run — Python fallback (same API, same files)

```bash
python3 dashboard/server.py
# Dashboard: http://127.0.0.1:8000/
```

Python 3.8+ is enough; only the standard library is used. Do not run
both servers on the same port at the same time.

## Concurrency (dashboard + console app at the same time)

Without a lock, this was a real bug, not just a theory. A synthetic
reproduction of the exact savings read-modify-write path (read the
saved value, add 100, write via a temp file and rename) run by two
processes at once gave 100 instead of 200 — one update was lost.
The same code path exists in the console app's `addSavingsAmount`,
in `delete_confirmation` (temp file + rename), and in
`appendDecisionRecord` (count, then append — two processes could
assign the same id).

Fix, now in place: `file_lock.h` in the repository root, and
`cpp_server.cpp` uses the same protocol. To protect `data.txt`, both
programs take an exclusive `flock` on `data.txt.lock` in the same
directory and hold it for the whole read-modify-write / count-append
operation. It is applied to decisions, savings, transactions, habits,
backup/restore, delete, and export in the console app, and to the
corresponding API writes in the C++ server.

Verified with the lock in place: 5 API savings-adds of 100 plus 5
console-app savings-adds of 100, run in parallel, gave exactly 1000;
3 API daily decisions plus 3 console daily decisions, run in
parallel, gave 6 records with unique ids 1–6 and no duplicates.

Remaining risk, stated honestly: read-only screens (search, filter,
sort, show transactions) do not take a lock, so a screen opened at
the exact moment of a write could show a partially written file, and
the lock is flock on Linux/macOS and LockFileEx on Windows (see "Windows 11"). Also,
two console-app processes that were built before this change do not
respect the lock at all, so old binaries must not be mixed with new
ones against the same files.

## Dashboard sections

Login/Register, Overview (with decision history, backup, restore,
delete), Search & History, Daily Decision (including Multi-Task Daily
Decision, menu 43), Task Management, Task Status, Priority, Decision
Explanation, Deadline Alerts, Budget, Income/Expense, Savings, Study
Planner, Time Allocation, Habit Tracker, Reports (weekly and monthly),
User Profile, Settings (theme, backend info, password change).

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
| GET/POST/PATCH/DELETE | /api/tasks | Task CRUD, sorted by score; status Pending/In Progress/Completed |
| POST | /api/study-planner, /api/time-allocation | Study plan (days x hours); 24-hour allocation check |
| POST | /api/decision-explanation | Formula, calculation, explanation, recommendation |
| GET | /api/deadlines | OVERDUE / DUE TODAY / UPCOMING alerts for open tasks |
| GET | /api/users (ADMIN) | Registered users, username + role only |
| POST | /api/change-password | Current-password check + new-password rules |
| GET | /api/info | Which backend is serving (C++ or Python fallback) |
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

Tested against throwaway data directories (not the repo's real files),
for both the Python server and the C++ server, with the same test
suite: every endpoint above was called with curl, including invalid
inputs (weak password, duplicate user, wrong login, invalid urgency,
impossible date, unknown goal, missing backup), and the resulting
files were read back and opened with the compiled C++ app — its
Search, Balance, Savings, and Habit Streak screens showed the
dashboard's data. The dashboard pages themselves were fetched from
the running server (index.html, style.css, app.js all return 200;
users.txt returns 404, never served). Every button in index.html was
checked against app.js: all 17 buttons have a listener, and every API
path the frontend calls is implemented by the C++ server. A malicious
decision title (`<img src=x onerror=...>`) was stored and then shown
escaped by the frontend (`&lt;img ...&gt;`), after the stored-XSS fix
in app.js (see "Security" below).

## Security audit (summary)

Checked and fixed, or inherited and documented:

- **Passwords:** plain text in users.txt, inherited from the C++
  format. Not fixed here, because hashing would break existing
  console users without a migration. Never returned by any API,
  never logged, never written to error_log.txt. Mitigation for now:
  localhost only, never exposed to the internet.
- **Sessions:** random tokens (C++: random_device; Python:
  secrets.token_hex), in-memory only, sent as a Bearer header, kept
  in sessionStorage (not localStorage, not a cookie, so no cookie
  CSRF). Tokens do not expire on the server — a future improvement
  is a timeout and a logout-all. Logout deletes the token.
- **File access:** static serving is allow-listed to index.html,
  style.css, app.js only. Verified: `/users.txt` returns 404.
  No user input is passed to a shell, no SQL, no path traversal
  through the static handler. Request bodies are capped at 1 MiB
  in the C++ server.
- **Stored XSS (fixed):** app.js previously put decision/task/
  transaction/savings/habit names into innerHTML without escaping.
  It now escapes `& < > " '` for every user-controlled value;
  messages use textContent, which was already safe.
- **Validation:** every endpoint re-validates on the server
  (ranges, real calendar dates, amount ≥ 0, username without
  spaces, password rules), so a tampered frontend request cannot
  bypass the console app's rules.
- **Not yet done:** no HTTPS, no rate limiting (a local attacker
  could brute-force logins — another reason for localhost only),
  no account lockout, no password reset, no admin user management
  beyond what users.txt already allows.

## Known limits (not hidden)

- Concurrent writes are now guarded by file locks (see
  "Concurrency"), but read-only screens do not lock. Old console
  binaries built before the lock change do not respect it, and a
  Windows binary and a Linux binary cannot share one directory's
  locks (different operating systems).
- The C++ server mirrors the console modules' logic instead of
  linking to them, because those modules are interactive
  `cin`/`cout` functions, not a library. Extracting them into a
  shared library is the clean next refactor, but it was not done
  here to avoid breaking the tested console app.
- Passwords remain plain text (inherited from the C++ format).
- There is no email verification, password reset, or admin user
  management in the dashboard beyond what users.txt already allows.
