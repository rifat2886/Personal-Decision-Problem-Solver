# iPhone preview: /api/register returns 404 — investigation (2026-11-06)

## What the user saw

- Device: iPhone Safari.
- Preview URL: `https://personal-decision-problem-solver-git-backend-108cf8-rifat-3fe6.vercel.app/`
- Register button responds (the tap works, the form submits).
- Error shown: `Request failed: 404`.
- No account was created, no dashboard appeared.

## Root cause (verified, not guessed)

**The C++ backend is NOT connected — there is no backend at all
behind this preview, so `/api/register` has nowhere to go.**

1. **Frontend API base URL:** `dashboard/app.js` uses
   `API_BASE = window.PDPS_API_BASE || ""` — empty by default,
   meaning "same origin". No `api-config.js` with a Render URL is
   committed (by design: a real backend URL must never be committed
   with secrets, and none exists yet). So the iPhone called
   `https://<preview>/api/register` on Vercel itself.
2. **Vercel routing:** `vercel.json` (PR branch only) rewrites
   only `/` → `/dashboard/index.html`, `/index.html` → the same,
   `/style.css` and `/app.js`. There is deliberately **no `/api/*`
   rewrite**, because there is no Render backend URL to rewrite to.
   Vercel therefore serves its static 404 for `/api/register`.
   The frontend's `api()` then turned that into the generic
   `Request failed: 404` — which looked like a registration bug,
   but was actually a missing-backend signal.
3. **Backend connection: NO.** Confirmed three ways:
   - No Render service and no Neon database have been created or
     connected (standing gate; this round also created none).
   - The latest preview deployment for this branch
     (`dpl_EtuiHV1VSTUYSEXWMLkcLHps8aZr`, from PR head `78f9c7c`,
     READY, target null) is a static-only deployment.
   - A direct `curl -X POST <preview>/api/register` returns
     Vercel's `401 Protected deployment` (SSO) before any API
     code runs, and from a signed-in browser the same path
     returns Vercel's 404 — never a C++ or Python server response.
     Locally, the same code passes: `api_test.py` 36/36 and
     `per_user_test.py` 29/29 against both local servers, and
     `/api/register` works there.
4. **This is NOT an auth-gate or registration bug.** The register
   handler, username validation and password rules were verified
   locally in the 2026-11-05 rounds. The 404 happens before any
   of that code runs, because the request never reaches a server.

## What was fixed in this round (PR #64 branch only)

No fake or mock registration was added — that was explicitly
forbidden, and it would have hidden the real problem.

- `dashboard/app.js` — `api()` now throws a plain-language error
  when a same-origin (`API_BASE` empty) `/api/*` call returns 404:
  *"Backend is not connected yet — this preview is frontend-only.
  No account was created. Register and Login will work after the
  Render backend is connected."* When `API_BASE` is set (a real
  Render backend), a 404 keeps the backend's own message.
- `dashboard/app.js` — new `checkBackend()` on page load: it calls
  the public `/api/health` endpoint. If it answers, nothing
  changes. If it returns 404 on the same origin, a banner with the
  message above appears on the Login/Register page and the Login
  and Register buttons are disabled, so a tap cannot look like a
  failed registration. Any other failure (server down, network
  error) leaves the buttons enabled, so a transient failure cannot
  lock a user out of a working local server.
- `dashboard/index.html` — new `<div id="backendMsg"></div>` in
  the auth section for that banner (styled by the existing
  `.msg-err` class; no new CSS needed).
- This document.

## What was NOT fixed (and why it cannot be fixed in this round)

- **Registration on the preview still cannot succeed.** That
  needs a real backend: Render + Neon connected (separate
  permission, not given in this round), then either a Vercel
  `/api` proxy rewrite to the Render origin (recommended — needs
  no frontend change) or `window.PDPS_API_BASE` set to the Render
  origin (see `dashboard/api-config.example.js`). Until one of
  those exists, any preview will show the banner above, honestly.
- **No Vercel setting, production deployment, main merge, account
  creation or paid service was changed in this round.** SSO is
  still on (preview protected), production is still main `ce2f9a2`.

## Fresh testable preview URL

Vercel auto-creates a preview for each PR-branch push. The branch
alias is stable:

`https://personal-decision-problem-solver-git-backend-108cf8-rifat-3fe6.vercel.app/`

After this round's push, the newest preview is the deployment for
the new head (see the final report for its id). The alias above
points at the newest preview.

## iPhone test instructions (what to expect now)

1. Open the preview URL in iPhone Safari. (Vercel SSO may ask
   you to sign in with your Vercel account first — that is the
   preview protection, not the app's login. It stays until the
   already-decided SSO change is applied at launch time.)
2. **Expected now:** on the Welcome / Login-Register page you
   should see a red banner: "Backend is not connected yet — this
   preview is frontend-only. No account was created. Register and
   Login will work after the Render backend is connected." The
   Login and Register buttons are greyed out / disabled.
3. That banner IS the pass for this round: it proves the frontend
   correctly detects a missing backend instead of showing a
   cryptic 404.
4. **Not expected yet:** a successful registration on the preview.
   Do not treat the banner as a failure of the Register button —
   the button is deliberately disabled until a backend exists.
5. To test a real registration today, use the fresh Windows ZIP
   (head `78f9c7c`) on a laptop, or a local server — not this
   preview. After the Render backend is connected (separate
   step), re-test on this same preview URL: the banner must
   disappear, Register must create a real account, and Login
   must open the dashboard.
