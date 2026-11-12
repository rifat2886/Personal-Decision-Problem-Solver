// google_auth.h — Google ID-token verification for the C++ dashboard server.
//
// Google Identity Services (GIS) "Sign in with Google" button returns
// an ID token (JWT) to the page; the page POSTs it to
// POST /api/auth/google, and this module verifies it before any
// account is created or any session is issued.
//
// Security rules (do not weaken them):
// - Identity comes ONLY from the verified ID token. Plain user IDs
//   from the client are never trusted (Google: "Do not use plain
//   user IDs from the client to identify users on your backend
//   server; always use verifiable ID tokens"). `sub` is the stable
//   ID; email is never used to link accounts (no auto-link).
// - Verification is local, against Google's public keys (JWKS):
//   RS256 signature over header.payload with the key for the
//   token's `kid`, plus iss / aud / exp / email_verified checks.
//   Google's tokeninfo endpoint is NEVER used (development only).
// - The token is never stored and never logged. Only `sub`,
//   `email` and the display name are stored (in the users table /
//   google_links.txt). Error codes never contain the token.
// - The API key model does not apply here: there is no client
//   secret in this flow at all. GOOGLE_CLIENT_ID is a public
//   identifier (it is embedded in the frontend by design).
//
// Build behaviour (same opt-in pattern as gemini_client / libpq):
// - When OpenSSL headers AND libcurl are available, the real
//   verification is compiled in and available() returns true.
// - When either is missing, available() returns false and
//   verifyToken() returns error "unavailable"; the server still
//   builds and runs normally, and POST /api/auth/google answers
//   503 "Google sign-in unavailable". This keeps Windows/MinGW
//   builds working without a new dependency.
// - PDPS_NO_OPENSSL (compile-time) forces the stub path even when
//   the headers exist, so tests can exercise the unavailable path
//   without uninstalling OpenSSL. The Makefile and the Windows
//   .bat launchers also set it when OpenSSL is not detected:
//   otherwise the headers compile the real verifier in while
//   -lcrypto is never linked and the build fails with
//   "undefined reference to EVP_*".

#ifndef PDPS_GOOGLE_AUTH_H
#define PDPS_GOOGLE_AUTH_H

#include <string>

namespace google_auth {

// Verified claims from one ID token. Only set when verifyToken()
// returns ok=true.
struct Claims {
    std::string sub;         // Google's stable user ID (primary key for identity)
    std::string email;       // verified email address
    std::string name;        // display name from the token (may be empty)
    bool emailVerified = false;
    long long exp = 0;       // expiry, seconds since epoch
};

// Outcome of one verifyToken() call. On success ok=true and claims
// holds the verified identity. On failure ok=false, claims is
// empty, and error is one short generic code (never the token):
//   "unavailable"       OpenSSL/libcurl support was not compiled in
//   "not_configured"    GOOGLE_CLIENT_ID is unset (sign-in disabled)
//   "fetch_failed"      the JWKS could not be fetched (try again later)
//   "invalid_token"     malformed JWT / malformed JSON / bad claim shape
//   "wrong_algorithm"   header alg is not exactly RS256
//   "wrong_issuer"      iss is not accounts.google.com
//   "wrong_audience"    aud does not equal GOOGLE_CLIENT_ID
//   "expired"           exp is in the past (60 s leeway allowed)
//   "email_not_verified" email_verified is not true
//   "unknown_kid"       no JWKS key matches the token's kid
//   "bad_signature"     the RS256 signature does not verify
struct Result {
    bool ok = false;
    Claims claims;
    std::string error;
};

// True only when the real verifier was compiled in (OpenSSL + curl).
bool available();

// True when GOOGLE_CLIENT_ID is set and non-empty (independent of
// whether OpenSSL was compiled in).
bool configured();

// True when Google sign-in is enabled: configured() and
// GOOGLE_SIGNIN_ENABLED is not "0". Default: enabled whenever
// GOOGLE_CLIENT_ID is set.
bool enabled();

// The configured client ID, or "" when unset. Public identifier.
std::string clientId();

// Verify one ID token end to end (structure, claims, JWKS fetch,
// RS256 signature). The token is never logged.
Result verifyToken(const std::string& idToken);

}  // namespace google_auth

#endif  // PDPS_GOOGLE_AUTH_H
