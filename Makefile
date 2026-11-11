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
	@if [ -z "$(PG_LIBS)" ]; then echo "WARNING: pg_config not found - building WITHOUT Postgres support (txt mode only). Install mingw-w64-ucrt-x86_64-postgresql in the MSYS2 UCRT64 terminal (or libpq-dev on Debian/Ubuntu), delete project.exe, and rebuild for Neon database support."; fi
	$(CXX) $(CXXFLAGS) $(PG_CFLAGS) $(PG_STUB) -o project $(SOURCES) $(PG_LIBS)

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
# If pg_config is missing, the libpq headers may still be in the
# compiler's default include path (MSYS2 UCRT64), so pg_store.h
# would compile the real Postgres code in while -lpq is never
# linked -> "undefined reference to PQconnectdb". Force Postgres
# support out instead (same mismatch as libcurl below, fixed the
# same way 2026-11-09). The server/console still build and run in
# txt mode, with a warning printed by the recipe.
ifeq ($(PG_LIBS),)
PG_STUB := -DPDPS_NO_LIBPQ
else
PG_STUB :=
endif

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
# If curl-config is missing, the curl headers may still be in the
# compiler's default include path, so gemini_client.cpp would
# compile the real HTTPS client in while -lcurl is never linked ->
# "undefined reference to curl_easy_init" (reported on Windows
# 2026-11-09). Force the stub instead: the server still builds and
# runs, /api/ai/health reports available=false, with a warning
# printed by the recipe. Install the curl dev package and rebuild
# for AI features.
ifeq ($(CURL_LIBS),)
CURL_STUB := -DPDPS_NO_CURL
else
CURL_STUB :=
endif

# Google Sign-In (Phase 3): link libcrypto only when OpenSSL is
# available (pkg-config openssl), which is the case when the
# OpenSSL dev headers are installed. Without it, google_auth.cpp
# compiles the stub (available() returns false, POST
# /api/auth/google answers 503 "Google sign-in unavailable") and
# the server still builds and runs — this keeps the Windows/MinGW
# build working without a new dependency (Windows CI installs no
# OpenSSL package). Same opt-in pattern as libcurl above. `make
# project` is unaffected (the console app never links OpenSSL).
OPENSSL_CFLAGS := $(shell if pkg-config --cflags openssl >/dev/null 2>&1; then pkg-config --cflags openssl; fi)
OPENSSL_LIBS := $(shell if pkg-config --libs openssl >/dev/null 2>&1; then pkg-config --libs openssl; fi)
# If pkg-config finds no openssl, the OpenSSL headers may still be
# in the compiler's default include path, so google_auth.cpp would
# compile the real verifier in while -lcrypto is never linked ->
# "undefined reference to EVP_*". Force the stub instead (same
# mismatch as libcurl, fixed the same way).
ifeq ($(OPENSSL_LIBS),)
OPENSSL_STUB := -DPDPS_NO_OPENSSL
else
OPENSSL_STUB :=
endif

# Windows (MinGW / mingw32-make): cpp_server.cpp uses Winsock, so the
# server must link -lws2_32 on Windows. $(OS) is Windows_NT under
# mingw32-make and MSYS2 make on Windows, and unset on Linux, so the
# Linux build is unchanged. `make project` needs no Winsock flag
# (the console app uses no sockets).
ifeq ($(OS),Windows_NT)
WS2_32 := -lws2_32
else
WS2_32 :=
endif

cpp_server: dashboard/cpp_server.cpp dashboard/gemini_client.cpp dashboard/google_auth.cpp dashboard/gemini_client.h dashboard/google_auth.h dashboard/pg_store.h password_hash.h
	@if [ -z "$(PG_LIBS)" ]; then echo "WARNING: pg_config not found - building WITHOUT Postgres support (txt mode only). Install mingw-w64-ucrt-x86_64-postgresql in the MSYS2 UCRT64 terminal (or libpq-dev on Debian/Ubuntu), delete cpp_server.exe, and rebuild for Neon database support."; fi
	@if [ -z "$(CURL_LIBS)" ]; then echo "WARNING: curl-config not found - building WITHOUT Gemini AI (libcurl not linked). Install mingw-w64-ucrt-x86_64-curl in the MSYS2 UCRT64 terminal (or libcurl4-openssl-dev on Debian/Ubuntu), delete cpp_server.exe, and rebuild for AI features."; fi
	@if [ -z "$(OPENSSL_LIBS)" ]; then echo "WARNING: pkg-config openssl not found - building WITHOUT Google Sign-In (OpenSSL not linked). Install mingw-w64-ucrt-x86_64-openssl in the MSYS2 UCRT64 terminal (or libssl-dev on Debian/Ubuntu), delete cpp_server.exe, and rebuild for Google sign-in."; fi
	$(CXX) $(CXXFLAGS) $(PG_CFLAGS) $(CURL_CFLAGS) $(OPENSSL_CFLAGS) $(PG_STUB) $(CURL_STUB) $(OPENSSL_STUB) -pthread -o cpp_server dashboard/cpp_server.cpp dashboard/gemini_client.cpp dashboard/google_auth.cpp $(PG_LIBS) $(CURL_LIBS) $(OPENSSL_LIBS) $(WS2_32)

clean:
	rm -f project project.exe cpp_server cpp_server.exe

.PHONY: all clean
