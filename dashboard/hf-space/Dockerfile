# Personal Decision & Problem Solver — C++ backend for Hugging Face Spaces (Route 2 alt, no card)
#
# Hugging Face Spaces (Docker SDK, free CPU-basic) runs the container as
# uid 1000 and expects the app on port 7860. This Dockerfile is a copy of
# the Render Dockerfile adapted only for those two facts:
#   - WORKDIR /home/user/app, owned by uid 1000, USER 1000 at runtime
#   - CMD listens on 0.0.0.0:7860 (explicit --port wins over $PORT)
# Postgres mode is mandatory here, exactly as on Render: DATABASE_URL must
# be set as a Space secret; without it the server fails fast instead of
# serving an empty txt data set (there is no persistent disk on Spaces).
# Secrets are set in the Space Settings, never baked into this image and
# never committed to the repo.

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        g++ \
        libpq-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY dashboard/ ./dashboard/
COPY password_hash.h ./
RUN chown -R user:user /home/user/app

# -I is required: libpq-fe.h is in /usr/include/postgresql on Debian.
RUN g++ -std=c++17 -Wall -Wextra -pthread \
        -I/usr/include/postgresql \
        -o /home/user/app/cpp_server dashboard/cpp_server.cpp -lpq

EXPOSE 7860
USER user

CMD ["./cpp_server", "--host", "0.0.0.0", "--port", "7860"]
