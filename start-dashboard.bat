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
REM Phase 4, Batch B: detect PostgreSQL dev files for the optional
REM Postgres build (same pattern as start-console.bat). Set before
REM the build block so %PG_CFLAGS% / %PG_LIBS% expand to these
REM values. Without pg_config the server builds txt-only, as before
REM — and then runs in txt mode even if DATABASE_URL is set.
set PG_CFLAGS=
set PG_LIBS=
set PG_STUB=-DPDPS_NO_LIBPQ
where pg_config >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%I in ('pg_config --includedir') do set PG_CFLAGS=-I%%I
  set PG_LIBS=-lpq
  set PG_STUB=
)
if not exist cpp_server.exe (
  echo Building the C++ server for the first time, please wait...
  if not "%PG_STUB%"=="" echo WARNING: pg_config not found - building WITHOUT Postgres support. Install mingw-w64-ucrt-x86_64-postgresql in the MSYS2 UCRT64 terminal, delete cpp_server.exe, and double-click again for Neon database support.
  where g++ >nul 2>nul
  if errorlevel 1 (
    echo ERROR: g++ MinGW-w64 was not found.
    echo Install MinGW-w64 GCC, add it to PATH, then double-click this file again.
    echo See RUN.md for the download link and steps.
    pause
    exit /b 1
  )
  REM Gemini (Phase 1): link libcurl when the curl dev files are
  REM really usable. gemini_client.cpp must always be compiled:
  REM without it the link fails (undefined gemini::* symbols).
  REM
  REM Build fix (2026-11-10): do NOT trust `where curl-config`.
  REM MSYS2 ships curl-config as a shell script, so cmd's `where`
  REM finds it but cmd cannot RUN it ("'curl-config' is not
  REM recognized"). The old check therefore took the libcurl
  REM branch, got empty flags, and the link failed with
  REM "undefined reference to __imp_curl_easy_init". Instead:
  REM  (1) actually run curl-config and capture its output;
  REM      if the capture produced flags, use them.
  REM  (2) otherwise look next to g++ itself: the curl headers
  REM      and import library live in the same UCRT64 tree
  REM      (include\curl\curl.h + lib\libcurl.dll.a); use -I/-lcurl.
  REM  (3) otherwise build the stub (-DPDPS_NO_CURL): the server
  REM      still builds and runs, AI answers 503, with a warning.
  REM The 2^>nul hides the "not recognized" noise when a command
  REM cannot run. All CURL_* values are set inside this block, so
  REM they are read with !VAR! (delayed expansion) below.
  set "CURL_CFLAGS="
  set "CURL_LIBS="
  set "CURL_STUB=-DPDPS_NO_CURL"
  for /f "delims=" %%C in ('curl-config --cflags 2^>nul') do set "CURL_CFLAGS=%%C"
  for /f "delims=" %%L in ('curl-config --libs 2^>nul') do set "CURL_LIBS=%%L"
  if not "!CURL_LIBS!"=="" set "CURL_STUB="
  if not "!CURL_STUB!"=="" (
    set "CURL_ROOT="
    for /f "delims=" %%G in ('where g++ 2^>nul') do if not defined CURL_ROOT set "CURL_ROOT=%%~dpG.."
    if defined CURL_ROOT for %%R in ("!CURL_ROOT!") do set "CURL_ROOT=%%~fR"
    if defined CURL_ROOT if exist "!CURL_ROOT!\include\curl\curl.h" if exist "!CURL_ROOT!\lib\libcurl.dll.a" (
      set "CURL_CFLAGS=-I!CURL_ROOT!\include"
      set "CURL_LIBS=-lcurl"
      set "CURL_STUB="
    )
  )
  if not "!CURL_STUB!"=="" echo WARNING: curl-config could not be run - building WITHOUT Gemini AI. Install mingw-w64-ucrt-x86_64-curl in the MSYS2 UCRT64 terminal, delete cpp_server.exe, and double-click again for AI features.
  REM Google Sign-In (Phase 3): link libcrypto when the OpenSSL
  REM dev files are really usable. google_auth.cpp must always be
  REM compiled: without it the link fails (undefined google_auth::*
  REM symbols). Same pattern as curl above: (1) try pkg-config;
  REM (2) otherwise look next to g++ in the UCRT64 tree
  REM (include\openssl\evp.h + lib\libcrypto.dll.a); (3) otherwise
  REM build the stub (-DPDPS_NO_OPENSSL): the server still builds
  REM and runs, Google sign-in answers 503, with a warning.
  set "OPENSSL_CFLAGS="
  set "OPENSSL_LIBS="
  set "OPENSSL_STUB=-DPDPS_NO_OPENSSL"
  for /f "delims=" %%C in ('pkg-config --cflags openssl 2^>nul') do set "OPENSSL_CFLAGS=%%C"
  for /f "delims=" %%L in ('pkg-config --libs openssl 2^>nul') do set "OPENSSL_LIBS=%%L"
  if not "!OPENSSL_LIBS!"=="" set "OPENSSL_STUB="
  if not "!OPENSSL_STUB!"=="" (
    set "OPENSSL_ROOT="
    for /f "delims=" %%G in ('where g++ 2^>nul') do if not defined OPENSSL_ROOT set "OPENSSL_ROOT=%%~dpG.."
    if defined OPENSSL_ROOT for %%R in ("!OPENSSL_ROOT!") do set "OPENSSL_ROOT=%%~fR"
    if defined OPENSSL_ROOT if exist "!OPENSSL_ROOT!\include\openssl\evp.h" if exist "!OPENSSL_ROOT!\lib\libcrypto.dll.a" (
      set "OPENSSL_CFLAGS=-I!OPENSSL_ROOT!\include"
      set "OPENSSL_LIBS=-lcrypto"
      set "OPENSSL_STUB="
    )
  )
  if not "!OPENSSL_STUB!"=="" echo WARNING: OpenSSL dev files not found - building WITHOUT Google Sign-In. Install mingw-w64-ucrt-x86_64-openssl in the MSYS2 UCRT64 terminal, delete cpp_server.exe, and double-click again for Google sign-in.
  g++ -std=c++17 -Wall -Wextra -pthread !CURL_CFLAGS! !CURL_STUB! !OPENSSL_CFLAGS! !OPENSSL_STUB! %PG_STUB% %PG_CFLAGS% -o cpp_server.exe dashboard\cpp_server.cpp dashboard\gemini_client.cpp dashboard\google_auth.cpp -lws2_32 !CURL_LIBS! !OPENSSL_LIBS! %PG_LIBS%
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
