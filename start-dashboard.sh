#!/bin/sh
# Personal Decision & Problem Solver - dashboard starter (Linux/macOS)
# Builds the C++ server if needed, then serves the dashboard on http://127.0.0.1:8000/
# Data files live in this repository directory (same files the console app uses).
# Do NOT expose this server to the internet: this server binds to
# localhost only and has no HTTPS of its own. Passwords are stored
# as PBKDF2 hashes in users.txt (old plaintext accounts are upgraded
# to a hash on their next login). See SECURITY.md.
set -e
cd "$(dirname "$0")"
if [ ! -x ./cpp_server ]; then
  echo "Building C++ server..."
  # Gemini (Phase 1): link libcurl only when curl-config exists,
  # which is the case when libcurl dev headers are installed.
  # Without curl-config, gemini_client.cpp compiles the stub
  # (available() returns false) and AI endpoints answer 503.
  # Same opt-in pattern as the Makefile. gemini_client.cpp must
  # always be compiled: without it the link fails (undefined
  # gemini::* symbols, called from cpp_server.cpp).
  CURL_CFLAGS=$(curl-config --cflags 2>/dev/null || true)
  CURL_LIBS=$(curl-config --libs 2>/dev/null || true)
  g++ -std=c++17 -Wall -Wextra -pthread $CURL_CFLAGS -o cpp_server dashboard/cpp_server.cpp dashboard/gemini_client.cpp $CURL_LIBS
fi
echo "Dashboard: http://127.0.0.1:8000/  (stop with Ctrl+C)"
exec ./cpp_server --port 8000 --data-dir .
