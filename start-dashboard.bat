@echo off
REM Personal Decision & Problem Solver - dashboard starter (Windows 11)
REM Requires MinGW-w64 g++ on PATH, or MSVC (see dashboard\README.md for the cl command).
REM Data files live in this repository directory (same files the console app uses).
REM Do NOT expose this server to the internet: passwords are stored in plain text
REM in users.txt (inherited C++ format). See dashboard\README.md, "Security".
cd /d %~dp0
if not exist cpp_server.exe (
  echo Building C++ server...
  g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server.exe dashboard\cpp_server.cpp -lws2_32
)
echo Dashboard: http://127.0.0.1:8000/  (stop with Ctrl+C)
cpp_server.exe --port 8000 --data-dir .
