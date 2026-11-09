@echo off
REM Delayed expansion is required below: the curl flags are set
REM by FOR loops inside a parenthesised block, and %VAR% would
REM expand when the block is parsed (empty), while !VAR! expands
REM when the line runs (after the loops). Without this, the
REM server would silently build WITHOUT libcurl.
setlocal EnableDelayedExpansion
REM Personal Decision & Problem Solver — dashboard starter (Windows 11)
REM Double-click this file, then open http://127.0.0.1:8000/ in your browser.
REM It builds the C++ server if needed. Data files live in this folder,
REM the same files the console app uses.
REM
REM SECURITY: this server is for your own computer only (localhost).
REM Do NOT put it on the public internet. See SECURITY.md.
cd /d "%~dp0"
if not exist cpp_server.exe (
  echo Building the C++ server for the first time, please wait...
  where g++ >nul 2>nul
  if errorlevel 1 (
    echo ERROR: g++ MinGW-w64 was not found.
    echo Install MinGW-w64 GCC, add it to PATH, then double-click this file again.
    echo See RUN.md for the download link and steps.
    pause
    exit /b 1
  )
  REM Gemini (Phase 1): link libcurl only when curl-config is
  REM on PATH (mingw-w64-x86_64-curl installed). Without it,
  REM gemini_client.cpp compiles the stub (available() returns
  REM false) and AI endpoints answer 503. Same opt-in pattern
  REM as the Makefile. gemini_client.cpp must always be compiled:
  REM without it the link fails (undefined gemini::* symbols).
  where curl-config >nul 2>nul
  if errorlevel 1 (
    g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server.exe dashboard\cpp_server.cpp dashboard\gemini_client.cpp -lws2_32
  ) else (
    for /f "delims=" %%C in ('curl-config --cflags') do set CURL_CFLAGS=%%C
    for /f "delims=" %%L in ('curl-config --libs') do set CURL_LIBS=%%L
    g++ -std=c++17 -Wall -Wextra -pthread !CURL_CFLAGS! -o cpp_server.exe dashboard\cpp_server.cpp dashboard\gemini_client.cpp -lws2_32 !CURL_LIBS!
  )
  if errorlevel 1 (
    echo ERROR: the build failed. See the messages above, or RUN.md troubleshooting.
    pause
    exit /b 1
  )
  echo Build finished.
)
echo.
echo Dashboard is ready: open http://127.0.0.1:8000/ in your browser.
echo First time? Click "Login / Register", then Register.
echo The first account you create becomes ADMIN.
echo To stop the server, close this window or press Ctrl+C.
cpp_server.exe --port 8000 --data-dir .
pause
