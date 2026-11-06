# Per-user backup / restore redesign (public launch, 2026-11-05)

## The flaw that was fixed

Verified in the 2026-11-05 pre-public-launch review, on PR head
7b24d7c, in BOTH txt and Postgres modes:

1. Alice backed up 1 decision.
2. Bob backed up 1 decision. The single global backup set
   (`decisions_backup.txt`, or `DELETE FROM decisions_backup` with
   no WHERE clause in Postgres) was overwritten with Bob's rows only.
3. Alice restored: `restored: 0`, and Alice's current decision was
   DELETED (restore replaces the caller's visible decisions with the
   backup's visible ones, and the backup no longer held Alice's row).

The console had the same flaw, plus a second bug: `restoreDecisions()`
opened `decisions.txt` for writing (truncating it) BEFORE reading the
current file, so the "kept" list was always empty and a restore wiped
every other user's decisions, not just the caller's.

## The redesign (this round, PR branch only)

The backup format is UNCHANGED, so old backups stay readable:

- txt: `decisions_backup.txt`, one `id|date|type|priority|title|owner`
  line per decision, owner as the last field (legacy rows: no owner).
- Postgres: `decisions_backup` table, same columns, owner NULL for
  legacy rows.

What changed is WHOSE rows a backup or restore touches:

- **Backup** replaces only the caller's own backup rows. Other users'
  backup rows stay verbatim in the same file / table. Hidden legacy
  backup rows stay untouched when 2+ users exist; in the sole-user
  case legacy rows ARE the caller's visible backup, so they are
  replaced with the caller's current visible rows (otherwise every
  backup would duplicate them).
- **Restore** replaces only the caller's current visible decisions
  with the caller's backup rows. Other users' current decisions are
  never touched, and the backup file / table is never deleted by a
  restore, so a restore can be repeated.
- **Restore confirmation, two layers:** the dashboard button shows a
  confirm dialog ("Restore will replace YOUR decisions with YOUR
  backup... Other users are not affected"), AND the API now requires
  `{"confirm": true}` in the request body. A direct API call without
  it gets HTTP 400 and changes nothing. The console already asked
  `Continue? (y/n)` and still does.
- **Restore validation, before writing anything:**
  - If the caller has NO backup rows at all, restore is rejected
    (400, "No backup found for this user. Nothing was changed.")
    instead of deleting the caller's current decisions with an
    empty restore.
  - Each backup row must parse as `id|date|type|priority|title[|owner]`
    with a numeric id, a valid date and a numeric priority. Malformed
    rows are skipped and counted in the response field `"skipped"`,
    never written into `decisions.txt` / `decisions`.
  - A backup row whose id already belongs to a kept (other user's)
    decision is skipped, never overwriting that decision.
  - Response is now `{"restored": N, "skipped": M}`. Existing tests
    check `restored` only, so this is backward compatible.
- **Scope limit (honest):** backup / restore cover DECISIONS only,
  exactly as before. Tasks, transactions, savings goals and habits
  are NOT included in `/api/backup` + `/api/restore`. A full-database
  backup is a separate procedure: see `docs/full-database-backup.md`.

## Files changed

- `dashboard/cpp_server.cpp` — txt + Postgres backup/restore, plus a
  `validDecisionLine()` helper and a `jsonBoolField()` helper.
- `dashboard/server.py` — txt backup/restore (Python has no Postgres
  mode; see `docs/route2-phase1.md`).
- `backup_restore.cpp` — console backup/restore, same per-user rules,
  plus the read-before-truncate fix.
- `dashboard/app.js` — restore button now sends
  `{"confirm": true}` and warns that current decisions not in the
  backup will be lost.
- `tests/backup_test.py` — NEW, 18 checks, both servers (txt mode).
- `tests/pg_backup_test.py` — NEW, 7 checks, Postgres mode, including
  a direct `decisions_backup` table check.
- `tests/pg_test.py` — restore call updated to `{"confirm": true}`
  (test-only change; the old call now correctly gets 400).

## Test results (this round, local only)

- `tests/backup_test.py` C++ server: 18/18 PASS
- `tests/backup_test.py` Python server: 18/18 PASS
- `tests/pg_backup_test.py` C++ Postgres (local test DB only): 7/7 PASS
- Old-format compatibility: a backup file written by the pre-redesign
  code restores only the caller's rows (tested in `backup_test.py`).

## What is still NOT covered

- There is no per-user backup for tasks / transactions / savings /
  habits through the API. Do not tell users that "Backup" saves
  everything; it saves decisions only.
- There is no backup scheduling. Backups happen only when a user
  clicks Backup.
- A user who restores without first backing up their current work
  loses the current decisions that are not in the backup. The
  confirm dialog says this, but there is no automatic pre-restore
  snapshot. Adding one is future work, not in this round.
