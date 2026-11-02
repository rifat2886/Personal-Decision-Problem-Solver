#!/bin/sh
# Personal Decision & Problem Solver - dashboard starter (Linux/macOS)
# Builds the C++ server if needed, then serves the dashboard on http://127.0.0.1:8000/
# Data files live in this repository directory (same files the console app uses).
# Do NOT expose this server to the internet: passwords are stored in plain text
# in users.txt (inherited C++ format). See dashboard/README.md, "Security".
set -e
cd "$(dirname "$0")"
if [ ! -x ./cpp_server ]; then
  echo "Building C++ server..."
  g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server dashboard/cpp_server.cpp
fi
echo "Dashboard: http://127.0.0.1:8000/  (stop with Ctrl+C)"
exec ./cpp_server --port 8000 --data-dir .
