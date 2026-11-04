#!/bin/sh
# Personal Decision & Problem Solver - dashboard starter, LAN mode (Linux/macOS)
# Same dashboard and same data files as start-dashboard.sh, but reachable
# from a phone on the SAME trusted Wi-Fi network.
#
# SAFETY - read before use:
#  - Use ONLY on a trusted home/office Wi-Fi network you control.
#  - NEVER on public Wi-Fi, NEVER port-forward your router, NEVER use
#    a public tunnel (ngrok etc.) for this server: it has no HTTPS.
#  - Stop the server (Ctrl+C) when you are done on the phone.
#  - Your phone and laptop must be on the same Wi-Fi network.
set -e
cd "$(dirname "$0")"
if [ ! -x ./cpp_server ]; then
  echo "Building C++ server..."
  g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server dashboard/cpp_server.cpp
fi
echo "LAN mode: starting on all local interfaces (port 8000)."
echo "On your phone, open:  http://<your-laptop-IP>:8000/"
echo "Find your laptop IP with:  hostname -I   (Linux)  or  ipconfig getifaddr en0   (macOS)"
echo "Stop with Ctrl+C when done. Do NOT port-forward this server."
exec ./cpp_server --host 0.0.0.0 --port 8000 --data-dir .
