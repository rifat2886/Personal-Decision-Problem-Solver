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

Files migrated: users.txt, google_links.txt, decisions.txt, tasks.txt,
transactions.txt, savings_goals.txt, habit_log.txt,
decisions_backup.txt, daily_report.txt, error_log.txt,
ai_history.txt.
Google-only accounts (Phase 3) are stored in users.txt as
"username! ROLE" (two fields) or "username ! ROLE" (the "!"
sentinel credential); their password_hash migrates as NULL and
their Google link (sub/email/display name) comes from
google_links.txt. A link line with an empty sub is an unlinked
account that keeps its verified email.
Legacy records (no owner field) are inserted with owner NULL,
so the legacy visibility rule is preserved exactly.
IDs from decisions.txt/tasks.txt are preserved, and the SERIAL
sequences are set to MAX(id) afterwards, so the next insert
does not collide with a migrated id. ai_history.txt rows keep
their ids too (same sequence fix); a row with no usable owner
is skipped, because the ai_history table requires owner NOT
NULL and an ownerless row could never be seen by any user.
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
    # Returns a list of dicts. A "!" credential is the Google-only
    # sentinel (Phase 3): the account has no password, so
    # password_hash migrates as NULL. Google fields start empty
    # and are filled from google_links.txt by the caller.
    users = []
    for ln in lines:
        parts = ln.split()
        if len(parts) >= 3:
            pw = None if parts[1] == "!" else parts[1]
            users.append({"username": parts[0], "password_hash": pw,
                          "role": parts[2], "email": None,
                          "google_sub": None,
                          "auth_provider": "google" if pw is None else "password",
                          "display_name": None})
        elif len(parts) == 2 and len(parts[0]) > 1 and parts[0].endswith("!"):
            users.append({"username": parts[0][:-1], "password_hash": None,
                          "role": parts[1], "email": None,
                          "google_sub": None, "auth_provider": "google",
                          "display_name": None})
    return users


def parse_google_links(lines):
    # google_links.txt: "username|google_sub|email|display_name".
    # An empty sub is an unlinked account that keeps its email.
    links = {}
    for ln in lines:
        p = ln.split("|")
        if len(p) >= 4:
            links[p[0]] = {"google_sub": p[1] or None,
                           "email": p[2] or None,
                           "display_name": p[3] or None}
    return links


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


def split_pipe_escaped(s):
    """Split on '|' but not on '\\|' — mirrors splitPipeEscaped in
    dashboard/cpp_server.cpp, so ai_history.txt parses exactly as
    the server reads it."""
    parts, cur, i = [], [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            cur.append(c)
            cur.append(s[i + 1])
            i += 2
        elif c == "|":
            parts.append("".join(cur))
            cur = []
            i += 1
        else:
            cur.append(c)
            i += 1
    parts.append("".join(cur))
    return parts


def ai_unescape(s):
    """Reverse aiEscape in dashboard/cpp_server.cpp: \\ -> \\,
    \\| -> |, \\n -> newline, \\r -> carriage return; an unknown
    escape keeps the escaped char (same as the server)."""
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n == "n":
                out.append("\n")
            elif n == "r":
                out.append("\r")
            elif n == "|":
                out.append("|")
            elif n == "\\":
                out.append("\\")
            else:
                out.append(n)
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def parse_ai_history(lines):
    """Parse ai_history.txt lines:
    id|created_at|feature|prompt|response|owner, with prompt and
    response escaped as the server writes them. Returns
    (rows, skipped): rows are (id, owner, feature, prompt,
    response, created_at) ready for the ai_history table, ids
    preserved. A line is skipped (counted, not fatal) when it has
    fewer than 6 fields, a non-integer id, or no owner — the
    server's own loader skips short lines the same way, and an
    ownerless row could never be returned to any user."""
    out, skipped = [], 0
    for ln in lines:
        p = split_pipe_escaped(ln)
        if len(p) < 6:
            skipped += 1
            continue
        try:
            row_id = int(p[0])
        except ValueError:
            skipped += 1
            continue
        owner = p[5]
        if not owner:
            skipped += 1
            continue
        out.append((row_id, owner, p[2], ai_unescape(p[3]), ai_unescape(p[4]), p[1]))
    return out, skipped


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
    google_links = parse_google_links(read_lines(data_dir, "google_links.txt"))
    for u in users:
        link = google_links.get(u["username"])
        if link:
            u["google_sub"] = link["google_sub"]
            u["email"] = link["email"]
            u["display_name"] = link["display_name"]
            # The provider follows the Google LINK (the sub), not
            # the email: an unlinked account keeps its email but
            # signs in with its password only.
            if u["google_sub"]:
                u["auth_provider"] = "both" if u["password_hash"] is not None else "google"
    decisions = parse_decisions(read_lines(data_dir, "decisions.txt"))
    tasks = parse_tasks(read_lines(data_dir, "tasks.txt"))
    txs = parse_txs(read_lines(data_dir, "transactions.txt"))
    goals = parse_goals(read_lines(data_dir, "savings_goals.txt"))
    habits = parse_habits(read_lines(data_dir, "habit_log.txt"))
    backup = parse_decisions(read_lines(data_dir, "decisions_backup.txt"))
    daily = read_lines(data_dir, "daily_report.txt")
    errors = read_lines(data_dir, "error_log.txt")
    ai_history, ai_skipped = parse_ai_history(read_lines(data_dir, "ai_history.txt"))
    counts = {"users": len(users), "decisions": len(decisions), "tasks": len(tasks),
              "transactions": len(txs), "savings_goals": len(goals), "habit_log": len(habits),
              "decisions_backup": len(backup), "daily_reports": len(daily), "error_logs": len(errors),
              "ai_history": len(ai_history)}
    print("Parsed txt counts:", counts)
    if ai_skipped:
        print(f"Note: skipped {ai_skipped} malformed/ownerless ai_history.txt line(s); they could never be returned to any user.")
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
            for table in ("users", "decisions", "tasks", "transactions", "savings_goals", "habit_log", "ai_history"):
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                existing[table] = cur.fetchone()[0]
            if not args.allow_nonempty and any(existing.values()):
                print(f"ERROR: target tables are not empty {existing}; refusing (use --allow-nonempty, or migrate into a fresh database).", file=sys.stderr)
                conn.rollback()
                return 2
            if users:
                cur.execute("SELECT username FROM users")
                clash = {r[0] for r in cur.fetchall()} & {u["username"] for u in users}
                if clash:
                    print(f"ERROR: username conflict in target database: {sorted(clash)}; refusing to merge.", file=sys.stderr)
                    conn.rollback()
                    return 2
            for u in users:
                cur.execute("INSERT INTO users (username, password_hash, role, email, google_sub, auth_provider, display_name) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (username) DO NOTHING",
                            (u["username"], u["password_hash"], u["role"], u["email"], u["google_sub"], u["auth_provider"], u["display_name"]))
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
            for h in ai_history:
                cur.execute("INSERT INTO ai_history (id, owner, feature, prompt, response, created_at) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING", h)
            cur.execute("SELECT setval('decisions_id_seq', COALESCE((SELECT MAX(id) FROM decisions), 1))")
            cur.execute("SELECT setval('tasks_id_seq', COALESCE((SELECT MAX(id) FROM tasks), 1))")
            cur.execute("SELECT setval('ai_history_id_seq', COALESCE((SELECT MAX(id) FROM ai_history), 1))")
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
