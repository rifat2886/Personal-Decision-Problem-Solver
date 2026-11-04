#!/usr/bin/env python3
"""Export all PDPS Postgres tables to JSON (Route 2, Phase 1).

This is the portable backup format for Postgres mode: it needs no
pg_dump on the host, so it works from any machine that can reach
the database. It exports data only — never passwords in plain
text beyond the password_hash values already stored in the
users table (those are hashes, not passwords, and the export
file must still be treated as sensitive and never committed).

Usage:
    python3 tools/pg_export_json.py --out pg-backup.json
    # DATABASE_URL must be set in the environment.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard"))
import pg_store  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Export PDPS Postgres tables to JSON.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    conn = pg_store.connect()
    try:
        data = {
            "users": [{"username": u, "password_hash": v["password"], "role": v["role"]}
                      for u, v in pg_store.load_users(conn).items()],
            "decisions": pg_store.load_decisions(conn),
            "tasks": pg_store.load_tasks(conn),
            "transactions": pg_store.load_transactions(conn),
            "savings_goals": pg_store.load_savings(conn),
            "habits": pg_store.load_habits(conn),
        }
    finally:
        conn.close()
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {args.out} (users={len(data['users'])}, decisions={len(data['decisions'])}, tasks={len(data['tasks'])}, transactions={len(data['transactions'])}, savings={len(data['savings_goals'])})")


if __name__ == "__main__":
    main()
