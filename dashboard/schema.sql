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
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('ADMIN', 'USER'))
);

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
