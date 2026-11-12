-- Personal Decision & Problem Solver — PostgreSQL schema (Route 2, Phase 1)
--
-- This schema mirrors the plain-text files exactly, field for field.
-- owner is NULL for "legacy" records (txt lines with no owner field).
-- Legacy visibility is NOT enforced by the database: it is enforced
-- by the server code, exactly as in txt mode — a legacy record is
-- visible only when the users table has exactly one user and that
-- user is the requester; ADMIN does NOT see other users' records.
-- See dashboard/pg_store.h and the server's ownerVisible() logic.
--
-- Apply with: psql "$DATABASE_URL" -f dashboard/schema.sql
-- The C++ server also creates these tables itself on first start
-- in Postgres mode (CREATE TABLE IF NOT EXISTS), so a manual
-- apply is only needed for a fresh database you want to inspect
-- or migrate into before starting the server.
--
-- No secret, password, or connection string is in this file.

CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT,
    role          TEXT NOT NULL CHECK (role IN ('ADMIN', 'USER')),
    email         TEXT,
    google_sub    TEXT,
    auth_provider TEXT NOT NULL DEFAULT 'password' CHECK (auth_provider IN ('password', 'google', 'both')),
    display_name  TEXT
);

-- Google Sign-In (Phase 3): partial unique indexes — uniqueness is
-- enforced only for accounts that actually have an email / Google
-- link; existing users with NULL email/google_sub are unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_unique ON users (google_sub) WHERE google_sub IS NOT NULL;

CREATE TABLE IF NOT EXISTS decisions (
    id           SERIAL PRIMARY KEY,
    record_date  TEXT NOT NULL,
    type         TEXT NOT NULL,
    priority     INTEGER NOT NULL,
    title        TEXT NOT NULL,
    owner        TEXT
);

CREATE TABLE IF NOT EXISTS decisions_backup (
    id           INTEGER PRIMARY KEY,
    record_date  TEXT NOT NULL,
    type         TEXT NOT NULL,
    priority     INTEGER NOT NULL,
    title        TEXT NOT NULL,
    owner        TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id         SERIAL PRIMARY KEY,
    title      TEXT NOT NULL,
    urgency    INTEGER NOT NULL,
    importance INTEGER NOT NULL,
    deadline   TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL,
    owner      TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id       SERIAL PRIMARY KEY,
    tx_date  TEXT NOT NULL,
    type     TEXT NOT NULL,
    category TEXT NOT NULL,
    amount   NUMERIC NOT NULL,
    note     TEXT NOT NULL DEFAULT '',
    owner    TEXT
);

CREATE TABLE IF NOT EXISTS savings_goals (
    id     SERIAL PRIMARY KEY,
    name   TEXT NOT NULL,
    target NUMERIC NOT NULL,
    saved  NUMERIC NOT NULL DEFAULT 0,
    owner  TEXT
);

-- Goal names are unique per user in the API (checked by the server
-- with the same ownerVisible rules as txt mode). This index is a
-- second line of defence for the same owner only; legacy (NULL)
-- goals are kept distinct by COALESCE so a legacy goal and an
-- owned goal with the same name can both exist, as in txt mode,
-- and the server's duplicate check still decides visibility.
CREATE UNIQUE INDEX IF NOT EXISTS savings_goals_name_owner_idx
    ON savings_goals (name, (COALESCE(owner, '')));

CREATE TABLE IF NOT EXISTS habit_log (
    id       SERIAL PRIMARY KEY,
    habit    TEXT NOT NULL,
    log_date TEXT NOT NULL,
    owner    TEXT
);

-- daily_report.txt lines are stored verbatim, one line per row.
-- There is no GET endpoint for daily reports in the API; this
-- table exists so the POST /api/daily-summary data is not lost
-- when the server runs in Postgres mode.
CREATE TABLE IF NOT EXISTS daily_reports (
    id   SERIAL PRIMARY KEY,
    line TEXT NOT NULL
);

-- error_log.txt lines are stored verbatim. The server only reads
-- this table (it never writes error lines); the console app writes
-- error_log.txt in txt mode, and the migration tool copies it here.
CREATE TABLE IF NOT EXISTS error_logs (
    id   SERIAL PRIMARY KEY,
    line TEXT NOT NULL
);

-- AI history (Gemini integration, Phase 2.1): one row per
-- successful AI reply. Unlike the other tables, owner is NOT NULL
-- here: history is always owned by exactly one user, there are no
-- legacy rows, and the server only ever selects/inserts/deletes
-- with an explicit owner filter, so one user can never see or
-- delete another user's history. created_at is a local
-- "YYYY-MM-DD HH:MM:SS" timestamp string.
CREATE TABLE IF NOT EXISTS ai_history (
    id         SERIAL PRIMARY KEY,
    owner      TEXT NOT NULL,
    feature    TEXT NOT NULL,
    prompt     TEXT NOT NULL,
    response   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
