#!/bin/sh
# Personal Decision & Problem Solver — console app launcher (Linux/macOS)
# Run: ./start-console.sh
# It builds the console app if needed, then runs it.
cd "$(dirname "$0")" || exit 1
if [ ! -x ./project ]; then
  echo "Building the console app for the first time, please wait..."
  if ! command -v g++ >/dev/null 2>&1; then
    echo "ERROR: g++ was not found. Install a C++ compiler (for example: sudo apt install g++), then run this script again. See RUN.md."
    exit 1
  fi
  g++ -std=c++17 -Wall -Wextra -o project admin.cpp backup_restore.cpp budget.cpp compare_options.cpp control.cpp daily_decision.cpp deadline_alert.cpp decision_explanation.cpp delete_confirmation.cpp error_handler.cpp export_report.cpp filter_sort.cpp habit.cpp habit_streak.cpp history.cpp income_expense.cpp input_validation.cpp login.cpp logout.cpp main.cpp multi_task_decision.cpp password_change.cpp password_validation.cpp period_report.cpp priority_calculator.cpp problem.cpp profile.cpp registration.cpp report.cpp savings_goal.cpp search_history.cpp study_planner.cpp task_prioritization.cpp task_status.cpp time_allocation.cpp || {
    echo "ERROR: the build failed. See the messages above, or RUN.md troubleshooting."
    exit 1
  }
  echo "Build finished."
fi
echo "Starting the console app..."
echo "First time? Choose 1 to Register. The first account you create becomes ADMIN."
./project
