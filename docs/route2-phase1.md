# Route 2, Phase 1 — Code Preparation (Vercel + Render Free + Neon Free)

Status: **CODE ONLY. No account was created, no deployment was made,
no Render/Neon connection was opened, no money was spent, no main
merge happened, and no Vercel production setting was changed.**
This document is the preparation record for the step that will
need the user's separate permission: creating the Render and Neon
accounts and connecting them.

## 1. Architecture (target, not yet deployed)

```
Browser (any device / network)
  -> Vercel static frontend (dashboard/, *.vercel.app, HTTPS)
  -> /api/*  ── Vercel proxy rewrite (RECOMMENDED, no CORS needed)
        OR direct API_BASE call (fallback, CORS allowlist)
  -> Render Free Docker service (C++ server, HTTPS via Render)
  -> Neon Free PostgreSQL (DATABASE_URL, TLS, data survives sleep/restart)
```

- Frontend: `dashboard/index.html` + `app.js` + `style.css`, already
  on Vercel preview via `vercel.json` rewrites for static files.
- Backend: `dashboard/cpp_server.cpp` only. The Python server
  (`dashboard/server.py`) is a local fallback and is NOT the
  Render target.
- Storage: PostgreSQL only in production. The C++ server's txt
  mode stays for local use, but **txt mode must never be used on
  Render**: Render Free has no persistent disk, so txt data
  would be lost on restart/redeploy.
- Sessions: in-memory, 12h, per server instance, exactly as in
  txt mode. They are NOT stored in Postgres in Phase 1.

## 2. How Postgres mode is selected (and why it fails fast)

- No `DATABASE_URL` → txt mode, exactly as before. All existing
  tests run in this mode unchanged.
- `DATABASE_URL` set → Postgres mode is **mandatory**. At startup
  the server connects and creates the schema (CREATE TABLE IF
  NOT EXISTS, same tables as `dashboard/schema.sql`). If the
  connection or schema creation fails, the server exits with an
  error and does **not** fall back to txt files. Silent fallback
  would serve a different, empty data set and hide a database
  outage — that is the risk this rule removes.
- The connection string comes only from the environment. It is
  never in source code, never in `render.yaml`, never logged,
  and never printed (the startup log says only "PostgreSQL mode").
- If the binary was built without libpq (for example Windows/
  MinGW without libpq-dev), Postgres mode is compiled out and
  setting `DATABASE_URL` fails fast with a clear message instead
  of silently running txt mode. `make` links `-lpq` only when
  `pg_config` exists; the Dockerfile installs `libpq-dev`.

## 3. Schema — what changed, what did not

`dashboard/schema.sql` mirrors the txt files field for field:

| txt file | Postgres table | Notes |
|---|---|---|
| users.txt | users | username PK, password_hash (same pbkdf2$ format), role |
| decisions.txt | decisions | id SERIAL, record_date, type, priority, title, owner NULL = legacy |
| decisions_backup.txt | decisions_backup | id INT PK (preserves original id) |
| tasks.txt | tasks | id SERIAL, title, urgency, importance, deadline, status, owner |
| transactions.txt | transactions | id SERIAL (internal only, not in API), tx_date, type, category, amount NUMERIC, note, owner |
| savings_goals.txt | savings_goals | name, target, saved NUMERIC, owner; unique index on (name, COALESCE(owner,'')) as a second defence — the server's duplicate check is primary |
| habit_log.txt | habit_log | habit, log_date, owner (no unique constraint, as in txt mode) |
| daily_report.txt | daily_reports | line TEXT, one row per report line |
| error_log.txt | error_logs | line TEXT; server only reads, never writes |

Owner/legacy rules are **not** enforced by the database; they
are enforced by the same server code as txt mode (`ownerVisible`
in the C++ server, `owner_visible` in Python): a NULL-owner
record is visible only when the users table has exactly one
user and that user is the requester; ADMIN never sees other
users' private records. Savings `add` and task PATCH/DELETE
assign a legacy record to the sole user on write, exactly as
txt mode does.

Deliberate deviations from txt mode (API contract unchanged):
- Export (`/api/export`): in Postgres mode the exported file is
  NOT written to disk (Render disk is ephemeral); the API
  response already carries the full `content`, so nothing is
  lost for the user. In txt mode the file write is unchanged.
- Export of an empty database returns an empty report instead
  of the txt-mode "No transactions file found" error, because
  in Postgres mode the store always exists.
- Backup (`/api/backup` + `/api/restore`) keeps the txt-mode
  semantics, including its known flaw: backup overwrites one
  global backup set with the current user's visible decisions.
  That flaw was not redesigned in Phase 1, to avoid changing
  behaviour silently; it is listed under "incomplete work".
- `/api/info` now also returns `"storage":"txt"` or
  `"storage":"postgres"`. All previous fields are unchanged.
- New public endpoint `/api/health` returns
  `{"ok":true,"backend":"C++","storage":"txt"|"postgres"}` with
  no token and no data. It exists for Render's health check
  (which cannot present a login token).

## 4. Frontend → backend wiring (two paths, one recommended)

**Recommended: Vercel /api proxy rewrite.** Add this to the
Vercel project's rewrite rules at deployment time (NOT in
Phase 1, because the Render URL does not exist yet):

```json
{ "source": "/api/(.*)", "destination": "https://<render-service>.onrender.com/api/$1" }
```

With the proxy, the frontend keeps calling same-origin `/api/...`,
no CORS header is needed, and no frontend code change is
required. The existing `vercel.json` (static rewrites only) is
left unchanged in Phase 1.

**Fallback: direct Render call + CORS.** `dashboard/app.js`
now supports `window.PDPS_API_BASE` (see
`dashboard/api-config.example.js`). Set it to the Render origin
and set the server's `CORS_ORIGINS` to the exact Vercel origin,
for example:

```
CORS_ORIGINS=https://personal-decision-problem-solver.vercel.app
```

CORS rules in both servers: exact origins only, comma-separated,
from `CORS_ORIGINS`; `*` is ignored with a startup warning;
preflight `OPTIONS /api/*` returns 204 with
`Access-Control-Allow-Methods: GET, POST, PATCH, DELETE, OPTIONS`
and `Access-Control-Allow-Headers: Authorization, Content-Type`;
API responses carry `Access-Control-Allow-Origin` only for an
allowed origin. Without `CORS_ORIGINS`, no CORS header is sent.

## 5. Migration and rollback (txt → Postgres)

Tool: `tools/migrate_txt_to_pg.py` (Python, needs psycopg2
locally for a test migration; the C++ server itself needs only
libpq). It is **read-only on the source**:

1. Parse the txt files from `--data-dir` (use a TEST COPY, never
   the live data directory, for a trial run; `--dry-run` parses
   and counts with no writes at all).
2. Copy the whole source directory to a backup directory
   (`--backup-dir`, default `<data-dir>.pre-pg-migration-<date>`).
   The original txt files are never modified or deleted.
3. Apply `dashboard/schema.sql`, refuse if target tables are
   non-empty (unless `--allow-nonempty`), and refuse on any
   username conflict — merging two user sets is not supported.
4. Insert all rows, preserving decision/task ids, with legacy
   owner as NULL, then set the `decisions_id_seq` and
   `tasks_id_seq` sequences to `MAX(id)`.
5. Re-read counts from Postgres and compare with txt counts;
   any mismatch aborts with an error.

**Rollback (before going live, or if Postgres mode fails):**
- Stop the Postgres-mode server.
- Restore the txt backup copy (the `.pre-pg-migration-*`
  directory) as the data directory.
- Start the server **without** `DATABASE_URL` (txt mode).
- The Postgres tables can be dropped and re-migrated; no txt
  data is lost by a failed migration, because the source was
  never written to.

**Backup in Postgres mode:** `tools/pg_export_json.py --out
pg-backup.json` exports all tables to JSON (needs DATABASE_URL).
It is a portable backup, not a replacement for Neon's own
backups (Neon free includes point-in-time recovery limits that
must be re-checked at signup — see section 7). Treat the export
file as sensitive: it contains password hashes.

## 6. Render deployment preparation (not deployed)

- `Dockerfile`: Debian bookworm-slim + `g++` + `libpq-dev`,
  builds `cpp_server` with `-lpq`, runs
  `cpp_server --host 0.0.0.0 --port $PORT`. Render sets `PORT`
  and terminates TLS, so the container serves plain HTTP behind
  Render's HTTPS. No secret is in the image.
- `render.yaml`: blueprint template only. It lists NO values
  for `DATABASE_URL` or `CORS_ORIGINS` (`sync: false`); those
  must be set as secrets in the Render dashboard at setup time.
  Applying this file would create a service, so it is NOT
  applied in Phase 1.
- Health check: `/api/health` (public, no data).

## 7. Free-tier limitations — read before promising 24/7

These were the published free-tier facts at plan time and must
be re-verified at signup, because free tiers change:

- **Render Free web service sleeps after 15 minutes idle.**
  The first request after sleep takes ~1 minute to wake the
  service. It is not instant 24/7. 750 free hours/month covers
  one service, but sleep still applies.
- **Render Free has no persistent disk.** Postgres mode is
  mandatory; txt mode on Render loses data on restart.
- **Neon Free: data is not deleted by inactivity** (compute
  scales to zero after 5 minutes idle and resumes on the next
  connection, which adds a few seconds to the first query).
  Limits to watch: storage ~0.5–1 GB/project (sources differ),
  compute ~100 CU-hours/project/month. Exceeding the compute
  cap suspends compute until the next month (data survives,
  site is down); exceeding storage makes writes fail.
- **Sessions do not survive sleep/restart** (in-memory). After
  a wake or a redeploy, every user must log in again. Data in
  Postgres is unaffected.
- **Console vs online data diverge.** The laptop console app
  still reads txt files locally; online data lives in Postgres.
  There is no sync between them in Phase 1. The user has not
  explicitly confirmed or rejected this assumption (see
  "incomplete work").
- **No password reset, no email, no 2FA** in this codebase.
  That was already true in txt mode and is unchanged here.
- **No HTTPS in the C++ server itself.** HTTPS comes from
  Vercel (frontend) and Render (backend TLS termination) in
  production; the server must never be exposed directly to the
  internet without that TLS layer.

## 8. Python server compatibility — what was checked

- The Python server (`dashboard/server.py`) stays txt-only in
  Phase 1. It is the local fallback, not the Render target, so
  duplicating a full Postgres mode in Python would double the
  surface for bugs without changing production behaviour.
- Compatibility was checked, not assumed: the Postgres schema
  uses the same field names, types, and owner/legacy rules as
  the Python server's txt parsing, and `dashboard/pg_store.py`
  provides a Python reader for the same tables (users,
  decisions, tasks, transactions, savings, habits) with the
  same `owner_visible` rule. The migration tool and the
  Postgres test suite use that reader to cross-check the C++
  server's Postgres output.
- The Python server gained the same CORS allowlist and `PORT`
  environment support as the C++ server, plus the public
  `/api/health` endpoint, so it can still be used for local
  CORS testing if needed. Its txt behaviour is unchanged and
  all txt tests still pass (see tests below).
- Full Python Postgres mode (server.py reading/writing
  Postgres) is **incomplete work** (see section 9). If the
  Python server is ever used as a production backend, that
  work must be built and tested first; do not point a
  production frontend at the Python server in Postgres mode
  today, because it will read txt files, not Postgres.

## 9. Incomplete work (honest list)

1. **Render account, Neon account, and any deployment or
   connection** — not done, needs the user's separate
   permission (and, for Neon, the connection string must be
   entered only on Neon's/Render's own secure pages, never in
   chat).
2. **Vercel /api proxy rewrite** — not added, because the
   Render URL does not exist yet. `vercel.json` is unchanged.
3. **Full Python Postgres mode** — not built (see section 8).
4. **Session persistence across sleep/restart** — sessions
   stay in-memory; users re-login after a wake (by design in
   Phase 1, documented in section 7).
5. **Backup/restore redesign** — DONE (2026-11-05, after
   Phase 1): the per-user redesign is implemented — a backup
   replaces only the caller's own rows and preserves other
   users' rows and hidden legacy rows; restore requires
   confirmation. The global backup-set flaw described in
   Phase 1 no longer exists.
6. **Console ↔ online data sync** — not built; console stays
   local txt, online stays Postgres (section 7).
7. **Live Render/Neon end-to-end test** — impossible in Phase 1
   without accounts; only local Postgres testing was done
   (see section 10). Production-ready testing on the actual
   deployment is still required before calling Route 2 done.
8. **Windows build with libpq** — the code compiles Postgres
   support out when libpq is missing (so Windows txt builds
   still work), but a Windows Postgres build was not tested
   (no Windows machine in this environment). Windows CI itself
   is NOT blocked: CI runs #20/#21 (2026-11-09) passed on
   Linux + Windows via browser-triggered workflow_dispatch.
   The GitHub App still lacks the Workflows permission, so
   workflow files are updated through the browser upload flow.

## 10. Tests run in Phase 1 (local only, 2026-11-05)

- Txt mode regressions (no DATABASE_URL, after all Phase 1
  changes): console 14/14, API 36/36 on the C++ server and
  36/36 on the Python server, per-user 29/29 on both servers,
  browser 33/33, mobile 19/19, auth_gate 30/30 on both servers.
  `make` builds clean (0 warnings) with libpq.
- Postgres mode (local PostgreSQL 16, DATABASE_URL pointing
  at a test database only): `tests/pg_test.py` **51/51 PASS**
  — schema creation, register/login, task/decision/transaction/
  savings/habit CRUD, per-user isolation (Alice/Bob, PATCH/
  DELETE 404), legacy hidden with 2 users / visible to sole
  user, backup/restore, export txt+csv, daily-summary,
  error-log, CORS allowed/disallowed/preflight, 401 sweep,
  and fail-fast on a bad DATABASE_URL.
- Migration: `tools/migrate_txt_to_pg.py` on a test copy
  (2 users, 2 decisions including 1 legacy, 1 task, 1
  transaction, 1 savings goal, 1 habit, 2 backup rows, 1 daily
  report, 1 error line) — all 9 table counts verified OK after
  migration, source txt files untouched, backup copy matches
  the source, and a post-migration decision got id 3 (after
  migrated max id 2), proving the sequence fix works.
- One bug was found and fixed by these tests (not hidden):
  the Makefile initially linked `pg_config --libs`, which
  lists static libraries that are not installed, and it
  initially lacked the `-I/usr/include/postgresql` flag, so
  Postgres support was silently compiled out. Both are fixed
  in the Makefile and Dockerfile (see section 2).
