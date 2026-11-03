# Security

## What was fixed in this branch

### Passwords are hashed, not stored in plain text
- New accounts store only a PBKDF2-HMAC-SHA256 hash
  (`pbkdf2$100000$<salt-hex>$<hash-hex>`, 100,000 iterations, 16-byte
  random salt per user), implemented in `password_hash.h` (C++) and
  with `hashlib.pbkdf2_hmac` in `dashboard/server.py` (Python) in the
  identical format, so the console app, the C++ server and the Python
  fallback all verify each other's credentials.
- Argon2id was considered but needs an external library, which this
  project does not depend on; PBKDF2-HMAC-SHA256 is a recognised
  standard KDF (RFC 8018) and is reproducible from the Python
  standard library.
- The users.txt format is unchanged in shape: still
  `username credential ROLE`, one user per line, no spaces in any
  field. Only the credential field changes from plaintext to hash.

### Backward-compatible migration (no data loss)
- Old plaintext accounts still log in. On a successful login, the
  credential is immediately rewritten as a hash, under the users.txt
  lock, in the console app, the C++ server and the Python server.
  After that login, no plaintext remains for that user.
- Before migrating, back up users.txt (copy it to users_backup.txt).
  Rollback: restore the backed-up users.txt file; old plaintext
  accounts will log in again and re-migrate on next login, and
  already-hashed accounts keep working (their hashes are still
  valid after a restore of the pre-migration file only if the
  restore is from before any password change — see "Recovery" below).
- Password change always stores the new password as a hash.
- Passwords are never returned by any API (admin/users return
  username + role only) and never written to any log file.

### Sessions
- Session tokens are random (C++: OS random_device + counter;
  Python: secrets.token_hex) and are never written to a file.
- Sessions expire after 12 hours; expired tokens are rejected and
  removed. Logout deletes the token immediately.
- There are no cookies, so there is no cookie-based CSRF: API calls
  require an `Authorization: Bearer <token>` header, which a plain
  cross-site form cannot supply.
- Sessions live only in the running server's memory and are NOT
  shared between servers: a token issued by the C++ server is not
  valid on the Python server and vice versa. Run only one server
  at a time (the normal `start-dashboard` flow) and log in again
  if you switch servers; the password hash itself is shared, so
  the same account works on either server after a fresh login.

### Rate limiting and request limits
- Login: 5 failed attempts per username in 5 minutes, then HTTP 429
  until the window passes. A successful login clears the count.
- Request bodies are capped at 1 MiB (C++: HTTP 413; Python: rejected
  as invalid JSON). Static serving is allow-listed to
  index.html / style.css / app.js only (`/users.txt` returns 404).

### File access and locking
- The console app, the C++ server and the Python fallback all lock
  the same per-file `<datafile>.lock` files (flock on POSIX,
  LockFileEx on Windows, fcntl/msvcrt in Python), so concurrent
  writes from different processes cannot lose updates. This was
  tested with 10 parallel savings adds totalling exactly 1000.
- Lock files (`*.lock`) are empty marker files and are git-ignored;
  they contain no data.

## What is still NOT safe, and must not be skipped

1. **No HTTPS in the servers themselves.** Both servers bind to
   localhost only (127.0.0.1) by default. Do NOT bind them to
   0.0.0.0 or expose them to the public internet unless they sit
   behind a reverse proxy that terminates TLS (HTTPS) and the
   operator has verified it. Public deployment is NOT done in this
   branch and must not be assumed.
2. **No account recovery.** There is no password reset, email
   verification, or "forgot password" flow. If a user forgets their
   password, an ADMIN must delete and re-create the account, or
   restore users.txt from backup.
3. **No per-IP rate limiting.** The login limit is per username, not
   per IP, so a distributed guessing attack across many usernames
   is not blocked by this control alone. Do not expose the login
   endpoint publicly without an additional proxy-level limit.
4. **Session tokens are bearer tokens.** Anyone who copies a token
   can use it until it expires (12h) or is logged out. Do not share
   tokens, screenshots of tokens, or browser storage contents.

## Recovery
- If users.txt is corrupted, restore it from a backup copy. The
  console app and both servers read users.txt on every login, so a
  restored file takes effect immediately (no restart needed for the
  Python server; the C++ server also re-reads it per request).
- If a migration is interrupted mid-write, users.txt is written
  under a lock as a whole file; a partial write from a crashed
  process can leave a truncated file — restore from backup in that
  case, then log in again to re-migrate.
