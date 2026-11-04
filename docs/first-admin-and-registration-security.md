# First ADMIN security and public registration security

This document is a REVIEW and a PLAN. It deliberately creates NO new
endpoint: there is no promote / demote / delete-user / password-reset
endpoint in the code, and none was added in this round, because each
of those would be a new account-takeover surface on a public site.
Any future endpoint of that kind needs its own separate approval and
its own security review.

## Priority 2 — First ADMIN: risk review

Current rule, verified in code (both servers and the console):
the FIRST user ever registered in an empty database / `users.txt`
becomes ADMIN; every later registration is USER, no matter what
`role` value the request body claims (the server computes the role
and ignores the client field). There is no endpoint that changes a
role afterwards.

Risks, in order of severity:

1. **Race on a fresh public database (HIGH, but preventable by
   launch order).** If the public URL is shared before the owner
   registers, the first stranger to register becomes ADMIN. That
   stranger can list all usernames and roles (`/api/users`), but —
   verified — cannot read any other user's private records, cannot
   change roles, and cannot delete users, because no such endpoint
   exists. The damage is therefore limited, but the owner would
   have lost the only ADMIN seat, and the only fix is the
   database-owner procedure in "Recovery" below.
2. **No recovery through the API (by design).** If the ADMIN
   password is lost, there is no "forgot password" flow and no
   second ADMIN can be created through the API. This is a lockout
   risk, not a takeover risk — and it is the price of having no
   reset endpoint (see below).
3. **ADMIN is also a regular data account.** The ADMIN's own
   decisions, tasks and budgets are per-user isolated like anyone
   else's; ADMIN does NOT get a back door into other users' data.
   That is intentional and must not be "fixed".
4. **Username enumeration (LOW).** Registering an existing username
   returns "already exists", and a wrong login returns "Invalid
   username or password" (the same message for a wrong username and
   a wrong password). Usernames are not secret — they appear in the
   ADMIN user list — so this is accepted, not hidden.

## Safe owner-ADMIN procedure (current code, no new feature)

This is the ONLY approved way to create the owner ADMIN before
public access, and the order matters:

1. Connect the Render backend and Neon database first (separate
   approval; not done in this round).
2. BEFORE changing any Vercel SSO setting and BEFORE sharing any
   public URL, the owner registers directly against the Render
   backend URL (not through the public site). Use a strong password
   (at least 8 characters, letter + digit — the server enforces
   this minimum; use much more than the minimum) and store it in a
   password manager immediately.
3. As that ADMIN, call `GET /api/users` and confirm it shows
   EXACTLY ONE user, with role ADMIN, and that `GET /api/me`
   returns the owner's username and ADMIN.
4. Only then apply the Vercel SSO change (preview-only, already
   decided, not yet applied) and share the public URL.
5. After sharing, check `/api/users` again: the second registered
   user must be USER, never ADMIN. If it is not, stop sharing the
   URL and use the database-owner recovery below.

### If a stranger already became ADMIN (recovery, database owner only)

1. Back up the database first (`pg_dump`, see
   `docs/full-database-backup.md`). Never edit a live database
   without a backup.
2. The database owner (Neon dashboard / `psql`, never the public
   API) runs, for the owner's username only:
   `UPDATE users SET role = 'ADMIN' WHERE username = 'owner-username';`
   and, if the stranger must lose ADMIN:
   `UPDATE users SET role = 'USER' WHERE username = 'stranger-username';`
3. Verify with `SELECT username, role FROM users;` and by logging in
   as the owner and calling `/api/users`.
4. Do NOT build a public promote endpoint to "fix" this faster: an
   endpoint that changes roles is exactly the endpoint an attacker
   would target, and it would need its own authentication, audit
   log and rate limiting before it could be considered safe.

### Future option (PROPOSAL ONLY, not implemented)

A seed ADMIN via environment variables on the hosting platform
(e.g. Render sets `PDPS_SEED_ADMIN` only on first deploy, the server
creates that ADMIN only when the users table is completely empty,
and the variable is then removed) would remove the race in step 1.
It was NOT implemented in this round because it introduces secret
handling in the hosting environment and a new code path that needs
its own review. If the owner wants it, it needs a separate approval
naming that exact mechanism.

## ADMIN password recovery (safe plan, no reset endpoint)

Why there is no "forgot password" endpoint: a reset flow without
email verification would let anyone reset anyone's password, which
is account takeover. Email verification would need an email service
(see Priority 3), which is a paid / third-party dependency the owner
has forbidden. So recovery is deliberately database-owner-only:

1. Back up first (`pg_dump` for Postgres, copy of `users.txt` for
   txt mode). Never edit without a backup.
2. Generate a new PBKDF2 hash OFFLINE, on the owner's own machine,
   in exactly the stored format
   `pbkdf2$100000$<32 hex salt>$<64 hex hash>` (PBKDF2-HMAC-SHA256,
   100000 iterations — the same format as `password_hash.h` and
   Python's `hashlib.pbkdf2_hmac`; a temporary password is generated
   this way, never stored as plaintext in the database).
3. Database owner only, update ONLY the owner's row:
   `UPDATE users SET password_hash = '<new hash>' WHERE username = 'owner-username';`
   (txt mode: replace only the second field of the owner's line in
   `users.txt`, keeping username and role untouched.)
4. Log in with the temporary password, then IMMEDIATELY change it
   through the normal `POST /api/change-password` flow (which
   requires a valid login) to a new strong password, and store that
   in a password manager. Delete the temporary password from
   history / notes.
5. Prevention, which is cheaper than recovery: the owner password
   lives in a password manager from day one, and the database is
   backed up regularly (see `docs/full-database-backup.md`).

## Priority 3 — Public registration: spam review

Existing controls, verified in code (no new control was added in
this round, for the reasons below):

- Password minimum: 8 characters, at least one letter and one digit
  (server-enforced on register; the same rule applies in the
  console). This stops empty / trivial passwords, not spam.
- Login rate limit: 5 failed logins per username per 300 seconds
  → HTTP 429. This slows password guessing; it is per-username, not
  per-IP, so it cannot be used to lock out a shared-IP user by
  guessing their username.
- PBKDF2 cost: each register / login in the C++ server takes
  ~1.85 s of CPU on the test VM (measured 2026-11-05). That is an
  accidental but real brake on mass registration: a single core can
  do at most ~2000 registrations per hour, and each one costs the
  attacker the same CPU time. Do NOT reduce the iteration count to
  "speed up" login; that would weaken both passwords and this brake.
- Username validation: no whitespace, control characters or `|`
  (fixed 2026-11-05, account-takeover fix). This stops file-format
  injection, not spam.
- No email, no CAPTCHA, no per-IP register limit (see below).

### Options reviewed and why each was NOT adopted in this round

- **CAPTCHA — rejected.** Every widely used CAPTCHA is a third-party
  service with an account, a key, and (for most) a paid tier or a
  usage limit; the owner forbade paid dependencies and new accounts
  in this round. A home-made "type the number" check is trivially
  bypassed by a script and adds friction for real users without
  stopping spam.
- **Email verification — rejected for the same reason.** There is
  no email field in the user model and no email service connected;
  adding one means an SMTP / email-API account, secrets in the
  hosting environment, and deliverability work. It also does not
  stop spam by itself (free email accounts are free).
- **Per-IP registration limit — NOT adopted as a hard limit, and
  this is the shared-IP point the owner asked about.** Mobile
  networks, university / office Wi-Fi and many ISPs put hundreds or
  thousands of real users behind a small number of public IPs
  (carrier-grade NAT). A hard limit such as "5 registrations per IP
  per day" would block the 6th real student on the same campus
  Wi-Fi while barely slowing an attacker, who can rotate IPs, use
  a VPN, or register slowly. A per-IP limit is also easy to abuse
  in reverse: an attacker who knows a victim's shared IP could
  deliberately exhaust that IP's quota and lock real users out.
- **Global registration counting + ADMIN review — RECOMMENDED,
  manual, no code change.** The ADMIN can already list users
  (`/api/users`) and watch for a sudden burst of new usernames.
  If spam appears, the response is: stop sharing the URL, clean the
  spam accounts at the database level (backup first, delete only
  rows that are provably spam and have no real data), and only then
  consider a code change.

### Future option (PROPOSAL ONLY, not implemented)

If spam actually appears, the least harmful code change is a HIGH,
soft per-IP threshold — for example, more than 30 registrations
from one IP in one hour returns 429 with a Retry-After header, and
the threshold is deliberately far above what a shared-IP group of
real users would hit in an hour — plus a hosting-level
registration-pause switch (an environment variable that makes
`/api/register` return 503 while existing logins keep working).
Both need separate approval and a test that a shared-IP group is
not blocked, because the threshold and the pause switch are exactly
the kind of change that can lock out real users if set wrong.
Neither was implemented in this round, and neither should be
presented as already protecting the site.
