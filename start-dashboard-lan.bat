@echo off
REM Personal Decision & Problem Solver - dashboard starter, LAN mode (Windows 11)
REM Same dashboard and same data files as start-dashboard.bat, but reachable
REM from a phone on the SAME trusted Wi-Fi network.
REM
REM SAFETY - read before use:
REM  - Use ONLY on a trusted home/office Wi-Fi network you control.
REM  - NEVER on public Wi-Fi, NEVER port-forward your router, NEVER use
REM    a public tunnel (ngrok etc.) for this server: it has no HTTPS.
REM  - If Windows Firewall asks, allow it ONLY for Private networks,
REM    never for Public networks.
REM  - Close this window to stop the server when you are done.
REM  - Your phone and laptop must be on the same Wi-Fi network.
cd /d "%~dp0"
if not exist cpp_server.exe (
  echo Building the C++ server for the first time, please wait...
  where g++ >nul 2>nul
  if errorlevel 1 (
    echo ERROR: g++ (MinGW-w64) was not found.
    echo Install MinGW-w64 GCC, add it to PATH, then double-click this file again.
    echo See RUN.md for the download link and steps.
    pause
    exit /b 1
  )
  g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server.exe dashboard\cpp_server.cpp -lws2_32
  if errorlevel 1 (
    echo ERROR: the build failed. See the messages above, or RUN.md troubleshooting.
    pause
    exit /b 1
  )
  echo Build finished.
)
echo.
echo LAN mode: the dashboard will be reachable on your local network (port 8000).
echo Find your laptop IP: open Command Prompt and run  ipconfig  -- look for "IPv4 Address" under your Wi-Fi adapter.
echo On your phone, open:  http://^<your-laptop-IP^>:8000/
echo Example: if ipconfig shows 192.168.1.5, open http://192.168.1.5:8000/
echo To stop the server, close this window or press Ctrl+C.
echo Do NOT port-forward this server to the internet.
cpp_server.exe --host 0.0.0.0 --port 8000 --data-dir .
pause
