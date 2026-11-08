# Gemini AI Integration — Phase 1 (foundation) + Phase 2.1 (history + Daily Decision)

Status: Phase 2.1 done. The Gemini client exists,
`/api/ai/health` reports its state, `POST /api/ai/daily-decision`
is the first AI feature endpoint, and every successful AI reply
is stored in per-user AI history. The other five feature
endpoints come in later phases (2.2–2.6).

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

## API: `POST /api/ai/daily-decision` (Phase 2.1)

Login required (401 without a valid session). Request:

```json
{"input": "Should I study math or physics tonight?",
 "options": ["math", "physics"]}
```

- `input` — required, non-empty after trimming, max 4000 chars.
- `options` — optional array, max 10 items, each max 500 chars.

The server prepends a fixed instruction (decision assistant:
analyse the decision and options, give one clear recommendation
with short reasons and a brief explanation, keep it concise).
The user's input is inserted as quoted DATA, never as an
instruction. Invalid input returns `400 {"error":"invalid input"}`
without echoing the value, and never calls Gemini.

Success (200):

```json
{"reply": "<Gemini reply text>", "history_id": 1}
```

Failure mapping (generic messages only, never the Gemini error
body or the key):

| Gemini error | HTTP | Body |
|---|---|---|
| `not_configured`, `unavailable` | 503 | `{"error":"AI unavailable"}` |
| `auth_error` | 503 | `{"error":"AI configuration error"}` |
| `rate_limited` | 503 | `{"error":"AI request limit reached"}` |
| `timeout` | 504 | `{"error":"AI request timed out"}` |
| `request_failed`, `invalid_response`, `invalid_request` | 502 | `{"error":"AI request failed"}` |

## API: `POST /api/ai/task-analyzer` (Phase 2.2)

Login required (401 without a valid session). Request:

```json
{"description": "Finish the maths assignment",
 "title": "Maths assignment", "urgency": 8, "importance": 9,
 "deadline": "2026-11-20", "status": "in-progress"}
```

- `description` — the task description (canonical); `input`
  is accepted for compatibility. Required, non-empty after
  trimming, max 4000 chars. When both are present,
  `description` wins.
- `title` — optional, non-empty after trimming, max 500 chars.
- `urgency`, `importance` — optional strict integers 1–10
  (non-integers such as `10.5` or strings such as `"high"` are
  rejected; out-of-range values are rejected).
- `deadline` — optional, non-empty after trimming, max 100 chars.
- `status` — optional, max 50 chars; if present it must be one
  of `"pending"`, `"in-progress"`, `"done"`. The aliases
  `"in_progress"` and `"completed"` are accepted and normalised
  to `"in-progress"` and `"done"`. Any other value is rejected.

The server prepends a fixed instruction (task analysis
assistant: answer with five sections — (a) Task Analysis,
(b) Priority Recommendation, (c) Urgency Assessment,
(d) Suggested Next Action, (e) Explanation — judging priority
from urgency/importance, pointing out risks, and suggesting a
sensible order with concrete next steps, kept concise). The
user's fields are inserted as quoted DATA, never as
instructions. Invalid input returns
`400 {"error":"invalid input"}` without echoing the value, and
never calls Gemini. Success (200) and failure mapping are the
same as Daily Decision above; the history entry uses feature
`"task-analyzer"`.

## API: `POST /api/ai/study-planner` (Phase 2.3)

Login required (401 without a valid session). Request:

```json
{"description": "Prepare for the final exams in maths and physics",
 "subjects": ["Maths", "Physics"], "hours_per_day": 3,
 "exam_date": "2026-12-15"}
```

- `description` — what to study (canonical); `input` is
  accepted for compatibility. Optional extra context:
  non-empty after trimming, max 4000 chars. When both are
  present, `description` wins.
- `subjects` — REQUIRED array of strings, 1–10 items, each
  non-empty after trimming, max 200 chars. Must be a real
  JSON array of strings. Duplicate subjects are deduplicated
  case-insensitively ("Math" and "math" count as one),
  keeping the first occurrence; the deduplicated list is
  what goes into the prompt and the stored history prompt.
- `hours_per_day` — REQUIRED number, 0.5–24. Missing,
  non-numbers, 0, negatives and values above 24 are rejected.
- `exam_date` — optional strict `YYYY-MM-DD` date: 10 chars,
  digits and dashes only, a real calendar date (month 01–12,
  day valid for that month including leap years), and today
  or in the future by the server's local date. A malformed
  or past date is rejected.
- Missing subjects or hours_per_day, or an empty subjects
  array, is rejected, as is an empty body.

The server prepends a fixed instruction (study planning
assistant: answer with five sections — (a) Study Plan,
(b) Daily Schedule, (c) Subject Priorities, (d) Revision
Strategy, (e) Explanation — making the plan realistic for
the days remaining until the exam date when one is given,
and making sure the total study time in any single day does
not exceed the given hours per day, with a sensible order
and concrete time blocks, kept concise). The user's fields
are inserted as quoted DATA, never as instructions. Invalid
input returns `400 {"error":"invalid input"}` without
echoing the value, and never calls Gemini. Success (200)
and failure mapping are the same as Daily Decision above
(including mock 429 -> 503 `{"error":"AI request limit
reached"}`); the history entry uses feature
`"study-planner"`. If the history save itself fails, the
endpoint returns 502 instead of a 200 claiming success.

## API: AI history (Phase 2.1)

`GET /api/ai/history` — login required. Optional `?limit=`
(1–100, default 50). Newest first. Response:

```json
{"history": [{"id": 1, "feature": "daily-decision",
  "prompt": "Should I study math or physics tonight? [options: math; physics]",
  "response": "<Gemini reply text>", "created_at": "2026-11-08 13:55:01"}]}
```

`DELETE /api/ai/history/{id}` — login required. Deletes only
the caller's own row; returns `{"deleted": true}` or 404 for a
missing id or someone else's row.

History is saved ONLY on Gemini success — never on failures,
and the API key is never stored. The stored `prompt` is what the
user asked (input + options), not the full prompt with the
server instruction.

## Storage design (Phase 2.1)

Postgres is the primary store; the txt file is the backup used
when `DATABASE_URL` is unset.

- Postgres: table `ai_history` (`id SERIAL PRIMARY KEY`,
  `owner TEXT NOT NULL`, `feature`, `prompt`, `response`,
  `created_at`, all `TEXT NOT NULL` except `id`). Created by
  `dashboard/schema.sql` and by the server on startup
  (`dashboard/pg_store.h`). All queries are parameterised and
  always filtered by owner (`WHERE owner = $1`, newest first).
- TXT: file `ai_history.txt`, one row per entry:
  `id|created_at|feature|prompt|response|owner` (owner is the
  LAST pipe field, like the other stores). Prompt/response may
  contain `|`, newlines and backslashes, so they are escaped on
  write (`\` → `\\`, `|` → `\|`, newline → `\n`, CR → `\r`)
  and unescaped on read, under the same file lock as
  `decisions.txt`. IDs are sequential (max existing + 1).
- Owner is mandatory — there are NO legacy rows. A row without
  an owner is never returned to anyone, and ADMIN gets no
  exception: history is visible only to its owner.

The Python server (`dashboard/server.py`) has no Gemini code:
any `/api/ai/*` path returns
`501 {"error":"AI requires the C++ server"}` (401 without a
login still comes first).

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
python3 tests/gemini_test.py        # mock Gemini server; no real API call
python3 tests/ai_endpoints_test.py  # Daily Decision + history (mock)
```

`tests/gemini_test.py` builds the server, runs a C++ harness
against a local mock Gemini server (success, invalid JSON,
HTTP 500, HTTP 401, timeout, empty/oversized prompt, missing
key), checks the no-libcurl stub, and checks `/api/ai/health`
with and without a key. `tests/ai_endpoints_test.py` checks the
Daily Decision endpoint (auth, validation, failure mapping),
history storage and per-user isolation, and the Python
server's 501 for `/api/ai/*`. The only key string in the tests
is the fake value `"test-key"`.
