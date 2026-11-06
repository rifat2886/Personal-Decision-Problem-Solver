# Hugging Face Spaces deployment (Route 2 alternative, no card)

Render requires a card on file even for its Free $0 plan, so this is the
no-card alternative tried instead. The Neon Free PostgreSQL project created
for Render ("pdps", Singapore, Postgres 16) is reused unchanged.

## What runs here

- One public Hugging Face Space, Docker SDK, CPU-basic (free, 2 vCPU /
  16 GB RAM), no credit card required at signup (verified from provider
  docs/search, 2026-11-06; re-check at signup).
- The Space serves the C++ server (`dashboard/cpp_server.cpp`) on port
  7860, in Postgres mode only. Data lives in Neon, so it survives Space
  sleep/restart. Sessions are in-memory, so a restart means logging in
  again (same limit as Render).
- The Space repo root must contain: `Dockerfile`, `README.md` (frontmatter
  `sdk: docker`, `app_port: 7860`), `dashboard/` (cpp_server.cpp,
  pg_store.h, index.html, style.css, app.js), `password_hash.h`.
  Those files are kept in the project repo under `dashboard/hf-space/`
  (Dockerfile + README.md) and at the repo root / `dashboard/`.

## Setup (with the user's permission)

1. Create a Hugging Face account (GitHub sign-in) and a Space:
   name `pdps-cpp-backend`, SDK Docker, hardware CPU-basic (free),
   visibility Public (the Vercel frontend calls it without a token).
2. In the Space Settings → Variables and secrets, set as secrets:
   `DATABASE_URL` = Neon pooled connection string (from the Neon console),
   `CORS_ORIGINS` = the Vercel origins
   (`https://personal-decision-problem-solver-git-backend-108cf8-rifat-3fe6.vercel.app,https://personal-decision-problem-solver.vercel.app`).
   Never commit these values.
3. Push the Space files with a Hugging Face write token
   (`git push https://<user>:<token>@huggingface.co/spaces/<user>/pdps-cpp-backend`).
   The Space builds the Docker image automatically.
4. Verify `https://<user>-pdps-cpp-backend.hf.space/api/health` returns
   backend C++ and storage postgres, then register/login and the full API
   suite against it before wiring the Vercel frontend to it.

## Limits (honest)

- Free Spaces sleep after 48 h without traffic; the next request takes
  about 1 minute to wake. A GitHub Action pinging `/api/health` can keep
  it warm (not set up yet).
- No persistent disk: txt mode must never be used here.
- Public Space: the API URL is public, as the dashboard API is by design
  (register/login public, everything else needs a session + per-user
  isolation). Do not put secrets in the Space repo.
- If Hugging Face asks for a card at signup, STOP and report it — do not
  add one without a separate permission.
