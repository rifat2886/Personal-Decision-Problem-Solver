# Public Launch Security Checklist — Final Review (2026-11-05)

Status: **REVIEW + PREP ONLY.** Vercel SSO was NOT changed
(still `all_except_custom_domains`), production was NOT changed
(still main `ce2f9a2`), no merge, no account, no deployment, no
paid service. The user's decision for the future SSO change is
recorded here, but it is NOT applied: **Only Preview
Deployments** (production public, previews stay behind the team
login). Applying it needs a separate, explicit go-ahead at launch
time, in the order in section 6.

This checklist is the gate for the public launch. An item marked
FAIL or NOT TESTED in section 1 blocks a "ready to launch" claim
for that item — it does not mean the whole project is broken.

## 1. Final review results (PASS / FAIL / NOT TESTED)

| # | Item | Result | Evidence (this round, head 7b24d7c + fixes below) |
|---|---|---|---|
| 1 | Linux build, 0 warnings | PASS | `make clean && make`: console + cpp_server, 0 warnings. |
| 2 | Console tests | PASS | `console_test.py` 14/14. |
| 3 | API tests, C++ server | PASS | `api_test.py` 36/36. |
| 4 | API tests, Python server | PASS | `api_test.py` 36/36 (via wrapper script). |
| 5 | Per-user isolation, both servers | PASS | `per_user_test.py` 29/29 C++ and 29/29 Python. |
| 6 | Browser tests | PASS (after test fix, see §2) | Original `browser_test.py`: 32/33, only "section auth visible" failed. Root cause was a test timing race, not a product bug: the C++ PBKDF2 register/login each take ~1.85s on this VM, longer than the test's fixed 1500ms wait, so login completed during the section loop and overwrote the auth click. With 3000ms waits in /tmp: 33/33. After the test fix in §2: 33/33 in the repo. |
| 7 | Mobile tests | PASS | `mobile_test.py` 19/19 (360/375/390px + desktop). Live mobile on a real phone / Vercel preview was NOT verified (browser tool has no 390px resize) — see NOT TESTED below. |
| 8 | Auth gate tests, both servers | PASS | `auth_gate_test.py` 30/30 C++ and 30/30 Python. |
| 9 | Postgres tests | PASS | `pg_test.py` 41/41 on a local Postgres 16 test DB (test DB only, no production DB). |
| 10 | Migration txt → Postgres | PASS | `migrate_txt_to_pg.py`: all 9 table counts verified OK (this round's re-run: users 2, others 0 on a small test copy; Phase 1's full test copy also passed 9/9). Source txt untouched, backup copy created first. |
| 11 | Username injection → account takeover (txt mode) | FAIL on 7b24d7c, PASS after fix in §2 | **CRITICAL, verified, not hidden.** Before the fix, a crafted username containing a newline split `users.txt` and overwrote an existing user's line: C++ server via a raw newline in JSON, Python server via a JSON `"\n"` escape. Attacker logged in as the victim with the attacker's password (victim's original password stopped working). Postgres mode was NOT vulnerable to the takeover (username is a column value, not a file line). After the fix in §2, both attacks return 400 and the victim's login still works. **Do NOT launch publicly on 7b24d7c. Launch only on the new head after this fix.** |
| 12 | First ADMIN logic | PASS (with ordering rule, §5) | First registered user = ADMIN, later users = USER, even if the request body contains `"role":"ADMIN"`. No role-change / promote endpoint exists in either server (PATCH/POST to `/api/users` → 404). `/api/users` and `/api/admin` return 403 for non-ADMIN. After the first ADMIN, a second user cannot become ADMIN via the API. |
| 13 | Public registration security (other items) | PASS with known gaps (§4) | Password 8+ with letter+digit, stored as PBKDF2-HMAC-SHA256 hashes, never returned by any API. Login rate limit 5 fails / 300s / username → 429. Sessions are random tokens (C++: random_device + counter; Python: `secrets.token_hex`), 12h TTL, in-memory. All protected APIs 401 without a token (21/21 sweep). Frontend escapes user data (`esc()`), Postgres uses parameters only (no string interpolation), CORS is an exact-origin allowlist (`*` ignored). Gaps that remain: no CAPTCHA, no email verification, no per-IP register rate limit, username enumeration (register "already exists"), no password-reset flow, sessions lost on Render sleep/restart. |
| 14 | Backup / restore, txt mode | FAIL for multi-user use | **Verified data loss.** Alice backed up 1 decision, Bob backed up afterwards and overwrote the single global `decisions_backup.txt`, Alice's restore then returned `restored: 0` and her decision was deleted (restore replaces the user's visible decisions with the backup's visible ones). Single-user backup/restore still works (as in api_test/pg_test). **Do not rely on `/api/backup` + `/api/restore` on a public multi-user site until it is redesigned per-user.** |
| 15 | Backup / restore, Postgres mode | FAIL for multi-user use, PARTIAL for whole-DB backup | Same global-backup flaw, verified in Postgres: Alice backup, Bob backup (which does `DELETE FROM decisions_backup` for all users), Alice restore → `restored: 0`, AliceDecision lost. Whole-DB backup exists as an export (`tools/pg_export_json.py`, verified: users 2, decisions 1 after the test), but **there is no restore tool for that export in the repo** — restoring a Postgres backup means a manual `pg_dump` / `pg_restore` outside the repo, which was NOT tested end-to-end in this round. |
| 16 | Windows cross-compile (MinGW) | PASS | `x86_64-w64-mingw32-g++` (GCC 13, installed via apt in this VM only): console `project.exe` and `cpp_server.exe` (with `-lws2_32`, txt mode, no libpq) both built with 0 warnings, PE32+ x86-64 executables. Code uses `_WIN32` guards for Winsock / file locking / localtime. |
| 17 | Windows 11 real runtime | NOT TESTED | No real Windows 11 machine is available in this VM. Wine is not installed, and Wine would NOT count as a Windows test even if it were. MSYS2 instructions in `RUN.md` / `start-dashboard.bat` match the cross-compile flags, but the `.exe` files were never run on Windows in this round. **The standing merge gate still applies: no merge / no public-launch claim until real Windows 11 runtime is actually tested (by the user on their Windows 11 machine, or by Windows CI once the Workflows permission is fixed).** |
| 18 | Windows Postgres build | NOT TESTED | On MinGW without libpq-dev, `pg_store.h` compiles Postgres support OUT (by design, via `__has_include`), so the Windows build is txt-only. A Windows Postgres build was not attempted and is not needed for production (Render backend is Linux Docker). |
| 19 | Vercel production / SSO settings | PASS (unchanged, verified) | Re-checked read-only after this round's push: `ssoProtection.enabled = true`, `deploymentType = "all_except_custom_domains"`, password protection off, production still `dpl_2xxNZC7Q23gbSLdVEaqNgjumEf1o` from main `ce2f9a2`. No settings change was made. |
| 20 | Secrets in repo | PASS | Grep for `DATABASE_URL=` values, `postgres://` credentials, API keys and passwords in code/docs: only placeholder/example strings (`postgres://user@localhost…`, `<redacted>`) and test-only local DB URLs in test docs, no real secret. `render.yaml` still contains no values. Frontend contains no database string or token. |

## 2. Code changes made in this round (PR branch only)

Only these files were changed, and only on
`backend-testing-dashboard`. No logic was changed to make a test
pass by weakening a check — the one product fix strengthens a
check, and the one test fix waits for a real completion event.

1. **Security fix — username validation (CRITICAL, §1 item 11):**
   `dashboard/cpp_server.cpp`, `dashboard/server.py`,
   `input_validation.cpp` (console). A username must now be a
   single safe token: any whitespace, control character
   (including newline, tab, carriage return) or `'|'` is
   rejected with 400. Normal usernames (letters, digits,
   `_`, `-`, `.`, etc.) are unaffected — all existing test
   users still register and log in. Verified after the fix:
   raw-newline attack (C++) → 400, escaped-newline attack
   (Python) → 400, `'|'` username → 400, victim's original
   login still works, attacker's login as victim → 401,
   and the full test suites in §1 still pass.
2. **Test fix — browser test timing (NOT a product change):**
   `tests/browser_test.py`. The fixed 1500ms waits after
   Register/Login were replaced with waits for the actual
   events (registration message containing "Registered";
   active section becoming "overview"), because the C++
   PBKDF2 step takes ~1.85s per operation on this VM. The
   "login leads to overview" check now verifies the active
   section is actually "overview" instead of checking the
   URL (which never changes). After this fix:
   `browser_test.py` 33/33 in the repo. PBKDF2 iterations
   were NOT reduced — login latency is a performance note,
   not a security change.
3. **This document:** `docs/public-launch-checklist.md`
   (this file).

No Vercel setting, production deployment, main change, account,
or paid service was touched in this round.

## 3. What the code review found (beyond §1)

- **No hardcoded secret, no OAuth, no fake data.** No
  Google/GitHub sign-in code exists anywhere in the frontend
  or servers; the only login is the project's own
  username/password system. No `DATABASE_URL` value, API key,
  or password is committed. Static serving is limited to
  `index.html`, `style.css`, `app.js` in both servers.
- **Per-user isolation is consistent** across C++ server,
  Python server and console (owner = last pipe field in txt,
  owner column in Postgres, NULL = legacy, legacy visible
  only to a sole user, ADMIN sees username/role only).
- **Record fields are sanitised** (`sanitize()` in C++,
  `sanitize()` in Python: `'|'`, newline and carriage return
  become `/` or a space) — the username was the one field
  that was NOT sanitised or validated this way, which is
  exactly how item 11 happened. After §2, every field that
  is written to a delimited file is either sanitised or
  validated.
- **One `main()` only, menus 0–43, no teammate file removed**
  (re-checked from the fresh clone; the file count is 112
  tracked files on the PR branch, including the new docs).
- **Login latency is ~1.85s per register/login on this VM**
  (C++ hand-written PBKDF2, 100k iterations). Python's
  `hashlib` is much faster. This is acceptable for a login,
  but it is why fixed test waits raced, and it means a
  public login page will feel slow on a cold Render instance
  (sleep/wake adds ~1 minute on top of that).

## 4. Public registration security review (what stays risky)

These are NOT hidden, and they are NOT fixed in this round
because each one needs a design decision, not a one-line fix:

- **Open registration spam:** anyone can create unlimited
  accounts. No CAPTCHA, no email verification, no per-IP
  register rate limit. A per-IP limit was deliberately NOT
  added: many legitimate users behind one mobile NAT share a
  public IP, so a strict limit could block real users.
  Mitigation for launch: monitor registrations, keep the
  ADMIN account's password strong and private, and decide
  later whether to add CAPTCHA or email verification.
- **Username enumeration:** register returns "already
  exists" for a taken name, so an attacker can probe which
  usernames exist. Usernames are not secret in this app, so
  this is low severity, but it should not be presented as
  fixed.
- **No password reset / account recovery:** if the owner
  loses the ADMIN password, there is no reset flow (no
  email, no 2FA). The owner must store the ADMIN password
  safely outside the app. There is also no "delete user"
  endpoint, so a compromised account cannot be deleted via
  the API — it must be removed directly in the database by
  the owner.
- **Sessions are in-memory:** after a Render sleep/restart,
  every user must log in again. Data in Postgres survives;
  sessions do not. This is a usability limit, not a data
  leak.
- **HTTPS comes from Vercel/Render, not from the C++ server
  itself.** The C++ server has no TLS. Never expose the
  Render backend URL directly as the public URL without TLS
  — the public URL must be the Vercel HTTPS alias (with the
  `/api` proxy rewrite, or CORS allowlist for direct calls).

## 5. First ADMIN account — the safe method (verified)

**Rule: the first registered user becomes ADMIN, and no API
can promote a later user.** Verified in this round:
registering with `"role":"ADMIN"` in the request body still
gives USER for the second and later users; `/api/users` and
`/api/admin` give 403 for non-ADMIN; PATCH/POST to
`/api/users` give 404; after those attempts, the attacker's
`/api/me` still says USER.

**Safe launch order (must be in this order):**

1. Backend connected (Render + Neon, separate permission —
   NOT done in this round).
2. **Owner registers the first account directly against the
   Render backend URL** (not via the public Vercel URL),
   before the Vercel SSO change is applied. The Render URL
   is not behind Vercel SSO, so the owner can do this while
   the public URL is still protected.
3. Owner verifies, via the Render backend, that
   `/api/users` shows exactly one ADMIN (the owner) and no
   other users.
4. Only then: apply the SSO change (Only Preview
   Deployments, production public, previews protected —
   decision recorded, NOT applied yet), then share the
   public Vercel URL.
5. If step 2 is skipped and the public URL is shared first,
   **the first stranger to register becomes ADMIN** — that
   is the single most dangerous ordering mistake in this
   launch, and it is not fixable via the API afterwards
   (no promote/demote endpoint, no delete-user endpoint).

Alternative safe method, if direct Render access is not
available at launch time: pre-seed the ADMIN account in the
Neon database before sharing (insert with a PBKDF2 hash in
the same `pbkdf2$100000$…` format, role ADMIN), then verify
with `/api/users` before applying the SSO change. Do NOT
pre-seed with a plaintext password — Postgres mode has no
plaintext-upgrade path in the same way txt mode does for
legacy accounts, and a plaintext row would be a different
format from every other account.

## 6. Pre-launch checklist (must all be ticked before sharing the public URL)

- [ ] New PR head after §2 is deployed (not 7b24d7c — that
      head is vulnerable to item 11 in txt mode).
- [ ] Render + Neon backend connected and tested end-to-end
      on the live backend (separate permission, not done).
- [ ] Owner's ADMIN account created FIRST via the Render
      backend URL and verified via `/api/users` (§5).
- [ ] Vercel SSO changed to Only Preview Deployments
      (decision recorded, NOT applied yet — separate
      go-ahead at launch time).
- [ ] Production deployment pointed at the dashboard code
      (merge / promote / production-branch change —
      separate permission, standing merge gates apply).
- [ ] Vercel `/api` proxy rewrite added (or CORS allowlist
      set to exactly the production Vercel origin) — no
      wildcard, no secret in the frontend.
- [ ] Live public test on the production URL, desktop +
      mobile: Welcome visible without Vercel login, Register
      a second user (must be USER, not ADMIN), Login, Logout,
      Refresh with valid session, Invalid session → Login,
      per-user isolation (Alice cannot see Bob's task),
      and a restart/redeploy persistence check (data still
      there after Render sleep/wake).
- [ ] Backup/restore warning given to users, OR backup
      redesigned per-user (§1 items 14–15) — do NOT present
      `/api/backup` + `/api/restore` as safe for multiple
      users until then. Real whole-DB backups must be done
      via Neon/Render (`pg_dump`), not via the API, and a
      restore procedure must be tested before launch.
- [ ] Real Windows 11 runtime tested (user's Windows 11
      machine, or Windows CI) — NOT TESTED in this round
      (§1 item 17). This blocks a merge claim, and it should
      block a "fully tested" public-launch claim too, even
      though production itself runs on Linux.
- [ ] ADMIN password stored safely outside the app (no
      reset flow exists, §4).

## 7. What is NOT ready for a public launch yet

1. **Public launch on head 7b24d7c is NOT safe** (username
   injection, §1 item 11) — fixed only in the new head from
   this round.
2. **Multi-user backup/restore is NOT safe** (§1 items
   14–15) — data loss verified in both txt and Postgres
   modes.
3. **Production URL is NOT ready** — SSO still on, production
   still on main with no dashboard, backend not connected.
   All three need separate permissions and are NOT done.
4. **Real Windows 11 runtime is NOT TESTED** (§1 item 17).
5. **Live mobile on the public URL is NOT TESTED** (local
   mobile tests pass, but the live preview could not be
   resized to 390px by the browser tool).

None of these are hidden, and none of them were fixed by
changing a test or a report — the two fixes in §2 are in the
code and in the test's waiting logic, with before/after
evidence in §1.
