# Testing

## Automated tests (run from the repository root)

```sh
# Build first (Linux/macOS):
make
# or, without make:
g++ -std=c++17 -Wall -Wextra -o project admin.cpp backup_restore.cpp budget.cpp compare_options.cpp control.cpp daily_decision.cpp deadline_alert.cpp decision_explanation.cpp delete_confirmation.cpp error_handler.cpp export_report.cpp filter_sort.cpp habit.cpp habit_streak.cpp history.cpp income_expense.cpp input_validation.cpp login.cpp logout.cpp main.cpp multi_task_decision.cpp password_change.cpp password_validation.cpp period_report.cpp priority_calculator.cpp problem.cpp profile.cpp registration.cpp report.cpp savings_goal.cpp search_history.cpp study_planner.cpp task_prioritization.cpp task_status.cpp time_allocation.cpp
g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server dashboard/cpp_server.cpp

# Console regression (14 checks, fresh temp data dir):
python3 tests/console_test.py --binary ./project

# API regression, C++ server (36 checks, fresh temp data dir):
python3 tests/api_test.py --server-cmd "./cpp_server" --port 8123

# API regression, Python fallback server (same 36 checks):
python3 tests/api_test.py --server-cmd "python3 dashboard/server.py" --port 8124

# Browser test (33 checks + 6 screenshots, needs Playwright + Chromium):
pip install playwright
python3 -m playwright install chromium
python3 tests/browser_test.py --server ./cpp_server --port 8130 --out screenshots
```

All test scripts create their own temporary data directories, use
only test accounts (never real credentials), and delete the data
afterwards. A non-zero exit code means at least one check failed;
the output lists every PASS and FAIL by name.

## What the tests cover

- Registration, login, logout, profile, admin permissions (403 for
  non-admin), password change, and old-plaintext password migration.
- Login rate limiting (5 failures, then 429).
- Daily decision, priority (50/50), tasks (create, PATCH to
  In Progress, deadline UPCOMING), compare, multi-task, decision
  explanation (45/50), budget (3800), transactions, savings,
  concurrent savings adds (10 x 100 = 1000, no lost update),
  habits, streak calculation, study planner (6h), time allocation,
  monthly report, search, backup, CSV export, overview, info.
- Console task persistence: a task created by Task Prioritization
  in one console session is visible to Task Status and Deadline
  Alert in a new session (tasks.txt, dashboard format).
- Dashboard: all 23 sections load, task and budget forms submit,
  dark mode toggles, mobile viewport has no horizontal overflow,
  unauthenticated API access is 401, no JavaScript errors, no
  failed API requests.
- Build warnings: `-Wall -Wextra -Wpedantic` with 0 warnings for
  both the console app and the C++ server.
- Sanitizers (manual, not in CI): the console app was also built
  with `-fsanitize=address,undefined` and run through register,
  login, task prioritisation, task status, deadline alert and
  balance with no sanitizer report.

## Continuous integration

`.github/workflows/ci.yml` runs the same console and API tests on
real Linux (ubuntu-latest) and real Windows (windows-latest, MinGW)
runners, plus a server startup/shutdown check and a standalone
build of Sweety's logic_priority test from its own branch (it has
its own main(), so it is never built into the production app).

## What is NOT tested here

- Runtime on a physical Windows 11 machine by hand: the Windows CI
  job is the real Windows runtime test (a hosted Windows runner).
  If CI is unavailable, that job is NOT TESTED, not passed.
- Public deployment, HTTPS termination, and proxy-level rate
  limiting: see SECURITY.md. They are not part of this test suite.
- Browser screenshots are taken from the real running dashboard
  in the browser test; earlier layout-preview diagrams in the
  workspace are labelled diagrams, not screenshots, and must not be
  presented as screenshots.
