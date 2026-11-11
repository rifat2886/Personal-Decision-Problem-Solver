-- Personal Decision & Problem Solver — Google Auth migration (up).
--
-- Adds Google Sign-In columns to the users table. Additive only:
-- no existing row is changed, no data is deleted. Idempotent: safe
-- to run twice.
--
-- Apply ONLY after the pre-migration safety query: the count of
-- users with NULL or empty password_hash must be 0. Apply in the
-- Neon SQL editor (or psql) after a backup. Never run against a
-- database you have not backed up. Never run against the local
-- test database in place of a real migration check — validate on
-- a scratch database first.
BEGIN;
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'password' CHECK (auth_provider IN ('password', 'google', 'both'));
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_unique ON users (google_sub) WHERE google_sub IS NOT NULL;
COMMIT;
