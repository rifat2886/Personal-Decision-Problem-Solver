# Personal Decision & Problem Solver — explicit build, no "*.cpp blindly".
#
# The production console app is built from exactly the 35 source files
# listed below. Test files with their own main() (for example Sweety's
# logic_priority_test.cpp, which lives on the logic-priority branch
# and is NOT in this tree) must never be added to this list, or the
# build would fail with duplicate main() definitions. The CI workflow
# builds that test standalone in a temporary directory instead.
#
#   make              -> build console app (project) and C++ server (cpp_server)
#   make project      -> console app only
#   make cpp_server   -> C++ dashboard server only
#   make clean        -> remove built binaries
#
# Windows: use start-dashboard.bat / start-console.bat instead of make,
# or use mingw32-make with the same targets.

CXX ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra

SOURCES = admin.cpp \
          backup_restore.cpp \
          budget.cpp \
          compare_options.cpp \
          control.cpp \
          daily_decision.cpp \
          deadline_alert.cpp \
          decision_explanation.cpp \
          delete_confirmation.cpp \
          error_handler.cpp \
          export_report.cpp \
          filter_sort.cpp \
          habit.cpp \
          habit_streak.cpp \
          history.cpp \
          income_expense.cpp \
          input_validation.cpp \
          login.cpp \
          logout.cpp \
          main.cpp \
          multi_task_decision.cpp \
          password_change.cpp \
          password_validation.cpp \
          period_report.cpp \
          priority_calculator.cpp \
          problem.cpp \
          profile.cpp \
          registration.cpp \
          report.cpp \
          savings_goal.cpp \
          search_history.cpp \
          study_planner.cpp \
          task_prioritization.cpp \
          task_status.cpp \
          time_allocation.cpp

all: project cpp_server

project: $(SOURCES) *.h
	$(CXX) $(CXXFLAGS) -o project $(SOURCES)

cpp_server: dashboard/cpp_server.cpp password_hash.h
	$(CXX) $(CXXFLAGS) -pthread -o cpp_server dashboard/cpp_server.cpp

clean:
	rm -f project project.exe cpp_server cpp_server.exe

.PHONY: all clean
