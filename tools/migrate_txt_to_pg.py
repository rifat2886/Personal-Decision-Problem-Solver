#!/usr/bin/env python3
"""Migrate PDPS txt data into PostgreSQL (Route 2, Phase 1).

Safety rules, by design:
- The source txt files are ONLY READ, never modified or deleted.
- Before any insert, the whole source data directory is copied to
  a backup directory (default: <data-dir>.pre-pg-migration-<date>,
  or --backup-dir). That copy is the rollback source.
- The target database must be empty for the tables being migrated
  (or --allow-nonempty, which still refuses if a username already
  exists — merging two user sets is not supported, because owner
  identity would become ambiguous).
- After inserting, counts are re-read from Postgres and compared
  with the txt counts. Any mismatch aborts with an error; the
  txt files are still untouched, and the Postgres tables can be
  dropped and re-migrated (see docs/route2-phase1.md, rollback).
- No secret is read from anywhere except DATABASE_URL, which is
  passed to psycopg2 and never printed or logged.

Usage (local/staging test only — no Render/Neon account is used
by this tool; DATABASE_URL must already point at a database you
control, for example a local Postgres):
    python3 tools/migrate_txt_to_pg.py --data-dir /path/to/test-copy \
        --backup-dir /path/to/backup
    # dry run, no writes at all:
    python3 tools/migrate_txt_to_pg.py --data-dir /path/to/test-copy --dry-run

Files migrated: users.txt, decisions.txt, tasks.txt,
transactions.txt, savings_goals.txt, habit_log.txt,
decisions_backup.txt, daily_report.txt, error_log.txt.
Legacy records (no owner field) are inserted with owner NULL,
so the legacy visibility rule is preserved exactly.
IDs from decisions.txt/tasks.txt are preserved, and the SERIAL
sequences are set to MAX(id) afterwards, so the next insert
does not collide with a migrated id.
"""

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard"))
import pg_store  # noqa: E402


def read_lines(data_dir, name):
    path = os.path.join(data_dir, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip()]


def parse_users(lines):
    users = []
    for ln in lines:
        parts = ln.split()
        if len(parts) >= 3:
            users.append((parts[0], parts[1], parts[2]))
    return users


def parse_decisions(lines):
    out = []
    for ln in lines:
        p = ln.split("|")
        if len(p) < 5:
            continue
        try:
            out.append((int(p[0]), p[1], p[2], int(p[3]), p[4], p[5] if len(p) >= 6 else None))
        except ValueError:
            continue
    return out


def parse_tasks(lines):
    out = []
    for ln in lines:
        p = ln.split("|")
        if len(p) < 6:
            continue
        try:
            out.append((int(p[0]), p[1], int(p[2]), int(p[3]), p[4], p[5], p[6] if len(p) >= 7 else None))
        except ValueError:
            continue
    return out


def parse_txs(lines):
    out = []
    for ln in lines:
        p = ln.split("|")
        if len(p) < 5:
            continue
        try:
            out.append((p[0], p[1], p[2], float(p[3]), p[4], p[5] if len(p) >= 6 else None))
        except ValueError:
            continue
    return out


def parse_goals(lines):
    out = []
    for ln in lines:
        p = ln.split("|")
        if len(p) < 3:
            continue
        try:
            out.append((p[0], float(p[1]), float(p[2]), p[3] if len(p) >= 4 else None))
        except ValueError:
            continue
    return out


def parse_habits(lines):
    out = []
    for ln in lines:
        p = ln.split("|")
        if len(p) >= 2:
            out.append((p[0], p[1], p[2] if len(p) >= 3 else None))
    return out


def main():
    ap = argparse.ArgumentParser(description="Migrate PDPS txt data to PostgreSQL (read-only source).")
    ap.add_argument("--data-dir", required=True, help="Directory holding the txt files (use a test copy).")
    ap.add_argument("--backup-dir", default=None, help="Backup copy destination (default: <data-dir>.pre-pg-migration-YYYYMMDD).")
    ap.add_argument("--dry-run", action="store_true", help="Parse and count only; do not connect or write.")
    ap.add_argument("--allow-nonempty", action="store_true", help="Allow non-empty tables (still refuses on username conflict).")
    args = ap.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    if not os.path.isdir(data_dir):
        print(f"ERROR: data directory not found: {data_dir}", file=sys.stderr)
        return 2

    users = parse_users(read_lines(data_dir, "users.txt"))
    decisions = parse_decisions(read_lines(data_dir, "decisions.txt"))
    tasks = parse_tasks(read_lines(data_dir, "tasks.txt"))
    txs = parse_txs(read_lines(data_dir, "transactions.txt"))
    goals = parse_goals(read_lines(data_dir, "savings_goals.txt"))
    habits = parse_habits(read_lines(data_dir, "habit_log.txt"))
    backup = parse_decisions(read_lines(data_dir, "decisions_backup.txt"))
    daily = read_lines(data_dir, "daily_report.txt")
    errors = read_lines(data_dir, "error_log.txt")
    counts = {"users": len(users), "decisions": len(decisions), "tasks": len(tasks),
              "transactions": len(txs), "savings_goals": len(goals), "habit_log": len(habits),
              "decisions_backup": len(backup), "daily_reports": len(daily), "error_logs": len(errors)}
    print("Parsed txt counts:", counts)
    if args.dry_run:
        print("Dry run: no backup, no database writes.")
        return 0

    import datetime
    backup_dir = args.backup_dir or (data_dir + ".pre-pg-migration-" + datetime.date.today().isoformat())
    if os.path.exists(backup_dir):
        print(f"ERROR: backup directory already exists, refusing to overwrite: {backup_dir}", file=sys.stderr)
        return 2
    shutil.copytree(data_dir, backup_dir)
    print(f"Backup copy created (source txt files untouched): {backup_dir}")

    conn = pg_store.connect()
    try:
        with conn.cursor() as cur:
            # Schema: apply dashboard/schema.sql if it is available.
            schema = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard", "schema.sql")
            if os.path.exists(schema):
                with open(schema, encoding="utf-8") as f:
                    cur.execute(f.read())
            existing = {}
            for table in ("users", "decisions", "tasks", "transactions", "savings_goals", "habit_log"):
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                existing[table] = cur.fetchone()[0]
            if not args.allow_nonempty and any(existing.values()):
                print(f"ERROR: target tables are not empty {existing}; refusing (use --allow-nonempty, or migrate into a fresh database).", file=sys.stderr)
                conn.rollback()
                return 2
            if users:
                cur.execute("SELECT username FROM users")
                clash = {r[0] for r in cur.fetchall()} & {u[0] for u in users}
                if clash:
                    print(f"ERROR: username conflict in target database: {sorted(clash)}; refusing to merge.", file=sys.stderr)
                    conn.rollback()
                    return 2
            for u, pw, role in users:
                cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s) ON CONFLICT (username) DO NOTHING", (u, pw, role))
            for d in decisions:
                cur.execute("INSERT INTO decisions (id, record_date, type, priority, title, owner) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING", d)
            for t in tasks:
                cur.execute("INSERT INTO tasks (id, title, urgency, importance, deadline, status, owner) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING", t)
            for tx in txs:
                cur.execute("INSERT INTO transactions (tx_date, type, category, amount, note, owner) VALUES (%s,%s,%s,%s,%s,%s)", tx)
            for g in goals:
                cur.execute("INSERT INTO savings_goals (name, target, saved, owner) VALUES (%s,%s,%s,%s)", g)
            for h in habits:
                cur.execute("INSERT INTO habit_log (habit, log_date, owner) VALUES (%s,%s,%s)", h)
            for d in backup:
                cur.execute("INSERT INTO decisions_backup (id, record_date, type, priority, title, owner) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING", d)
            for ln in daily:
                cur.execute("INSERT INTO daily_reports (line) VALUES (%s)", (ln,))
            for ln in errors:
                cur.execute("INSERT INTO error_logs (line) VALUES (%s)", (ln,))
            cur.execute("SELECT setval('decisions_id_seq', COALESCE((SELECT MAX(id) FROM decisions), 1))")
            cur.execute("SELECT setval('tasks_id_seq', COALESCE((SELECT MAX(id) FROM tasks), 1))")
        conn.commit()
        # Verify counts back from Postgres.
        with conn.cursor() as cur:
            for table, expected in counts.items():
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                got = cur.fetchone()[0]
                status = "OK" if got == expected else "MISMATCH"
                print(f"Verify {table}: txt={expected} pg={got} {status}")
                if got != expected:
                    print("ERROR: count mismatch after migration. Txt files are untouched; see rollback in docs/route2-phase1.md.", file=sys.stderr)
                    return 3
    finally:
        conn.close()
    print("Migration complete. Rollback: restore the txt backup copy and run without DATABASE_URL (see docs/route2-phase1.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
