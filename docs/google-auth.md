# Google Sign-In — Personal Decision & Problem Solver

Google Sign-In (Phase 3, 2026-11-11) adds a **"Continue with Google"**
button to the Login and Register cards, next to the existing
username/password login. Both sign-in methods stay available; nothing
about password login changes.

## How it works (the short version)

1. The user clicks **Continue with Google**. Google's Identity
   Services (GIS) button returns an **ID token** (a JWT) to the page.
2. The page POSTs that token to `POST /api/auth/google`.
3. The **C++ backend** verifies the token locally against Google's
   public keys (JWKS): RS256 signature, issuer, audience, expiry,
   and `email_verified`. It never calls Google's `tokeninfo` endpoint
   (development only) and never trusts a plain user ID from the
   client.
4. The backend finds the account by the Google **`sub`** (the stable
   account ID) or creates it on first use, and returns a normal app
   session — the same `{username, role, token}` shape as password
   login, same 12-hour in-memory session.

There is **no client secret** anywhere in this flow. The GIS button
flow needs only the OAuth **Client ID**, which is a public identifier
(it is embedded in the page by design). Never create, copy, or store
a client secret for this project.

## Setup (done once, by the owner, in their own browser)

Google Cloud Console (free, no billing, no card):

1. Create a project (no API needs enabling).
2. OAuth consent screen: **External**, app name, support email,
   scopes `openid`, `email`, `profile`. Leave the app in **Testing**
   mode (up to 100 test users — add your own account, and the
   teacher's if the teacher will sign in).
3. Create an OAuth 2.0 Client ID of type **Web application** with:
   - **Authorized JavaScript origins:** `http://127.0.0.1:8000`
   - **Authorized redirect URIs:** NONE (the GIS flow uses none).
   Do NOT add the Vercel URL — it has no backend.
4. Copy the **Client ID** only and share it with the developer
   (it is public and safe to share). Never share the Client Secret —
   this flow never uses it.

On the machine that runs the server, set the environment variable
in the same PowerShell window before `start-dashboard.bat`
(same pattern as `GEMINI_API_KEY`):

```powershell
$env:GOOGLE_CLIENT_ID = "your-client-id"
.\start-dashboard.bat
```

Without `GOOGLE_CLIENT_ID` the Google buttons are hidden and
`POST /api/auth/google` answers 503 — password login is unaffected.

## Environment variables

| Variable | Meaning | Default |
|---|---|---|
| `GOOGLE_CLIENT_ID` | OAuth Client ID (public). Required for Google sign-in. | unset (sign-in disabled) |
| `GOOGLE_JWKS_URL` | JWKS endpoint for the public keys. | `https://www.googleapis.com/oauth2/v3/certs` (only used in tests to point at a mock JWKS server) |
| `GOOGLE_SIGNIN_ENABLED` | Set to `0` to disable Google sign-in even when a client ID is set. | enabled whenever `GOOGLE_CLIENT_ID` is set |

## Endpoints (C++ server only)

### `GET /api/auth/google/config` (public)

What the frontend needs to render the button. Nothing secret is
returned.

```json
{"clientId": "123456789-abc.apps.googleusercontent.com", "enabled": true, "available": true}
```

- `clientId` — the configured client ID, or `""` when unset.
- `enabled` — false when no client ID is set or `GOOGLE_SIGNIN_ENABLED=0`.
- `available` — false when the server was built without OpenSSL
  (the stub build answers 503 for sign-in; see "Build" below).

### `POST /api/auth/google` (public)

```json
{"credential": "<Google ID token>"}
```

- Success: **200** `{"username": "alice", "role": "USER", "token": "<session token>"}`.
- Missing/empty credential → 400.
- More than 20 attempts from one IP in 60 s → 429.
- Google sign-in not compiled in, or no client ID → 503
  `"Google sign-in unavailable."`
- JWKS cannot be fetched → 503 `"Google sign-in is temporarily unavailable."`
- Bad token (wrong signature, expired, wrong audience/issuer,
  `email_verified` false, `alg` not RS256, unknown key) → 401
  `"Invalid Google sign-in."`
- First use creates the account: the username comes from the email
  local part (lowercased, sanitized); on collision `"-"` + the
  first 6 digits of the `sub`, then `"-2"`, `"-3"`, … The first
  account ever created is `ADMIN`, like password registration.
- If another account already holds the token's email, creation is
  refused with **409** — email is never proof of ownership
  (password accounts never verified their email), so a Google
  account must never take over that email's identity. The owner
  signs in with their password and links Google instead (below).

### `POST /api/auth/google/link` (logged in)

Links the Google account in the verified token to the currently
logged-in account. Body: `{"credential": "<ID token>"}`.

- Success: **200** `{"linked": true}`. Linking the same Google
  account again is a no-op success.
- The token's `sub` already linked to another account → 409.
- The token's email belongs to another account → 409.
- This account already linked to a different Google account → 409.
- **There is no auto-link on email, ever.** Linking only happens
  through this endpoint, while logged in.

### `POST /api/auth/google/unlink` (logged in)

Removes the Google link from the logged-in account. No body needed.

- Success: **200** `{"unlinked": true}`.
- No Google account linked → 400.
- **Last-method guard:** an account whose only sign-in method is
  Google cannot unlink it → **409** `"Cannot unlink Google
  sign-in: it is your only sign-in method. Set a password first."`
- The verified email stays on the account (so nobody else can
  create an account with it), and the owner can re-link later by
  signing in with their password.

### `POST /api/auth/set-password` (logged in)

Sets a password on an account that signs in with Google, so it can
also sign in with a password. Body:

```json
{"password": "NewPass123", "confirm_password": "NewPass123"}
```

- Same password rule as registration (8+ characters, a letter and
  a digit); `confirm_password`, when supplied, must match.
- Allowed only with a **Google session younger than 15 minutes**,
  or with a fresh ID token for the account's own linked Google
  sub (pass it as `credential` in the same body). Otherwise 401
  `"Sign in with Google again to set a password."`
- An account with no linked Google account gets 400 — password
  users change their password with `/api/change-password` instead.
- Success: **200** `{"ok": true}`. The account becomes
  `auth_provider = "both"` (it can sign in either way).

### Python server

`dashboard/server.py` returns **501** `{"error": "Google sign-in
requires the C++ server"}` for `/api/auth/google*` and
`/api/auth/set-password` (after the login check, like the AI 501 —
so an unauthenticated call still gets 401). Google sign-in needs
the C++ server.

## Data model

### Postgres

The `users` table gains four columns (migration:
`tools/migrate_add_google_columns.sql`, rollback:
`tools/migrate_add_google_columns_rollback.sql` — additive only,
existing rows are untouched, `auth_provider` defaults to
`'password'`):

| Column | Meaning |
|---|---|
| `password_hash` | Now nullable. **NULL for Google-only accounts** — no random password is ever generated or stored. |
| `email` | Verified email from the token (NULL for password-only accounts). Partial unique index (`WHERE email IS NOT NULL`). |
| `google_sub` | Google's stable account ID. Partial unique index (`WHERE google_sub IS NOT NULL`). |
| `auth_provider` | `'password'`, `'google'`, or `'both'`. |
| `display_name` | Display name from the token (may be empty). |

A Google-only account cannot log in with any password: the
empty-password guard at the top of `verifyPassword`
(`password_hash.h`) and `verify_password` (`server.py`) refuses
an empty or `"!"` stored credential before any comparison.

### Txt mode

- Google-only users are stored in `users.txt` as
  `username! ROLE` (two fields). The `"!"` is the same sentinel
  the guard refuses.
- Linked accounts are stored in `google_links.txt` as
  `username|google_sub|email|display_name`.
- Unlink keeps the email (the line becomes
  `username||email|display_name`), so the email still blocks
  anyone else from claiming it.

## Build

`dashboard/google_auth.h` / `dashboard/google_auth.cpp` verify
tokens with OpenSSL (`EVP_DigestVerify`, `-lcrypto`) and fetch the
JWKS with libcurl. The Makefile detects OpenSSL with
`pkg-config openssl` and links `-lcrypto` when present; when
absent it defines `PDPS_NO_OPENSSL` and the module is a stub
(`available()` false, sign-in answers 503) — the same opt-in
pattern as the Gemini (`PDPS_NO_CURL`) and Postgres
(`PDPS_NO_LIBPQ`) stubs, so Windows/MinGW builds keep working
without a new dependency. The Dockerfile installs `libssl-dev`;
`start-dashboard.bat` detects OpenSSL the same way it detects
curl. Windows CI builds the stub (no OpenSSL package there).

## Security notes

- Identity comes **only** from the verified ID token. `sub` is
  the stable ID; email is never used to link accounts.
- The token is never stored and never logged. Only `sub`, `email`
  and the display name are stored.
- The JWKS is cached by `kid` and refreshed when a token arrives
  with an unknown `kid`, or at most once an hour.
- `POST /api/auth/google` is rate-limited per client IP
  (20 attempts / 60 s → 429).
- Sessions after Google sign-in are the same in-memory 12-hour
  sessions as password login, and die on server restart.
- The Neon migration is applied separately by the owner (Neon SQL
  editor) — never by the server, and never by guessing a
  connection string. Before applying it, the count of users with
  NULL or empty `password_hash` must be 0 (no Google-only account
  can exist before the migration, because the guard lands first).

## Troubleshooting

- **Google button does not appear:** `GOOGLE_CLIENT_ID` is not
  set in the server's own environment (same-window rule as
  `GEMINI_API_KEY`), or the GIS script did not load (no network),
  or the server is the Python fallback (501 — use the C++ server).
  Check `GET /api/auth/google/config` in the browser.
- **"Google sign-in unavailable." (503):** the server was built
  without OpenSSL (check the build WARNINGs; rebuild after
  installing `libssl-dev` / the MSYS2 openssl package and
  deleting `cpp_server.exe` first), or no client ID is set.
- **"Invalid Google sign-in." (401):** the token is expired,
  signed for a different client ID, or from a different issuer;
  or the Google account's email is not verified.
- **409 "An account with this email already exists":** sign in
  with the password for that account, then link Google from the
  profile (link endpoint). Do not create a second account.
- **409 "Cannot unlink … only sign-in method":** set a password
  first (`POST /api/auth/set-password` within 15 minutes of a
  Google sign-in), then unlink.
- **401 "Sign in with Google again to set a password":** the
  Google session is older than 15 minutes — sign in with Google
  again, or pass a fresh `credential` in the set-password body.
