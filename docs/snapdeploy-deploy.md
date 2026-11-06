# SnapDeploy deployment — free tier, no card (2026-11-06)

## Why SnapDeploy

After Render (card required even for Free $0) and Hugging Face Docker
Spaces (paid PRO required to create a Docker Space) were both ruled out,
SnapDeploy is the first host whose OWN free-tier page states the free tier
"never expires and never asks for a card": 4 containers x 512 MB / 0.25
vCPU, 100 container-hours/month shared, 10 deploys/day. Source:
https://snapdeploy.dev/free-container-hosting (checked 2026-11-06).

## Honest limits (from the same page)

- Sleeps after 15 minutes without traffic; wakes in ~60 s on the next
  **browser visit**. Scripts, bots, webhooks and cron pings do NOT wake it.
- 100 hours/month = ~3.3 hours of continuous running per day. Anything
  that must answer at 3 a.m. needs Always-On ($12/month, card — NOT used).
- No disk that survives a restart: state lives ONLY in Neon PostgreSQL
  (DATABASE_URL), never in the container. Sessions are in-memory, so a
  sleep/restart logs everyone out.
- One container per deploy, no Docker Compose. One region (AWS US East).
- No WebSockets, no custom domain on the free tier.

## How it is wired

- The repo's root `Dockerfile` (written for Render) works unchanged on
  SnapDeploy: it builds the C++ server with libpq, listens on
  `--host 0.0.0.0 --port ${PORT:-8000}` (SnapDeploy sets `PORT`), and
  runs in Postgres mode when `DATABASE_URL` is set (fail-fast, no txt
  fallback).
- Deploy source: GitHub repo `rifat2886/Personal-Decision-Problem-Solver`,
  branch `backend-testing-dashboard`, Dockerfile at repo root.
- Environment variables (set in the SnapDeploy dashboard, never in the
  repo): `DATABASE_URL` = Neon pooled connection string (project "pdps",
  Singapore, Postgres 16), `CORS_ORIGINS` = the Vercel origins.
- **Frontend wiring: use `API_BASE` (the SnapDeploy URL) directly, NOT a
  Vercel /api proxy.** A Vercel server-side proxy request is a bot-like
  request and does not wake a sleeping container; a fetch from the user's
  own browser to the SnapDeploy URL does. `CORS_ORIGINS` must therefore
  list the Vercel preview and production origins exactly.
- Expected public URL once built: `https://<name>.containers.snapdeploy.app`
  (name chosen at creation; record the real URL here after deploy).

## Launch order (same as the public-launch rule)

1. Backend live, `/api/health` returns storage postgres.
2. Owner registers the FIRST account directly against the backend URL and
   verifies `/api/users` shows exactly one ADMIN — before sharing any URL.
3. Only then wire the Vercel preview to it and share the preview URL.
