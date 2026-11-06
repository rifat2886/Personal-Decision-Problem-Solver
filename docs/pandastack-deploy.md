# PandaStack deployment — EXPERIMENT (2026-11-06)

## Status: experiment, not a proven host

PandaStack was picked as the #2 no-card option, then corrected: its app
hosting deploys from a git URL with a build command (runtimes installed
with mise) — there is NO Dockerfile deploy step for apps, and no C++
example in its docs. What its own docs DO confirm:

- Billing (https://docs.pandastack.ai/docs/getting-started/billing/):
  Free $0, $5.40/mo usage credit; $0.054/active vCPU-hour +
  $0.0162/working-set GiB-hour. Apps deploy on the Free tier. An app
  kept always-on exhausts the free credit in a few days and is then
  hibernated until next month. Running out of credit pauses compute, it
  never destroys work and never surprise-bills. Homepage says no card
  for the free tier — re-verify at signup; STOP if a card is asked for.
- Full-stack hosting
  (https://www.pandastack.ai/solutions/full-stack-hosting/): "Deploy from
  a git URL", pipeline clones the ref, installs runtimes with mise,
  builds, starts the app, health-checks its port. Only PORT and HOST
  are injected automatically. TLS is mandatory for its Postgres (our
  Neon string already uses sslmode=require).
- Templates (https://docs.pandastack.ai/docs/templates/overview/):
  a custom template IS built from a Dockerfile ("You give PandaStack a
  Dockerfile and it does the rest"), Debian-based images only, build
  context <= 50 MB / <= 50 files. Our repo Dockerfile context is 13
  files, ~280 KB, debian:bookworm-slim — it fits. Templates are
  documented for sandboxes; whether an App can run on a custom template
  is UNCONFIRMED — that is part of the experiment.

## Experiment plan (in order)

1. Create a free PandaStack account (GitHub or email). No card, no
   paid plan, no add-on. If a card is asked for at any step: STOP.
2. Path A — App from git URL: repo
   rifat2886/Personal-Decision-Problem-Solver, branch
   backend-testing-dashboard. Build command (Ubuntu base, needs apt):
   `apt-get update && apt-get install -y g++ libpq-dev && g++ -std=c++17 -Wall -Wextra -pthread -I/usr/include/postgresql -o cpp_server dashboard/cpp_server.cpp -lpq`
   Start command: `./cpp_server --host 0.0.0.0 --port $PORT`
   Env vars (dashboard only, never in the repo): DATABASE_URL = Neon
   pooled connection string, CORS_ORIGINS = the two Vercel origins.
   If apt is not permitted in the build sandbox, Path A fails.
3. Path B — custom template from the repo root Dockerfile, then run
   the app/sandbox from that template with the same start command and
   env vars. Only if the dashboard/CLI offers a template choice for
   apps; do not force it.
4. Verify: public URL answers /api/health with storage postgres.
   Then owner registers the FIRST account directly against the backend
   URL and verifies /api/users shows exactly one ADMIN, before any
   Vercel wiring or sharing.

## Limits if it works

- Sleeps when idle; credit covers a sleeping side project, not 24/7.
  Always-on needs Pro ($20/mo) — NOT used.
- Sessions are in-memory: a sleep/restart logs everyone out. State
  lives only in Neon Postgres.
- Frontend wiring: use API_BASE (the PandaStack URL) directly from the
  browser, not a Vercel /api proxy (a proxy request is bot-like and
  may not wake a sleeping app); CORS_ORIGINS must list the Vercel
  origins exactly.
