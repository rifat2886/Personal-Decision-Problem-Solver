# File-to-contributor-to-feature mapping (audited 2026-11-03)

Source of truth: `git log origin/main` authors and branch ancestry,
re-checked for this master task. Main HEAD is f21865c; PR #64 branch
HEAD after the 2026-11-03 plain-text restore is 6cd41e9 (the
earlier 63fb546 push stored all 30 files as base64 blobs, which
made the branch unbuildable; that error was found by a fresh clone
audit and fixed file-by-file in plain text, with no file deleted);
55 remote branches, none deleted.

## 2026-11-03 follow-up round (after f38fc78)
- Verified f38fc78 from a fresh clone: all files plain text
  (no base64 blobs), `make` builds clean, 0 warnings.
- Topbar fix: dashboard/style.css — at 375px the title was cut
  off; now the brand container shrinks and the title wraps to
  two lines under 420px. Verified at 375px, 768px, 1280px: no
  horizontal overflow, full title visible at 375px.
- TESTING.md corrected: console test needs an absolute binary
  path, and the CI section now states plainly that
  `.github/workflows/ci.yml` is not on the branch and CI has
  NOT run (Workflows permission, see SECURITY.md / PR comment).
- No teammate branch, commit, file or contribution was deleted;
  no public deployment was done.

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
| time_allocation.cpp | Rifat | Time Allocation | menu 6 | /api/time-allocation |
| study_planner.cpp | Rifat | Study Planner | menu 7 | /api/study-planner |
| daily_decision.cpp | Nuriya | Daily Decision Maker | menu 9 | /api/daily-decision |
| priority_calculator.cpp | Nuriya | Priority Calculator | menu 10 | /api/priority |
| task_prioritization.cpp, task_data.h | Nuriya | Task Prioritization | menu 11 | /api/tasks (create) |
| task_status.cpp | Nuriya | Task Status | menu 13 | /api/tasks (PATCH), Task Status section |
| deadline_alert.cpp | Nuriya | Deadline Alerts | menu 14 | /api/deadlines |
| decision_explanation.cpp | Nuriya | Decision Explanation | menu 15 | /api/decision-explanation |
| compare_options.cpp | Nuriya | Compare Options | menu 12 | /api/compare-options |
| multi_task_decision.cpp (restored Sweety algorithm, Nuriya's assigned area in the task list) | Sweety algorithm, restored in PR #63 | Multi-Task Decision | menu 43 | /api/multi-task |
| search_history.cpp, filter_sort.cpp | Sweety (search), Nuriya (filter/sort) | Search & History | menus 28-30 | /api/decisions?search=, Search & History section |
| backup_restore.cpp, error_handler.cpp | Nuriya | Backup & Restore, Error Handling | menus 31-33 | /api/backup, /api/restore, /api/error-log |
| budget.cpp | Sweety | Budget Management | menu 37 | /api/budget |
| income_expense.cpp | Sweety | Income & Expense Tracking | menus 16-18, 38 | /api/transactions |
| savings_goal.cpp | Sweety | Savings Goals, Savings Goal Calculator | menus 19-21, 39 | /api/savings, /api/savings/add, /api/savings-calculator |
| habit.cpp, habit_streak.cpp | Sweety | Habit Tracker, Habit Streak, Habit Decision | menus 22-23, 40-41 | /api/habits, /api/habit-decision, /api/habit-streak-calc |
| period_report.cpp, report.cpp | Sweety | Weekly/Monthly Reports, Daily Summary | menus 24-25, 36 | /api/reports, /api/daily-summary |
| export_report.cpp | Sweety | TXT/CSV Export | menus 26-27 | /api/export |
| problem.cpp | Sweety | Problem Solver | menu 35 | /api/problem-solver |
| delete_confirmation.cpp | Nuriya | Delete Confirmation | menu 34 | (console only; dashboard has no delete endpoint by design) |

## Data files (all shared, same formats, console + both servers)

users.txt (`username credential ROLE`, credential now a PBKDF2 hash
for new/migrated accounts, plaintext only until an old account's
next login), decisions.txt, tasks.txt, transactions.txt,
savings_goals.txt, habit_log.txt, daily_report.txt,
financial_report.txt/.csv, error_log.txt, decisions_backup.txt.

## Main-branch stray workflow file — 2026-11-03 (documented, NOT deleted, NOT merged)

Main moved from f21865c to 418420baf8f2ad6024a2602775c998a931c239a7
(commit "Add CI workflow configuration", 2026-11-03 11:21 +06, author
Rifat, NOT pushed by Muse). That commit adds exactly one file, with a
literally broken name: `workflows/workflow.yml‐.` — the directory is
`workflows/`, not `.github/workflows/`, and the filename ends with a
hyphen-like character and a dot. Its content is only 13 lines: a single
checkout step, no build or test step, and a reference to a
`secrets.workflow_token` secret. Consequences, verified 2026-11-03:

- GitHub Actions does NOT discover this file, so it does NOT run any
  CI. It must not be described as a working workflow.
- It is on main only, not on the PR #64 branch. The PR branch head is
  still 44571fbee9fa93c93ceb036a96493af0aeb06bc2.
- No file was deleted or overwritten to document this. Whether the
  stray file is later removed, renamed, or replaced is a separate
  decision for the repository owner, with explicit permission.
- The correct workflow is the prepared `.github/workflows/ci.yml`
  (Linux ubuntu-latest + Windows windows-latest jobs, no secrets,
  build list exactly matching the 35 root .cpp files, tests
  console_test.py / api_test.py). It is held ready locally and is
  NOT pushed while the Workflows permission is ineffective.

## Workflows permission — still BLOCKED (not assumed effective)

The Muse GitHub App installation still lacks Workflows: Read and
write. The last push attempt for `.github/workflows/ci.yml` returned
403 "Resource not accessible by integration", while a non-workflow
write in the same session succeeded, proving the failure is
workflow-specific. Per GitHub's App model, the App developer must first
add Workflows to the App registration, and the installation owner must
then approve the new permission; until both happen, the old permission
set continues. No bypass is used, and permission is not assumed
effective from a repository-access change alone.

## Compatibility of new main 418420b with PR #64 (checked, NOT merged)

Merge-base of main and backend-testing-dashboard is f21865c. Since
that base, main changed only the one stray file above; the PR branch
changed 36 files and added the dashboard, tests, docs and launchers.
No path was changed on both sides, so a simulated merge
(`git merge-tree`, no commit, no branch change) produced tree
6ebf52ea0ca40e3f4765d8a486cdb294b2b47b9d with NO conflicts: 95
files = the PR branch's 94 files plus main's 1 stray file. A future
merge would therefore keep the stray file unless the owner separately
decides to remove it. PR #64 stays open; no merge, delete, or public
deployment was done in this round.
