# Full database backup and restore (Postgres + txt)

This is the procedure for a WHOLE-database backup, not the per-user
decisions backup in `/api/backup` (which covers decisions only — see
`docs/backup-restore-redesign.md`). Never run any step below against
a production database without first reading the whole procedure, and
never point a test at a database holding real user data.

## Postgres (Render + Neon, production path)

### Backup

```bash
# One-off backup. DATABASE_URL comes from the hosting environment
# (Render / Neon dashboard), never from a file committed to git,
# never pasted into a chat, issue or document.
pg_dump "$DATABASE_URL" -F c -f pdps-backup-YYYY-MM-DD.dump

# Plain-SQL alternative (readable, larger, slower to restore):
pg_dump "$DATABASE_URL" -f pdps-backup-YYYY-MM-DD.sql
```

Keep the dump file offline (password manager / encrypted drive), not
in the git repository and not in a public folder. A dump contains
every user's data, including password hashes — treat it like the
database itself.

### Restore (to a NEW, empty database first — never straight into production)

```bash
# 1. Create an empty target database (Neon dashboard, or psql).
# 2. Restore the dump into it:
pg_restore --clean --if-exists -d "$TARGET_DATABASE_URL" pdps-backup-YYYY-MM-DD.dump
# For a plain-SQL dump instead:
psql "$TARGET_DATABASE_URL" -f pdps-backup-YYYY-MM-DD.sql

# 3. Fix the id sequences, so new records do not collide with
#    restored ids (the migration tool does the same after a txt
#    import; see tools/migrate_txt_to_pg.py):
psql "$TARGET_DATABASE_URL" -c "
  SELECT setval('decisions_id_seq', COALESCE((SELECT MAX(id) FROM decisions), 1));
  SELECT setval('tasks_id_seq', COALESCE((SELECT MAX(id) FROM tasks), 1));
  SELECT setval('transactions_id_seq', COALESCE((SELECT MAX(id) FROM transactions), 1));
  SELECT setval('savings_goals_id_seq', COALESCE((SELECT MAX(id) FROM savings_goals), 1));
  SELECT setval('habit_log_id_seq', COALESCE((SELECT MAX(id) FROM habit_log), 1));
  -- users has no id column (username is the primary key), so there
  -- is no users_id_seq to fix. daily_reports and error_logs also
  -- have SERIAL ids; fix theirs the same way if they are restored.
"
```

If a sequence name in the live schema differs, list the sequences
first (`\ds` in psql) and adjust — do not guess and do not run the
restore into production on a guessed name.

### Test plan for a backup/restore (run on a COPY, never on production)

1. `pg_dump` the source database (test database for a rehearsal).
2. Restore into a fresh, empty test database, using the commands above.
3. Compare row counts per table between source and target:
   `users`, `decisions`, `decisions_backup`, `tasks`, `transactions`,
   `savings_goals`, `habit_log`. Every count must match.
4. Point the C++ server at the RESTORED database (test copy only)
   and run `tests/pg_test.py` against it: it must pass, including
   per-user isolation (Bob cannot see Alice's records) and the
   first-user-is-ADMIN check (`/api/users` shows exactly the same
   users and roles as the source).
5. Insert one new decision as each test user against the restored
   database and confirm the new id is greater than every restored id
   (this proves the sequence fix worked; without it, the insert
   fails with a duplicate-key error or silently overwrites).
6. Only after steps 3–5 pass on the copy may the same procedure be
   considered for a real restore, and a real restore must still be
   preceded by a fresh backup of the current production database,
   with the server stopped (or in maintenance) during the restore,
   so no new records are written mid-restore.

Status: this procedure is DOCUMENTED and its commands are the standard
`pg_dump` / `pg_restore` tools. An end-to-end dump → restore → pg_test
rehearsal against a live Render/Neon database was NOT run in this
round, because no Render/Neon account was created or connected (standing
gate). It must be rehearsed on a test database before it is ever
relied on for production. The local `pg_test.py` / `pg_backup_test.py`
runs in this round used a local Postgres test database only.

## txt mode (local / console)

A txt-mode "full backup" is a copy of the whole data directory while
the server / console is STOPPED:

```bash
cp -r data-dir data-dir-backup-YYYY-MM-DD
# Restore: stop the server first, then copy back.
cp -r data-dir-backup-YYYY-MM-DD/. data-dir/
```

Never copy data files while a server is running: the file locks and
the in-memory session state do not protect a mid-write copy, and a
partial copy can corrupt `users.txt` (a truncated user line locks
that user out). After a txt restore, verify with
`tests/console_test.py` and `tests/api_test.py` before serving users
again, and check that `users.txt` still has exactly the expected
users (username + role, no plaintext passwords — new accounts are
PBKDF2 hashes; see `password_hash.h`).
