# Personal Decision & Problem Solver — C++ backend for Render (Route 2, Phase 1)
#
# This image builds ONLY the C++ server (dashboard/cpp_server.cpp).
# It does not build or run the console app, and it does not need
# any txt data files: in production it runs in Postgres mode
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
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY dashboard/ ./dashboard/
COPY password_hash.h ./

# -I is required: libpq-fe.h is in /usr/include/postgresql on
# Debian, not a default search path. Without it, Postgres support
# is silently compiled out (see pg_store.h) and the server would
# fail fast on Render instead of connecting to Postgres.
RUN g++ -std=c++17 -Wall -Wextra -pthread \
        -I/usr/include/postgresql \
        -o /app/cpp_server dashboard/cpp_server.cpp -lpq

# Render sets PORT at runtime; EXPOSE is documentation only.
EXPOSE 8000

# The server reads PORT, DATABASE_URL and CORS_ORIGINS from the
# environment (see cpp_server.cpp --help). --host 0.0.0.0 is
# required on Render, where the platform, not localhost, routes
# traffic to the container. --data-dir is unused in Postgres
# mode except for export side-files, which are skipped there.
CMD ["/bin/sh", "-c", "exec /app/cpp_server --host 0.0.0.0 --port ${PORT:-8000}"]
