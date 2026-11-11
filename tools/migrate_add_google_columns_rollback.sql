-- Personal Decision & Problem Solver — Google Auth migration (down / rollback).
--
-- Removes the Google Sign-In columns and restores password_hash
-- NOT NULL. REFUSES while any Google-only user (NULL
-- password_hash) still exists: remove or convert those accounts
-- first (give them a password via POST /api/auth/set-password, or
-- delete the account), then run this again.
BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE password_hash IS NULL) THEN
        RAISE EXCEPTION 'Cannot roll back: Google-only users (NULL password_hash) still exist';
    END IF;
END $$;
DROP INDEX IF EXISTS users_google_sub_unique;
DROP INDEX IF EXISTS users_email_unique;
ALTER TABLE users DROP COLUMN IF EXISTS display_name;
ALTER TABLE users DROP COLUMN IF EXISTS auth_provider;
ALTER TABLE users DROP COLUMN IF EXISTS google_sub;
ALTER TABLE users DROP COLUMN IF EXISTS email;
ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL;
COMMIT;
