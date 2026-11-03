# File-to-contributor-to-feature mapping (audited 2026-11-03)

Source of truth: `git log origin/main` authors and branch ancestry,
re-checked for this master task. Main HEAD is f21865c; PR #64 branch
HEAD before this round was b74f373; 55 remote branches, none deleted.

## Contributors (main branch commits)

- Rifat (rifat2886 / "Rifat"): 97 commits — System Core &
  Authentication, Registration, Login/Logout, Profile, Admin,
  Password Validation & Change, Time Allocation, Study Planner,
  Dashboard & C++ Backend.
- Umma Habiba Nuriya (nuriya2772): 21 commits — Daily Decision,
  Priority Calculator, Task Prioritization, Compare Options,
  Task Status, Deadline Alert, Decision Explanation, Multi-Task
  (via the restored algorithm, see below), Search & History,
  Error Handling, Backup & Restore, Control Panel.
- Sweety Akter (sweety2803): 21 commits — Budget Management,
  Income & Expense, Savings Goals, Habit Tracker, Habit Streak,
  Weekly/Monthly Reports, TXT/CSV Export, Problem Solver,
  Daily Summary, Habit Decision, Savings Goal Calculator.
- copilot-swe-agent[bot]: 1 commit (2 include lines removed) —
  not a team member, not counted as a contribution.

## Branch status

- Every teammate branch (Nuriya 21 patch branches, Sweety patch
  branches, budget/habit/report branches) is an ancestor of main,
  except the PR #64 branch itself and `rifat2886-patch-9`, whose
  sole change deletes admin.cpp and which is deliberately NOT
  merged.
- The only teammate files ever on a branch but not on main are
  Sweety's `logic_priority.cpp`, `logic_priority.h` and
  `logic_priority_test.cpp` (merged in PR #13, 2026-10-25, deleted
  2026-10-30). Its priority/compare/task formulas are superseded
  by Nuriya's modules (different formulas, kept); its multi-task
  energy/time-budget daily decision was restored in PR #63 as
  `multi_task_decision.h/.cpp` (menu 43) with a distinct
  `MultiTaskItem` struct. Its test file has its own `main()`, so
  it is NOT built into the production app; CI builds it standalone
  in a temporary directory from its own branch (see
  `.github/workflows/ci.yml`). No duplicate integration of the
  same code from multiple branches was done.

## Mapping: file -> contributor -> feature -> where it is verified

| File | Contributor | Feature | Console | Dashboard/API |
|---|---|---|---|---|
| registration.cpp, login.cpp, logout.cpp, profile.cpp, admin.cpp, password_validation.cpp, password_change.cpp | Rifat | Registration, Login/Logout, Profile, Admin, Password Validation & Change | menus 1-5 | /api/register, /api/login, /api/logout, /api/me, /api/users, /api/admin, /api/change-password |
| main.cpp, control.cpp, input_validation.cpp, history.cpp, decision_store.h, file_lock.h, password_hash.h, task_store.h | Rifat (shared infra) | System Core, Input Validation, History, Decision Store, File Locking, Password Hashing, Task Store | all menus | all endpoints |
| time_allocation.cpp | Rifat | Time Allocation | menu 32 | /api/time-allocation |
| study_planner.cpp | Rifat | Study Planner | menu 31 | /api/study-planner |
| daily_decision.cpp | Nuriya | Daily Decision Maker | menu 9 | /api/daily-decision |
| priority_calculator.cpp | Nuriya | Priority Calculator | menu 10 | /api/priority |
| task_prioritization.cpp, task_data.h | Nuriya | Task Prioritization | menu 11 | /api/tasks (create) |
| task_status.cpp | Nuriya | Task Status | menu 13 | /api/tasks (PATCH), Task Status section |
| deadline_alert.cpp | Nuriya | Deadline Alerts | menu 14 | /api/deadlines |
| decision_explanation.cpp | Nuriya | Decision Explanation | menu 15 | /api/decision-explanation |
| compare_options.cpp | Nuriya | Compare Options | menu 12 | /api/compare-options |
| multi_task_decision.cpp (restored Sweety algorithm, Nuriya's assigned area in the task list) | Sweety algorithm, restored in PR #63 | Multi-Task Decision | menu 43 | /api/multi-task |
| search_history.cpp, filter_sort.cpp | Sweety (search), Nuriya (filter/sort) | Search & History | menus 16-17, 28 | /api/decisions?search=, Search & History section |
| backup_restore.cpp, error_handler.cpp | Nuriya | Backup & Restore, Error Handling | menus 27, 42 | /api/backup, /api/restore, /api/error-log |
| budget.cpp | Sweety | Budget Management | menu 37 | /api/budget |
| income_expense.cpp | Sweety | Income & Expense Tracking | menus 18-19 | /api/transactions |
| savings_goal.cpp | Sweety | Savings Goals, Savings Goal Calculator | menus 20, 40 | /api/savings, /api/savings/add, /api/savings-calculator |
| habit.cpp, habit_streak.cpp | Sweety | Habit Tracker, Habit Streak, Habit Decision | menus 21-22, 39, 41 | /api/habits, /api/habit-decision, /api/habit-streak-calc |
| period_report.cpp, report.cpp | Sweety | Weekly/Monthly Reports, Daily Summary | menus 23-26, 36 | /api/reports, /api/daily-summary |
| export_report.cpp | Sweety | TXT/CSV Export | menus 35, 38 | /api/export |
| problem.cpp | Sweety | Problem Solver | menu 30 | /api/problem-solver |
| delete_confirmation.cpp | Nuriya | Delete Confirmation | menu 33 | (console only; dashboard has no delete endpoint by design) |

## Data files (all shared, same formats, console + both servers)

users.txt (`username credential ROLE`, credential now a PBKDF2 hash
for new/migrated accounts, plaintext only until an old account's
next login), decisions.txt, tasks.txt, transactions.txt,
savings_goals.txt, habit_log.txt, daily_report.txt,
financial_report.txt/.csv, error_log.txt, decisions_backup.txt.
