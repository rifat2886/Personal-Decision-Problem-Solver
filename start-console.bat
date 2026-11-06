@echo off
REM Personal Decision & Problem Solver — console app launcher (Windows 11)
REM Double-click this file. It builds the console app if needed, then runs it.
REM No C++ knowledge is needed. If the compiler is missing, it tells you so.
cd /d "%~dp0"
if not exist project.exe (
  echo Building the console app for the first time, please wait...
  where g++ >nul 2>nul
  if errorlevel 1 (
    echo ERROR: g++ (MinGW-w64) was not found.
    echo Install MinGW-w64 GCC, add it to PATH, then double-click this file again.
    echo See RUN.md for the download link and steps.
    pause
    exit /b 1
  )
  g++ -std=c++17 -Wall -Wextra -o project.exe admin.cpp backup_restore.cpp budget.cpp compare_options.cpp control.cpp daily_decision.cpp deadline_alert.cpp decision_explanation.cpp delete_confirmation.cpp error_handler.cpp export_report.cpp filter_sort.cpp habit.cpp habit_streak.cpp history.cpp income_expense.cpp input_validation.cpp login.cpp logout.cpp main.cpp multi_task_decision.cpp password_change.cpp password_validation.cpp period_report.cpp priority_calculator.cpp problem.cpp profile.cpp registration.cpp report.cpp savings_goal.cpp search_history.cpp study_planner.cpp task_prioritization.cpp task_status.cpp time_allocation.cpp
  if errorlevel 1 (
    echo ERROR: the build failed. See the messages above, or RUN.md troubleshooting.
    pause
    exit /b 1
  )
  echo Build finished.
)
echo Starting the console app...
echo First time? Choose 1 to Register. The first account you create becomes ADMIN.
project.exe
pause
