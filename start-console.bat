@echo off
REM Personal Decision & Problem Solver — console app launcher (Windows 11)
REM Double-click this file. It builds the console app if needed, then runs it.
REM No C++ knowledge is needed. If the compiler is missing, it tells you so.
cd /d "%~dp0"
REM Phase 4, Batch B: detect PostgreSQL dev files for the optional
REM Postgres build (see the g++ line below). Set before the build
REM block so %PG_CFLAGS% / %PG_LIBS% expand to these values.
set PG_CFLAGS=
set PG_LIBS=
where pg_config >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%I in ('pg_config --includedir') do set PG_CFLAGS=-I%%I
  set PG_LIBS=-lpq
)
if not exist project.exe (
  echo Building the console app for the first time, please wait...
  where g++ >nul 2>nul
  if errorlevel 1 (
    echo ERROR: g++ MinGW-w64 was not found.
    echo Install MinGW-w64 GCC, add it to PATH, then double-click this file again.
    echo See RUN.md for the download link and steps.
    pause
    exit /b 1
  )
  REM Phase 4, Batch B: link libpq only when pg_config exists (the
  REM case when PostgreSQL dev files are installed), so the console
  REM can use the shared PostgreSQL database when DATABASE_URL is
  REM set. The flags are set BEFORE this block, so %VAR% expands to
  REM the values set above. Without pg_config the console builds
  REM txt-only, as before.
  g++ -std=c++17 -Wall -Wextra %PG_CFLAGS% -o project.exe admin.cpp backup_restore.cpp budget.cpp compare_options.cpp control.cpp daily_decision.cpp deadline_alert.cpp decision_explanation.cpp delete_confirmation.cpp error_handler.cpp export_report.cpp filter_sort.cpp habit.cpp habit_streak.cpp history.cpp income_expense.cpp input_validation.cpp login.cpp logout.cpp main.cpp multi_task_decision.cpp password_change.cpp password_validation.cpp period_report.cpp priority_calculator.cpp problem.cpp profile.cpp registration.cpp report.cpp savings_goal.cpp search_history.cpp study_planner.cpp task_prioritization.cpp task_status.cpp time_allocation.cpp %PG_LIBS%
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
