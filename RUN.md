# How to run Personal Decision & Problem Solver

No Node, no npm, no database, no external packages. You need only a C++17
compiler (and Python 3 if you want the fallback server).

## Easiest start (no commands to remember)

Windows 11:
- Dashboard (website): double-click `start-dashboard.bat`, then open
  http://127.0.0.1:8000/ in your browser.
- Console app: double-click `start-console.bat`.

Linux/macOS:
- Dashboard: `./start-dashboard.sh`, then open http://127.0.0.1:8000/
- Console app: `./start-console.sh`

First time? Click "Login / Register", then Register. The first account
you create becomes ADMIN. (The same first account rule applies in the
console app: choose 1 to Register first.)

If a starter says the compiler is missing, install MinGW-w64 GCC on
Windows (https://www.msys2.org/ — install, then in the MSYS2 terminal
run `pacman -S mingw-w64-x86_64-gcc`, and add
`C:\msys64\mingw64\bin` to PATH) or `g++` on Linux
(`sudo apt install g++`), then run the starter again.

## 1. Console app (all three members' features, menus 0–43)

Linux/macOS:

```
g++ -std=c++17 -Wall -Wextra -o project *.cpp
./project
```

Windows 11 (MinGW-w64, from MSYS2 or the MinGW installer):

```
g++ -std=c++17 -Wall -Wextra -o project.exe *.cpp
project.exe
```

Or with MSVC (Developer Command Prompt):

```
cl /std:c++17 /EHsc *.cpp /Fe:project.exe
```

The first registered user becomes ADMIN. Data files (users.txt,
decisions.txt, transactions.txt, savings_goals.txt, habit_log.txt,
tasks.txt, daily_report.txt, financial_report.txt/.csv, error_log.txt)
are created in the directory you run the app from.

## 2. Website dashboard (recommended way to use it)

Linux/macOS:

```
./start-dashboard.sh
```

Windows 11:

```
start-dashboard.bat
```

Then open **http://127.0.0.1:8000/** in your browser. Log in with the same
account you registered in the console app (or register a new one in the
dashboard — it writes the same users.txt). The dashboard's first page is a
landing page; after login you get the Overview and all 23 sections.

Manual equivalent (if the scripts do not suit you):

```
g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server dashboard/cpp_server.cpp   # Linux
x86_64-w64-mingw32-g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server.exe dashboard/cpp_server.cpp -lws2_32   # cross-compile for Windows
./cpp_server --port 8000 --data-dir .    # run from the repository root
```

Python fallback only (same API, same files):

```
python3 dashboard/server.py --port 8000 --data-dir .
```

## 3. Data persistence and backup

- Every change is written to a plain-text file immediately; closing the
  browser or stopping the server does not lose data.
- Back up by copying the `*.txt` / `*.csv` files, or use Overview →
  "Backup decisions" (writes decisions_backup.txt) and "Restore".
- The console app and the dashboard read the same files, so you can
  switch between them freely. The one exception is tasks: the console
  tasks.txt is shared: the console app (Task Prioritization appends,
  Task Status and Deadline Alert load) and the dashboard use the same
  format `id|title|urgency|importance|deadline|status`.

## 4. Security — read this before sharing anything

- **Localhost only.** The C++ server binds to 127.0.0.1 and must not be
  exposed to the internet, port-forwarded, or put behind a public tunnel.
- **Passwords are hashed** in users.txt (PBKDF2-HMAC-SHA256, see
  SECURITY.md). Old plaintext accounts are upgraded to a hash on
  their next successful login. Do not deploy publicly: the servers
  have no HTTPS of their own (see section 5).
- The dashboard never returns passwords: Admin/Profile list username +
  role only, sessions are random in-memory tokens, and static serving is
  limited to index.html, style.css and app.js (e.g. /users.txt → 404).
- Non-ADMIN users get 403 from /api/admin and /api/users.

## 5. Future public deployment (NOT done, and NOT safe yet)

Do not deploy publicly until all of these are done, in this order:

1. Password hashing and session expiry and login rate limiting are
   DONE in this branch (see SECURITY.md).
2. Add HTTPS (TLS) via a reverse proxy (e.g. Caddy/nginx) — the
   servers themselves have no TLS.
3. Only then bind to 0.0.0.0 behind that proxy, with the proxy
   terminating TLS and the servers still validating every token.

## 6. Troubleshooting

- "Port already in use": another server is running — stop it, or use
  `--port 8001`.
- "Cannot open data file": run the server from the repository root, or
  pass `--data-dir <path>`.
- Windows: if your data directory path contains non-ASCII characters,
  use a plain ASCII path (the Windows file-lock code uses ANSI paths).
- If the dashboard page loads but login fails, check that the server
  log shows the same data directory as your console app.
