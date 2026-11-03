# Personal Decision & Problem Solver

A C++ based application designed to help users make better daily decisions, manage tasks, organize time, track expenses, and build productive habits.

## Project Overview

**Personal Decision & Problem Solver** is a team-based Object-Oriented Programming (OOP) project. It provides several tools for personal planning and decision-making through a menu-driven console application.

The main goal is to make everyday activities easier by combining decision-making, task management, budgeting, and habit tracking in one system.

## Team Members

| Member | Responsibility |
|---|---|
| Rifat | System Core & Authentication |
| Umma Habiba Nuriya | Logic & Decision Engine |
| Sweety Akter | Planner & Habit Tracker |

## Quick start (beginner-friendly)

- **Dashboard (website):** Windows: double-click `start-dashboard.bat`.
  Linux/macOS: `./start-dashboard.sh`. Then open http://127.0.0.1:8000/
- **Console app:** Windows: double-click `start-console.bat`.
  Linux/macOS: `./start-console.sh`.
- First time? Register — the first account becomes ADMIN.
- Full instructions: `RUN.md`. Tests: `TESTING.md`. Security: `SECURITY.md`.
- File-to-contributor-to-feature audit: `AUDIT.md`.

## Main Features

### 1. Authentication & Core System
- User Registration
- User Login
- User Profile
- Password Change
- Admin Panel
- Time Allocation
- Study Planner
- Logout

### 2. Decision & Task Management
- Daily Decision Maker
- Priority Calculator
- Task Prioritization
- Compare Options
- Task Status Manager
- Deadline Alert
- Decision Explanation
- Multi-Task Decision
- Web Dashboard (23 sections, C++ backend, see dashboard/README.md)


### 3. Budget, Savings & Habits
- Add Income and Expenses
- View Transactions
- Check Balance
- Add Savings Goals
- Add Savings Amount
- View Savings Goals
- Habit Completion Tracking
- Weekly Report
- Monthly Report
- Export TXT Report
- Export CSV Report

### 4. History & File Management
- Search Decision History
- Filter Decisions
- Sort Decisions by Priority
- Backup Decisions
- Restore Decisions
- Error Log
- Delete Confirmation

### 5. Additional Integrated Modules
- Problem Solver (35)
- Daily Summary Report (36)
- Budget Decision calculator (37)
- Income & Expense Tracking summary (38)
- Savings Goal Calculator (39)
- Habit Decision (40)
- Habit Streak calculator (41)
- Control Panel for history management (42)
- Multi-Task Daily Decision, energy/time budget (43)

## Technologies Used

- **Programming Language:** C++
- **Concepts:** Object-Oriented Programming (OOP)
- **Compiler:** GCC / G++
- **Development Environment:** Visual Studio Code
- **Version Control:** Git & GitHub
- **Data Storage:** Local File Handling

## Project Structure

The project is organized into separate header (`.h`) and source (`.cpp`) files.

```text
Personal-Decision-Problem-Solver/
│
├── main.cpp
├── README.md
│
├── Authentication/
│   ├── registration.h / registration.cpp
│   ├── login.h / login.cpp
│   ├── password_validation.h / password_validation.cpp
│   ├── profile.h / profile.cpp
│   ├── password_change.h / password_change.cpp
│   ├── admin.h / admin.cpp
│   ├── input_validation.h / input_validation.cpp
│   ├── logout.h / logout.cpp
│
├── Planning/
│   ├── time_allocation.h / time_allocation.cpp
│   ├── study_planner.h / study_planner.cpp
│
├── Decision_Management/
│   ├── daily_decision.h / daily_decision.cpp
│   ├── priority_calculator.h / priority_calculator.cpp
│   ├── task_prioritization.h / task_prioritization.cpp
│   ├── task_data.h
│   ├── compare_options.h / compare_options.cpp
│   ├── task_status.h / task_status.cpp
│   ├── deadline_alert.h / deadline_alert.cpp
│   ├── decision_explanation.h / decision_explanation.cpp
│   ├── multi_task_decision.h / multi_task_decision.cpp
│   └── decision_store.h
│
├── Budget_and_Habits/
│   ├── income_expense.h / income_expense.cpp
│   ├── savings_goal.h / savings_goal.cpp
│   ├── habit.h / habit.cpp
│   ├── habit_streak.h / habit_streak.cpp
│   ├── period_report.h / period_report.cpp
│   ├── export_report.h / export_report.cpp
│   ├── budget.h / budget.cpp
│   ├── report.h / report.cpp
│   └── problem.h / problem.cpp
│
└── History_and_Control/
    ├── history.h / history.cpp
    ├── search_history.h / search_history.cpp
    ├── filter_sort.h / filter_sort.cpp
    ├── backup_restore.h / backup_restore.cpp
    ├── error_handler.h / error_handler.cpp
    ├── delete_confirmation.h / delete_confirmation.cpp
    └── control.h / control.cpp
```

*Note: The structure above shows the logical module grouping. All
`.cpp` and `.h` files actually live in the repository root directory,
not in subfolders. The one real subfolder is `dashboard/` (see below),
which holds the website dashboard; it does not change the C++ build,
because `g++ *.cpp` in the root does not pick up `dashboard/` files.*

### Website dashboard

See `dashboard/README.md`. The dashboard is served by a C++ API server
(`dashboard/cpp_server.cpp`, built separately from the console app),
with a Python server (`dashboard/server.py`) kept as a fallback. Both
use the same API and the same data files as the C++ console app, and
both bind to localhost only. The C++ server and the console app are
cross-platform C++17: on Windows 11 they build natively with MinGW-w64
or MSVC (Winsock and LockFileEx instead of POSIX sockets and flock);
WSL is not required. See `dashboard/README.md` for the Windows build
commands and the honest build-vs-runtime status.

## How to Run the Project

### Requirements
- Windows, Linux, or macOS
- GCC/G++ compiler
- Visual Studio Code (recommended)

### Step 1: Clone the Repository

```bash
git clone https://github.com/rifat2886/Personal-Decision-Problem-Solver.git
```

### Step 2: Open the Project Folder

```bash
cd Personal-Decision-Problem-Solver
```

### Step 3: Compile the Project

This project requires C++17. Compile every `.cpp` file together
(the headers are included by the sources; there is no separate
build system):

```bash
g++ -std=c++17 -Wall -Wextra -o project *.cpp
```

All modules are reachable from the main menu, including the
previously unlisted ones: Problem Solver (35), Daily Summary
Report (36), Budget Decision (37), Income & Expense Tracking
summary (38), Savings Goal Calculator (39), Habit Decision (40),
Habit Streak calculator (41), and Control Panel for history
management (42).

Multi-Task Daily Decision (43) restores
the multi-task energy/time-budget capability from Sweety's old
`logic_priority` daily decision: tasks are sorted by deadline
urgency, then accepted in that order only while their energy and
time both fit the remaining budgets. Only that capability was
restored; the old class's priority, compare, and task methods were
not, because Nuriya's Priority Calculator, Compare Options, and
Task Prioritization already cover those features.

Decision records are shared through `decision_store.h` in the
format `id|date|type|priority|title` in `decisions.txt`, so
Daily Decision Maker, Problem Solver, Task Prioritization, and
Multi-Task Daily Decision records can be found by Search (28),
Filter (29), Sort (30), Backup (31), Restore (32), and Delete (34).

### Step 4: Run the Application

On Windows:

```bash
project.exe
```

On Linux/macOS, use the executable name generated by your compiler.

## Version Control & Collaboration

GitHub is used to manage the project and collaborate among team members.

Each team member works on assigned modules and pushes changes to GitHub. The main branch is used to maintain the integrated project.

Repository:  
https://github.com/rifat2886/Personal-Decision-Problem-Solver

## Project Goals

- Improve daily decision-making.
- Organize tasks according to priority.
- Manage time effectively.
- Track income, expenses, and savings.
- Build productive habits.
- Maintain decision history and reports.
- Practice teamwork and collaborative software development.

## Data Files Created at Runtime

| File | Contents |
|---|---|
| `users.txt` | Username, password, and role, space-separated. The first registered user becomes `ADMIN`. |
| `decisions.txt` | Shared decision records (`id\|date\|type\|priority\|title`). |
| `decisions_backup.txt` | Backup of `decisions.txt`. |
| `transactions.txt` | Income/expense records (`date\|type\|category\|amount\|note`). |
| `savings_goals.txt` | Savings goals (`name\|target\|saved`). |
| `habit_log.txt` | Habit completions (`habit\|date`). |
| `search_history.txt`, `error_log.txt`, `system_log.txt` | Search history, error log, and history-action log. |
| `financial_report.txt`, `financial_report.csv`, `daily_report.txt` | Exported reports. |

Task prioritization data (`taskList` in `task_data.h`) is kept
in memory only for the current run: run Task Prioritization (11)
before Task Status (13) or Deadline Alert (14) in the same session.

> Security note: this is a coursework console app. Passwords are
> stored in plain text in `users.txt` and usernames/passwords
> cannot contain spaces (they are space-separated in that file).
> Do not reuse a real password here.

## Future Improvements

- Web-based dashboard using HTML, CSS, and JavaScript.
- C++ backend integration.
- Database integration.
- Improved user interface and user experience.
- Enhanced authentication and data security.

## Academic Project

**Project Name:** Personal Decision & Problem Solver  
**Course:** Object-Oriented Programming (C++)  
**Project Type:** Team Project

---

**Developed by the Personal Decision & Problem Solver Team**
