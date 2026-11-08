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
  g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server dashboard/cpp_server.cpp
fi
echo "Dashboard: http://127.0.0.1:8000/  (stop with Ctrl+C)"
exec ./cpp_server --port 8000 --data-dir .
