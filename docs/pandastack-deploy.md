# PandaStack deployment — EXPERIMENT FAILED (2026-11-06 12:01)

## Result: Apps need a paid plan on the Free tier

PandaStack's own billing docs say "Apps deploy on the Free tier" with a
$5.40/mo credit, but the live dashboard REJECTED app creation with:
"Create failed: Apps need a paid plan. Upgrade your plan in Billing,
then deploy again." No app was created, no URL, no /api/health check.
The dashboard also lists Pro at $49/mo (docs say $20/mo) and shows no
$5.40 credit balance — the docs are out of date on price. No card was
added, no plan upgraded. Account exists (rifat2886, Free $0, signed in).

Path A (app from git URL, apt g++ build) failed at creation, before any
build step — apt permission and C++ runtime were never tested.
Path B (custom Dockerfile template) is NOT applicable: templates are
sandbox-only ("Pre-baked Firecracker rootfs snapshots. Launch a sandbox
from any of them"), the Apps form has only a Runtime dropdown
(Auto-detect, Node, Python, Go, Ruby, Rust, Bun, Deno — no C++, no
template field), and custom builds are CLI-only. There is no free route
to run this app on PandaStack. Do not retry without a paid plan.

## What remains

- SnapDeploy: both deploys blocked by Acceptable Use Policy (see
  docs/snapdeploy-deploy.md); appeal to billing@snapdeploy.dev within 7
  days of 2026-11-06, or clean the repo and retry (3 of 5 deploys left
  in the 12h window).
- Back4App: free container destroyed 60 minutes after each deploy —
  1-hour demo only.
- Neon "pdps" Postgres project remains valid for any future host.
- Honest position: no mainstream free host found yet gives C++
  long-running + persistent disk + instant 24/7 + no card all at once.
