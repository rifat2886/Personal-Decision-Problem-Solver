---
title: PDPS C++ Backend
emoji: 🧭
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Personal Decision & Problem Solver — C++ Backend

Free Hugging Face Spaces (Docker SDK) hosting for the C++ API server of the
Personal Decision & Problem Solver project. The server runs in Postgres mode
only (`DATABASE_URL` Space secret, Neon Free PostgreSQL) — there is no
persistent disk on Spaces. Frontend: Vercel preview of the same project.
See `docs/hf-spaces-deploy.md` in the project repo for the full setup.
