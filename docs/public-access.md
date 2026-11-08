# Public Access — Vercel login wall, and how to get a free permanent public URL

Status: **AUDIT + CODE PREP ONLY. No Vercel setting was changed,
no production deployment was made, no main merge happened, and
no paid plan was used.** Changing the setting below needs the
user's separate, explicit permission (see section 5).

## 1. Why a login wall appears today — the exact cause

Verified read-only on 2026-11-05 from the Vercel project
`personal-decision-problem-solver`
(`prj_YSyI3FmTsdiANBuXV0CnEWj1EtHI`, account `rifat2886`,
Hobby plan):

- `ssoProtection.enabled = true`
- `ssoProtection.deploymentType = "all_except_custom_domains"`
- `passwordProtection.enabled = false`
- `trustedIps.enabled = false`

That is Vercel Authentication (SSO), not the project's own
login. "SSO" here means: Vercel asks the visitor to sign in
with a Vercel / Google / GitHub account that belongs to the
project's team, before Vercel serves any page at all. The
project's own Welcome / Login / Register page is behind that
wall, so a stranger cannot even reach it.

Two things this is NOT:
- It is NOT a password on the site (password protection is off).
- It is NOT the project's username/password login (that login
  is in `dashboard/app.js` + the C++/Python server, with
  PBKDF2 hashes, and it works only AFTER Vercel lets the
  visitor through).

Why the second preview test in the previous round showed "no
SSO": that browser session already held a Vercel team login
from the earlier test, so Vercel let it through without asking
again. That was an authenticated session being reused, not
public access. A visitor with no Vercel login still hits the
wall — that is the behaviour to fix.

## 2. Current URLs — what each one actually serves today

| URL | What it is | Login wall today? | What it serves |
|---|---|---|---|
| `https://personal-decision-problem-solver.vercel.app/` | Production alias | YES (SSO, `all_except_custom_domains`) | GitHub **main** `ce2f9a2` — which has **no dashboard at all** (no HTML/CSS/JS on main). Even with the wall removed, this URL would not show the dashboard until the production deployment is changed (section 4). |
| `https://personal-decision-problem-solver-git-backend-108cf8-rifat-3fe6.vercel.app/` | Branch (preview) alias, always points at the latest preview of `backend-testing-dashboard` | YES (SSO) | Latest PR preview (after Phase 1, head `e4f428a`, deployment `dpl_9yAT3KErmEK5zUiJ67SWNmGbH12Q`, READY). This is a **preview** URL: it changes with every PR push and is not a permanent production URL. |
| `https://personal-decision-problem-solver-<random>-rifat-3fe6.vercel.app/` | One preview deployment's own URL | YES (SSO) | One single commit's preview. Also temporary. |

Conclusion: there is **no permanent public production URL
today**, for two independent reasons: (1) SSO blocks every
`.vercel.app` URL, and (2) the production deployment is from
main, which has no dashboard. Fixing only (1) is not enough;
both must be fixed, in the order in section 4.

## 3. How a completely free permanent public link is possible

No paid plan, no custom domain, and no new account are needed:

1. **Remove the SSO wall for production** (free on Hobby).
   In Vercel Dashboard: Project → Settings → Deployment
   Protection → Vercel Authentication. Two free options:
   - **Recommended: preview-only.** Set Vercel Authentication
     to "Only Preview Deployments". Production
     (`.vercel.app`) becomes public; previews stay behind
     the team login, so work-in-progress PR builds are not
     public. This meets the user's public-URL requirement
     while keeping unfinished previews private.
   - **Alternative: off for all deployments.** Disable Vercel
     Authentication entirely. Then preview URLs are public
     too. This is what "Preview or Production URL, no login"
     literally asks for, but it publishes every PR preview,
     including unfinished work, to anyone with the link.
   The choice between these two is a user decision (see
   section 5). Neither option costs money, and neither needs
   a custom domain. (Note: `all_except_custom_domains` means
   a custom domain would bypass SSO, but a custom domain
   costs ~$10–15/year and is NOT needed — do not buy one
   for this.)
2. **Point production at the dashboard code** (free, but a
   production change — needs separate permission). One of:
   - Merge PR #64 into main (the normal path, but it is
     gated by the standing rule: no merge until Windows CI
     + real Windows runtime pass and a final merge-readiness
     report + separate merge approval), then Vercel's Git
     integration auto-deploys main to production; OR
   - Promote the latest PR preview to production in Vercel
     (a production deployment, also gated — the user said
     "no production deployment" in this round); OR
   - Change the project's production branch to
     `backend-testing-dashboard` (a project-settings change,
     also gated).
   Until one of these happens, the permanent production URL
   will stay on main and will not show the dashboard, even
   with SSO off.
3. **Connect the backend** (free, Route 2 Phase 1 code is
   ready, accounts are not). The public frontend alone can
   show Welcome / Register / Login, but Register/Login will
   return `404` for `/api/*` until the Render C++ backend +
   Neon Postgres are connected (this is exactly what the
   preview tests already showed). That step needs its own
   permission (Render + Neon account setup), and it is NOT
   part of this round. A public URL without a backend is a
   public landing page, not a working public app — do not
   present it as finished until the backend test passes on
   the live URL.

After steps 1–3, the permanent public URL is simply the
existing production alias:
`https://personal-decision-problem-solver.vercel.app/`
— no new URL, no new project, no domain purchase. It works
on desktop, laptop, iPhone and Android because it is a plain
HTTPS static site (the dashboard is already responsive,
mobile drawer under 720px, tested at 360/375/390px locally;
live mobile on the preview could not be verified with the
browser tool, which has no 390px resize — see the preview
auth test report).

## 4. Security when the Vercel wall is removed — what stays safe, what to watch

What does NOT change when SSO is removed (verified in code,
not assumed):
- **Project login stays.** Register/Login are the project's
  own system: username + password, 8+ characters with a
  letter and a digit, stored as PBKDF2-HMAC-SHA256 hashes
  (`pbkdf2$100000$…`, same format in C++ and Python).
  No Google/GitHub OAuth code exists anywhere in the
  frontend or servers (grep-verified in this round).
- **No user data is in the frontend.** The static files
  contain no passwords, no database strings, no tokens, and
  no other user's data. Static serving in both servers is
  limited to `index.html`, `style.css`, `app.js` — data
  files/tables are never served as static files.
- **Every protected API still needs a token.** After the
  auth-gate fix, the frontend shows only Welcome/Login/
  Register before a verified login, and every other `/api`
  route returns 401 without a valid session (401 sweep
  21/21 endpoints, auth_gate 30/30 on both servers, in txt
  mode; pg_test 41/41 in Postgres mode, including its own
  401 sweep).
- **Per-user isolation stays.** Reads/writes/edits/deletes/
  reports/backups/exports are owner-filtered; cross-user
  PATCH/DELETE return 404; ADMIN sees username/role only,
  never other users' private records; legacy (NULL-owner)
  records are visible only to a sole user.
- **Login brute force is rate-limited** (5 failed attempts
  per username in 300s → 429, both servers). Bodies are
  capped at 1 MiB. CORS, when used, is an exact-origin
  allowlist only (`*` is ignored); the recommended Vercel
  `/api` proxy needs no CORS at all.
- **Database string stays secret.** `DATABASE_URL` lives
  only in Render/Neon environment variables, never in the
  repo, never in the frontend, never in `render.yaml`.

What to watch once anyone can register (this is the new
risk that SSO previously hid):
- **Open registration is intended** (the user's requirement
  6), but it also means anyone can create accounts, including
  spam accounts. There is currently **no CAPTCHA, no email
  verification, and no per-IP register rate limit** in either
  server. A per-IP limit was deliberately NOT added in this
  round: many legitimate users behind one mobile NAT share
  a public IP, so a strict IP limit could block real users.
  Decision needed before a high-traffic launch: accept open
  registration and monitor, or add CAPTCHA/email verification
  (both are new work, not free in the same way, and need
  separate design).
- **Username enumeration exists today** (register says
  "already exists" for a taken name; login says "invalid"
  for a wrong pair). That was already true before, and SSO
  only hid it from strangers. It is low severity for this
  app (usernames are not secret), but it should not be
  presented as if it were fixed by removing SSO.
- **First registered user becomes ADMIN.** On a fresh
  production database, the very first registration is ADMIN.
  That account must be created by the owner first, before
  the URL is shared widely, or a stranger could become
  ADMIN. This is the single most important ordering rule
  for the public launch (see section 5, step order).
- **Sleep/wake and session loss** (Route 2 free tier) are
  unchanged: Render Free sleeps after 15 min idle, sessions
  are in-memory, so users re-login after a wake. Data in
  Postgres survives. See `docs/route2-phase1.md` section 7.

## 5. Exact permission needed before any settings change (NOT done in this round)

Do NOT run any of these until the user explicitly approves
them, in a separate message, after reading this plan:

1. **Vercel Authentication change** — choose one:
   (a) preview-only (recommended), or (b) off for all
   deployments. Scope: project
   `personal-decision-problem-solver` only, SSO setting
   only; no password, no trusted-IP, no domain change.
2. **Production deployment change** — choose one: merge
   PR #64 to main (subject to the standing merge gates),
   promote the PR preview to production, or change the
   production branch. Scope: production deployment only.
3. **Backend connection** — Render + Neon account setup
   and `DATABASE_URL`/`CORS_ORIGINS` (or the Vercel `/api`
   proxy rewrite), as in `docs/route2-phase1.md`.
4. **Launch order** (must be in this order, or a stranger
   could take ADMIN): backend connected → owner registers
   the first (ADMIN) account on the live URL → SSO change
   applied → URL shared publicly → live test (register a
   second user, check per-user isolation, logout, refresh,
   invalid session, mobile + desktop) on the public URL.

## 6. Code changes prepared in this round (PR branch only, safe)

- `dashboard/index.html` (text only, no logic change):
  the landing hero no longer says "localhost only / plain-
  text files" (that was already inaccurate for LAN mode and
  false for the online Postgres mode); it now says no
  Google/GitHub sign-in or invitation is needed, registration
  is in this app's own system, and each user's data is
  private to their account. The auth section no longer says
  "uses users.txt" (false in Postgres mode); it says the
  same, in mode-neutral terms, with hashes for new accounts.
- This document (`docs/public-access.md`): the full plan
  above, so the permission decision in section 5 can be
  made from one place.
- No Vercel setting, no production deployment, no main
  change, no backend connection, and no auth-logic change
  was made in this round. The auth gate, per-user isolation,
  rate limiting, and CORS rules are unchanged.
