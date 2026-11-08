# Gemini AI Integration — Phase 1 (foundation)

Status: Phase 1 only. The Gemini client exists, `/api/ai/health`
reports its state, and mock tests pass. No AI feature endpoint
exists yet — those come in later phases.

## Environment variables

| Variable | Meaning | Default |
|---|---|---|
| `GEMINI_API_KEY` | Gemini API key. Read by the C++ backend only, fresh on every call. Never commit it, never put it in a file, never paste it in chat. | (unset = AI not configured) |
| `GEMINI_MODEL` | Model name used in the request URL. Only `[A-Za-z0-9._-]` are allowed; anything else falls back to the default. | `gemini-2.0-flash` |
| `GEMINI_API_BASE_URL` | Base URL of the Gemini API. Test seam: point it at a local mock server. | `https://generativelanguage.googleapis.com/v1beta` |
| `GEMINI_TIMEOUT_SECS` | Total request timeout, clamped to 1–120 s (connect timeout is always 10 s). | `30` |

Set the key only in the environment of the machine that runs
`cpp_server`, for example:

```sh
GEMINI_API_KEY="your-key-here" ./cpp_server --port 8000
```

## Build behaviour (libcurl is opt-in)

`dashboard/gemini_client.cpp` uses libcurl only when
`<curl/curl.h>` is available at compile time (same opt-in pattern
as libpq in `dashboard/pg_store.h`). The Makefile links `-lcurl`
only when `curl-config` exists.

- With libcurl: the real HTTPS client is compiled in and
  `/api/ai/health` reports `"available": true`.
- Without libcurl: the server still builds and runs normally;
  `gemini::generate()` returns error `"unavailable"` and
  `/api/ai/health` reports `"available": false`. This keeps
  Windows/MinGW builds working without a new dependency.

Install headers on Debian/Ubuntu with
`sudo apt-get install libcurl4-openssl-dev`. On MSYS2/MinGW
install the `mingw-w64-x86_64-curl` package.

`PDPS_NO_CURL` is a compile-time, test-only switch that forces
the stub path even when the headers exist
(`tests/gemini_test.py` uses it to test the unavailable path).

## API: `GET /api/ai/health`

Login required (401 without a valid session), like `/api/me`.
Response (example):

```json
{"available": true, "configured": true, "model": "gemini-2.0-flash"}
```

- `available` — libcurl client compiled in.
- `configured` — `GEMINI_API_KEY` is set and non-empty.
- `model` — effective model name.

The response never contains the key or any fragment of it.

## Security rules

- The key comes only from the environment, is sent only as the
  `x-goog-api-key` request HEADER, and is never placed in a URL,
  a log line, an error string, a database row, or an HTTP
  response. Error codes are short generic words only
  (`unavailable`, `not_configured`, `invalid_request`,
  `auth_error`, `timeout`, `request_failed`,
  `invalid_response`).
- User input is sent as DATA (`contents.parts[].text`) only. It
  is never treated as an instruction to the model, and prompt or
  response text is never logged.
- Requests are validated: empty prompts and prompts over 8000
  characters are rejected before any network call. Responses are
  validated: a 2xx reply without a usable
  `candidates[0].content.parts[0].text` is `invalid_response`.
  Replies are capped at 1 MiB.
- The Python server (`dashboard/server.py`) has no Gemini code
  and must never handle the key.

## Tests

```sh
python3 tests/gemini_test.py   # mock Gemini server; no real API call
```

It builds the server, runs a C++ harness against a local mock
Gemini server (success, invalid JSON, HTTP 500, HTTP 401,
timeout, empty/oversized prompt, missing key), checks the
no-libcurl stub, and checks `/api/ai/health` with and without a
key. The only key string in the tests is the fake value
`"test-key"`.
