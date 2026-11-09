// gemini_client.h — minimal Gemini API client for the C++ dashboard server.
//
// Phase 1 (foundation only): one function, gemini::generate(), which
// sends a prompt to the Gemini generateContent endpoint and returns
// the reply text, plus helpers the server uses for /api/ai/health.
//
// Security rules (do not weaken them):
// - The API key comes ONLY from the GEMINI_API_KEY environment
//   variable, read fresh on every call. It is never written to a
//   file, never stored in a struct that is logged, and never
//   included in any error string, log line, or HTTP response.
// - Auth uses the "x-goog-api-key" request HEADER. The key is
//   never placed in the request URL.
// - User input is sent as DATA (contents.parts[].text) only. It is
//   never treated as an instruction to the model, and no prompt
//   text is ever logged.
// - This client never prints anything. All outcomes are returned
//   in the Result struct with a short generic error code.
//
// Build behaviour (same opt-in pattern as libpq in pg_store.h):
// - When <curl/curl.h> is available, the real HTTPS client is
//   compiled in and available() returns true.
// - When it is not available, available() returns false and
//   generate() returns error "unavailable"; the server still
//   builds and runs normally, and /api/ai/health reports
//   available=false. This keeps Windows/MinGW builds working
//   without a new dependency.
// - PDPS_NO_CURL (compile-time, test-only) forces the stub path
//   even when the headers exist, so tests can exercise the
//   unavailable path without uninstalling libcurl.

#ifndef PDPS_GEMINI_CLIENT_H
#define PDPS_GEMINI_CLIENT_H

#include <string>

namespace gemini {

// Outcome of one generate() call. On success ok=true and text holds
// the model's reply. On failure ok=false, text is empty, and error
// is one short generic code:
//   "invalid_request"  prompt empty or over 8000 chars
//   "unavailable"      libcurl support was not compiled in
//   "not_configured"   GEMINI_API_KEY is unset or empty
//   "auth_error"       Gemini answered 401/403 (bad or revoked key)
//   "rate_limited"     Gemini answered 429 (quota exceeded)
//   "timeout"          the request exceeded GEMINI_TIMEOUT_SECS
//   "request_failed"   network/HTTP failure (incl. 5xx)
//   "invalid_response" HTTP 2xx but the body had no usable reply text
// Error codes never contain the key, the prompt, or response text.
struct Result {
    bool ok = false;
    std::string text;
    std::string error;
};

// True only when the real HTTPS client was compiled in.
bool available();

// True when GEMINI_API_KEY is set and non-empty (independent of
// whether libcurl was compiled in).
bool configured();

// Model from GEMINI_MODEL, or "gemini-3-flash-preview" when
// unset/invalid. The fallback model is gemini-3-flash-preview
// (verified working live); the production target gemini-3.8-flash
// is selectable with GEMINI_MODEL once it serves reliably.
std::string modelName();

// Send one prompt to Gemini and return the reply text.
Result generate(const std::string& prompt);

}  // namespace gemini

#endif  // PDPS_GEMINI_CLIENT_H
