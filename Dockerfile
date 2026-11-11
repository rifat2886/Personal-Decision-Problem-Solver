# Personal Decision & Problem Solver — C++ backend for Render (Route 2, Phase 1)
#
# This image builds ONLY the C++ server (dashboard/cpp_server.cpp
# + dashboard/gemini_client.cpp + dashboard/google_auth.cpp). It
# does not build or run the console app, and it does not need any
# txt data files: in production it runs in Postgres mode
# (DATABASE_URL is set by Render from the Neon database, as an
# environment variable — never baked into this image, never
# committed to the repo).
#
# Build locally (no account needed, for a smoke test only):
#   docker build -t pdps-cpp-server .
#   docker run -e PORT=8000 -p 8000:8000 pdps-cpp-server
# The container listens on $PORT (Render sets PORT automatically)
# and on 0.0.0.0, because Render terminates TLS and forwards
# plain HTTP to the container. Do NOT run this image with a
# public port and no DATABASE_URL/CORS setup outside Render's
# documented configuration (see docs/route2-phase1.md).

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        g++ \
        libpq-dev \
        libcurl4-openssl-dev \
        libssl-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY dashboard/ ./dashboard/
COPY password_hash.h ./

# -I is required: libpq-fe.h is in /usr/include/postgresql on
# Debian, not a default search path. Without it, Postgres support
# is silently compiled out (see pg_store.h) and the server would
# fail fast on Render instead of connecting to Postgres.
# Gemini (Phase 1/2): gemini_client.cpp MUST be compiled and
# linked with the curl-config flags. Without the file the link
# fails (undefined gemini::* symbols, called from cpp_server.cpp);
# without libcurl the client compiles to the stub (available()
# returns false) and every AI endpoint answers 503 in production.
# curl-config is provided by libcurl4-openssl-dev above.
# Google Sign-In (Phase 3): google_auth.cpp MUST be compiled and
# linked with -lcrypto (libssl-dev above). Without the file the
# link fails (undefined google_auth::* symbols); without libcrypto
# it compiles to the stub (available() returns false) and every
# Google endpoint answers 503 in production.
RUN g++ -std=c++17 -Wall -Wextra -pthread \
        -I/usr/include/postgresql \
        $(curl-config --cflags) \
        -o /app/cpp_server dashboard/cpp_server.cpp dashboard/gemini_client.cpp dashboard/google_auth.cpp \
        -lpq $(curl-config --libs) -lcrypto

# Render sets PORT at runtime; EXPOSE is documentation only.
EXPOSE 8000

# The server reads PORT, DATABASE_URL and CORS_ORIGINS from the
# environment (see cpp_server.cpp --help). --host 0.0.0.0 is
# required on Render, where the platform, not localhost, routes
# traffic to the container. --data-dir is unused in Postgres
# mode except for export side-files, which are skipped there.
CMD ["/bin/sh", "-c", "exec /app/cpp_server --host 0.0.0.0 --port ${PORT:-8000}"]
