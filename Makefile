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

project: $(SOURCES) *.h dashboard/pg_store.h console_pg.h
	$(CXX) $(CXXFLAGS) $(PG_CFLAGS) -o project $(SOURCES) $(PG_LIBS)

# Postgres mode (Route 2, Phase 1) for the console too (Phase 4,
# Batch B): PG_LIBS/PG_CFLAGS above are shared with the console
# target, so `make project` links -lpq and finds libpq-fe.h only
# when libpq-dev is installed. Without pg_config, the console
# compiles Postgres support out (see console_pg.h) and still builds
# and runs in txt mode.

# Postgres mode (Route 2, Phase 1): link libpq only when pg_config
# exists, which is the case when libpq-dev is installed. (Do NOT
# use `pg_config --libs` here: it lists static-link libraries such
# as -lpgcommon that are not installed as linkable libraries.)
# Without pg_config, cpp_server.cpp compiles Postgres support out
# (see pg_store.h) and the server still builds and runs in txt
# mode — this keeps the Windows/MinGW build working without a new
# dependency.
PG_LIBS := $(shell if pg_config --includedir >/dev/null 2>&1; then echo "-lpq"; fi)
# libpq-fe.h lives in /usr/include/postgresql on Debian, which is
# NOT a default compiler search path — without this -I flag,
# __has_include(<libpq-fe.h>) is false and Postgres support is
# silently compiled out (caught by local Postgres testing).
PG_CFLAGS := $(shell pg_config --includedir 2>/dev/null | sed 's/^/-I/' | grep -v '^-I$$')

# Gemini (Phase 1): link libcurl only when curl-config exists, which
# is the case when libcurl dev headers are installed. Without
# curl-config, gemini_client.cpp compiles the stub (available()
# returns false, /api/ai/health reports available=false) and the
# server still builds and runs — this keeps the Windows/MinGW build
# working without a new dependency. Same opt-in pattern as libpq
# above. `make project` is unaffected (the console app never links
# curl).
CURL_CFLAGS := $(shell if curl-config --cflags >/dev/null 2>&1; then curl-config --cflags; fi)
CURL_LIBS := $(shell if curl-config --libs >/dev/null 2>&1; then curl-config --libs; fi)

cpp_server: dashboard/cpp_server.cpp dashboard/gemini_client.cpp dashboard/gemini_client.h dashboard/pg_store.h password_hash.h
	$(CXX) $(CXXFLAGS) $(PG_CFLAGS) $(CURL_CFLAGS) -pthread -o cpp_server dashboard/cpp_server.cpp dashboard/gemini_client.cpp $(PG_LIBS) $(CURL_LIBS)

clean:
	rm -f project project.exe cpp_server cpp_server.exe

.PHONY: all clean
