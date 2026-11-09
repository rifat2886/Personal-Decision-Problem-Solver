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

## API: `POST /api/ai/problem-solver` (Phase 2.4)

Login required (401 without a valid session). Request:

```json
{"problem": "I keep missing my morning study sessions"}
```

- `problem` — the problem to solve (canonical); `input` is
  accepted for compatibility. Required, non-empty after
  trimming, max 4000 characters. When both are present,
  `problem` wins. No other fields are accepted.
- The 4000-character limit counts UTF-8 code points, not
  bytes: 4000 Bengali characters (~12000 bytes) are
  accepted, 4001 are rejected. The Gemini client's own
  8000-character prompt budget is counted the same way
  (Phase 2.4 fixed its byte-length check), so a 4000-
  character problem plus the fixed instruction stays
  inside the budget. The Daily Decision, Task Analyzer
  and Study Planner endpoints keep their byte-length
  checks unchanged.

The server prepends a fixed instruction (problem solving
assistant: answer with five sections — (a) Problem Analysis,
(b) Possible Solutions, (c) Recommended Solution, (d) Action
Steps, (e) Explanation — giving practical, prioritised
solutions with concrete next steps, kept concise). The
user's problem is inserted as quoted DATA and the
instruction states it is untrusted data to analyse, not
instructions to follow, so instruction-like text inside
the problem cannot redirect the model. Invalid input
returns `400 {"error":"invalid input"}` without echoing
the value, and never calls Gemini. Success (200) and
failure mapping are the same as Daily Decision above
(including mock 429 -> 503 `{"error":"AI request limit
reached"}`); the history entry uses feature
`"problem-solver"` and stores the problem text only, not
the server instruction. Like Study Planner, the saved row
is verified to have landed (read-back) before the reply
is sent: if the history save itself fails, the endpoint
returns 502 instead of a 200 claiming success — in both
txt and Postgres mode.

## API: `POST /api/ai/budget` (Phase 2.5)

Login required (401 without a valid session). Request
(all fields optional, but at least one meaningful field
is required — an empty object returns
`400 {"error":"invalid input"}`):

```json
{"income": 10000,
 "expenses": [{"category": "food", "amount": 3000},
              {"category": "transport", "amount": 1500}],
 "savings_goal": {"name": "laptop", "target": 10000, "saved": 1000},
 "input": "exam next month"}
```

- `income` — JSON number, 0 to 1,000,000,000. Decimals
  allowed. `expenses` — array, at most 20 items, each an
  object with `category` (string, non-empty after
  trimming, max 100 UTF-8 code points) and `amount`
  (JSON number, 0 to 1,000,000,000). `savings_goal` —
  object with `name` (string, non-empty after trimming,
  max 200 code points), `target` (JSON number, greater
  than 0, up to 1,000,000,000) and `saved` (JSON number,
  0 to 1,000,000,000; may exceed `target` — the goal is
  already reached). `input` — free text, max 2000 UTF-8
  code points (empty after trimming counts as absent).
- Numbers are validated strictly: only a valid JSON
  number is accepted (optional `-`, digits, optional
  fraction, optional exponent, no leading zeros except
  the number 0 itself). Strings, booleans, null, NaN,
  Infinity, malformed numbers, numbers outside the
  bounds and trailing junk after a value are all
  rejected with 400. A quoted field name inside the
  free text or inside a category string is never treated
  as a real field.
- The server computes the figures itself and puts them
  in the prompt as DATA — Gemini only advises, never
  calculates. Total expenses = sum of amounts.
  Remaining = income − total expenses (N/A when income
  is absent). Savings rate = remaining ÷ income as a
  percentage (N/A when income is absent or 0 — division
  by zero is guarded, never inf/nan). Goal progress =
  saved ÷ target as a percentage (target is always
  greater than 0). Months to goal = (target − saved) ÷
  remaining, only when remaining is greater than 0 and
  target is greater than saved, otherwise N/A (0.00
  when the goal is already reached). A negative
  remaining is shown explicitly as a deficit, e.g.
  `Remaining: -1500.00 (DEFICIT: expenses exceed income
  by 1500.00)`. All money figures are formatted with
  2 decimal places, and tiny floating-point residues
  are rounded away (0.1 + 0.2 against 0.3 income is
  exactly 0.00 remaining, never -0.00 or a deficit).
  Amounts are capped at 1e9 each with at most 20
  expenses, so totals stay far below double's
  exact-integer range; no unbounded sum ever passes
  validation.
- The fixed instruction asks Gemini for five sections —
  (a) Income & Expense Analysis, (b) Budget Plan,
  (c) Savings Goal Progress, (d) Spending
  Recommendations, (e) Explanation — and states the
  figures are pre-computed (use them as given, do not
  recompute them) and the user data is untrusted data
  to analyse, not instructions to follow. The prompt
  budget is 8000 code points; the largest valid request
  (20 expenses + 2000-character input + income + goal,
  about 5200 code points) stays inside it. Invalid input
  returns `400 {"error":"invalid input"}` without
  echoing the value, and never calls Gemini. Success
  (200) and failure mapping are the same as Daily
  Decision above (including mock 429 -> 503
  `{"error":"AI request limit reached"}`); the history
  entry uses feature `"budget"` and stores the
  structured summary (income, expenses list, savings
  goal, input text) only — never the fixed instruction
  and never the computed figures. Like Study Planner
  and Problem Solver, the saved row is verified to
  have landed (read-back) before the reply is sent:
  if the history save itself fails, the endpoint
  returns 502 instead of a 200 claiming success — in
  both txt and Postgres mode (Postgres save failure
  verified live: DROP TABLE ai_history mid-run ->
  502, restart -> 200).

## API: `POST /api/ai/habit` (Phase 2.6)

Login required (401 without a valid session). Request
(`habit` is required; everything else is optional):

```json
{"habit": "morning run", "target_streak": 30,
 "frequency": "daily", "input": "I keep skipping weekends",
 "today": "2026-11-09"}
```

- `habit` — string, non-empty after trimming, at most
  100 UTF-8 code points. A number, boolean or null is
  rejected with 400, as are control characters and `|`
  (the txt-file separator, same rule as usernames).
  `target_streak` — strict integer 1–365 (`10.5`,
  `"30"`, `true`, `null` and trailing junk are all
  rejected with 400). `frequency` — `"daily"` (the
  default) or `"weekly"`; anything else is 400.
  `input` — free text, at most 2000 UTF-8 code points.
  `today` — a strict YYYY-MM-DD date (valid calendar
  date) within ±2 days of the server's local date; a
  malformed date or one further away is 400. A quoted
  `"habit"` inside the free text is never treated as a
  real field (strict field parsing, as in Budget).
- The server computes the figures itself from the
  caller's own habit log (owner-filtered) and puts
  them in the prompt as DATA — Gemini only advises,
  never calculates. The reference date is `today` when
  given, otherwise the server's local date; all
  windows are computed from it, and the prompt names
  the reference date (plus the server date when they
  differ). Daily: current streak (consecutive days
  ending at the latest log date), total log count,
  latest log date (or N/A), days since the last log
  (0 when a log is dated in the future), 30-day
  completion rate (distinct logged days in the last 30
  days / 30, 2 decimals) and longest streak. Weekly:
  streak of consecutive ACTIVE ISO weeks (Monday–
  Sunday, a week with at least one log) ending at the
  latest active week — never the daily streak; several
  logs in one week count as one active week, a missed
  week resets the streak, and a Sunday log plus the
  next Monday's log are two consecutive active weeks.
  Also reported: latest active week (its Monday),
  whether the current week is active, weeks since the
  last active week, the 8-week completion rate (active
  weeks in the last 8 ISO weeks / 8) and the longest
  weekly streak. The target unit follows the
  frequency (days for daily, weeks for weekly);
  progress is streak / target as a percentage (it may
  exceed 100%), and a streak at or above the target
  is noted as "goal already reached" in the prompt.
- The figures come from a separate helper
  (`habitAiStats`) used only by this route. The
  existing `habitStreakJson()` and the
  `/api/habits/streak` route are untouched and still
  daily-only. The endpoint is read-only on habit data:
  it never inserts, updates or deletes habit rows; its
  only write is the ai_history save, as in the other
  AI endpoints.
- The fixed instruction asks Gemini for five sections —
  (a) Habit Analysis, (b) Streak Assessment, (c)
  Improvement Plan, (d) Motivation & Tips, (e)
  Explanation — and states the figures are pre-computed
  (use them as given, do not recompute them) and the
  user data is untrusted data to analyse, not
  instructions to follow. The prompt budget is 8000
  code points; the largest valid request (100-character
  habit + 2000-character input + target + frequency +
  today, about 3000 code points) stays inside it.
  Invalid input returns `400 {"error":"invalid input"}`
  without echoing the value, and never calls Gemini.
  Success (200) and failure mapping are the same as
  Daily Decision above (including mock 429 -> 503
  `{"error":"AI request limit reached"}`); the history
  entry uses feature `"habit"` and stores the user's
  data only (habit, target_streak, frequency, input,
  reference date) — never the fixed instruction and
  never the computed figures. Like Study Planner,
  Problem Solver and Budget, the saved row is verified
  to have landed (read-back) before the reply is sent:
  if the history save itself fails, the endpoint
  returns 502 instead of a 200 claiming success — in
  both txt and Postgres mode (Postgres save failure
  verified live: DROP TABLE ai_history mid-run ->
  502, restart -> 200).

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
  UTF-8 characters (code points, not bytes) are rejected
  before any network call. Responses are
  validated: a 2xx reply without a usable
  `candidates[0].content.parts[0].text` is `invalid_response`.
  Replies are capped at 1 MiB.
- The Python server (`dashboard/server.py`) has no Gemini code
  and must never handle the key.

## Phase 3.1 — AI Daily Decision in the dashboard

The first AI section in the dashboard. It calls only
`POST /api/ai/daily-decision` (Phase 2.1) — no backend change
was needed for Phase 3.1.

- UI: new nav group "AI Assistant" (after "Personal") with a
  button `data-section="ai-daily"`, and a section
  `<section id="ai-daily">` following the existing section
  pattern (`<h2>`, `.muted` description, `.card` with the form,
  an action button, `<div id="aiDailyMsg">`, a warning div and
  the reply div). The section is protected by the existing
  auth gate: it is NOT in `PUBLIC_SECTIONS` (landing, auth
  only), the nav button is hidden by the logged-out body
  class, and the server still returns 401 without a session.
- Form: a textarea for the decision and up to 10 optional
  option rows ("Add option", each row removable; empty rows
  are ignored and never sent; the `options` field is omitted
  entirely when no option is given).
- Validation (client-side, mirrors the server): input trimmed,
  non-empty, max **4000 UTF-8 BYTES** — counted with
  `TextEncoder`, not characters (a Bengali character is 3
  bytes; the UI text says "4000 bytes", never "4000
  characters"). Each option trimmed, non-empty, max **500
  bytes**. Validation errors are shown immediately, before
  any network call.
- Newline sanitization: `\r`, `\n`, `\t` and other control
  characters (U+0000–U+001F, U+007F) are replaced with spaces
  BEFORE sending, because the backend's old JSON helpers
  (`jsonStringField`/`jsonStringArrayField`, Phase 2.1–2.4) do
  NOT decode escapes — a `\n` in the request body would
  otherwise arrive as the letter `n`.
- Reply: rendered with `esc()` into the reply div (never raw
  `innerHTML`); line breaks are preserved by the `.ai-reply`
  CSS class (`white-space: pre-wrap`). The `history_id` is
  shown next to the success message. If `history_id` is 0,
  the reply is shown AND a warning is shown that the reply
  was received but was NOT saved to AI history (this endpoint
  has no history read-back check — a failed save can still
  return 200 with `history_id` 0).
- Loading/error states: the Ask button is disabled and shows
  "Thinking…" while the call runs (double-submit blocked);
  an error clears any stale reply. `400 {"error":"invalid
  input"}` shows a friendly "Invalid input" message; `401`
  is handled by the shared `api()` (forced logout to Login);
  `501` explains that AI needs the C++ server; `502`/`503`/
  `504` show the server's message with a short note. No API
  key is ever sent, logged or shown by the frontend.
- Files: `dashboard/index.html`, `dashboard/app.js`,
  `dashboard/style.css` (new rules only: `textarea`,
  `.ai-reply`, `.ai-opt-row`, mobile textarea sizing),
  `tests/browser_test.py`, `tests/auth_gate_test.py`,
  `tests/mobile_test.py`.

## Phase 3.2 — AI Task Analyzer in the dashboard

The second AI section in the dashboard. It calls only
`POST /api/ai/task-analyzer` (Phase 2.2) — no backend change
was needed for Phase 3.2.

- UI: a nav button `data-section="ai-task"` in the existing
  "AI Assistant" group, and a section
  `<section id="ai-task">` following the existing section
  pattern (`<h2>`, `.muted` description, `.card` with the
  form, an action button, `<div id="aiTaskMsg">`, a warning
  div and the reply div). The section is protected by the
  existing auth gate: it is NOT in `PUBLIC_SECTIONS`
  (landing, auth only), the nav button is hidden by the
  logged-out body class, and the server still returns 401
  without a session.
- Form: a textarea for the task description, an optional
  title, optional urgency and importance (number inputs,
  1–10), an optional deadline as a plain text field, and an
  optional status dropdown (Pending / In progress / Done).
  The deadline is deliberately NOT a date picker: the server
  does no date validation on it, so any text up to 100 bytes
  is accepted.
- Validation (client-side, mirrors the server): description
  trimmed, non-empty, max **4000 UTF-8 BYTES** — counted
  with `TextEncoder`, not characters. Title trimmed,
  non-empty, max **500 bytes**. Urgency and importance must
  be whole numbers from 1 to 10, sent as JSON numbers.
  Deadline trimmed, non-empty, max **100 bytes**. Status is
  only ever one of `pending`, `in-progress`, `done` (the
  server also accepts the aliases `in_progress` and
  `completed`, but the UI never sends them). Empty optional
  fields are omitted from the request entirely. Validation
  errors are shown immediately, before any network call.
- Newline sanitization: `\r`, `\n`, `\t` and other control
  characters (U+0000–U+001F, U+007F) are replaced with spaces
  BEFORE sending, because the backend's old JSON helpers
  (`jsonStringField`, Phase 2.1–2.4) do NOT decode escapes —
  a `\n` in the request body would otherwise arrive as the
  letter `n`. The byte-length and sanitization helpers are
  shared with Phase 3.1.
- Reply: rendered with `esc()` into the reply div (never raw
  `innerHTML`); line breaks are preserved by the `.ai-reply`
  CSS class (`white-space: pre-wrap`). The `history_id` is
  shown next to the success message. If `history_id` is 0,
  the reply is shown AND a warning is shown that the reply
  was received but was NOT saved to AI history (this endpoint
  has no history read-back check — a failed save can still
  return 200 with `history_id` 0).
- Loading/error states: the Analyse button is disabled and
  shows "Thinking…" while the call runs (double-submit
  blocked); an error clears any stale reply. `400
  {"error":"invalid input"}` shows a friendly "Invalid
  input" message; `401` is handled by the shared `api()`
  (forced logout to Login); `501` explains that AI needs
  the C++ server; `502`/`503`/`504` show the server's
  message with a short note. No API key is ever sent,
  logged or shown by the frontend.
- Files: `dashboard/index.html`, `dashboard/app.js`,
  `tests/browser_test.py`, `tests/auth_gate_test.py`,
  `tests/mobile_test.py`. No `dashboard/style.css` change
  was needed: the 3.1 `textarea` and `.ai-reply` rules and
  the existing `input`/`select` styling (including the
  44px mobile tap targets) already cover this form.

## Phase 3.3 — AI Study Planner in the dashboard

The third AI section in the dashboard. It calls only
`POST /api/ai/study-planner` (Phase 2.3) — no backend change
was needed for Phase 3.3.

- UI: a nav button `data-section="ai-study"` in the existing
  "AI Assistant" group, and a section
  `<section id="ai-study">` following the existing section
  pattern (`<h2>`, `.muted` description, `.card` with the
  form, action buttons, `<div id="aiStudyMsg">`, a warning
  div and the reply div). The section is protected by the
  existing auth gate: it is NOT in `PUBLIC_SECTIONS`
  (landing, auth only), the nav button is hidden by the
  logged-out body class, and the server still returns 401
  without a session.
- Form: dynamic subject rows (one row at first, "Add subject"
  adds up to 10, each row removable), a number input for
  hours per day, an optional exam date (`<input type="date">`,
  which produces `YYYY-MM-DD`), and an optional description
  textarea. The "Make study plan" button sits in the same
  actions row as "Add subject".
- Validation (client-side, mirrors the server): at least one
  subject, each trimmed, non-empty, max **200 UTF-8 BYTES**
  (counted with `TextEncoder`, not characters); at most 10
  subjects. Subjects are deduped case-insensitively before
  sending (first occurrence wins, like the server); the
  success message says how many unique subjects were sent,
  and a note is shown when duplicates were removed. Hours
  per day must be a plain decimal number from **0.5 to 24**,
  sent as a JSON number — exponent notation (`1e3`) and
  dotted junk are rejected client-side because the server's
  `jsonNumberField` truncates them. The exam date must be a
  strict `YYYY-MM-DD` real calendar date, today or in the
  future (checked against the user's local date; the server,
  which checks against its own local date, is the authority).
  The description is trimmed, non-empty, max **4000 bytes**.
  Empty subject rows are ignored, never sent. Validation
  errors are shown immediately, before any network call.
- Newline sanitization: `\r`, `\n`, `\t` and other control
  characters (U+0000–U+001F, U+007F) are replaced with spaces
  BEFORE sending, because the backend's old JSON helpers
  (`jsonStringField`, Phase 2.1–2.4) do NOT decode escapes —
  a `\n` in the request body would otherwise arrive as the
  letter `n`. The byte-length and sanitization helpers are
  shared with Phase 3.1.
- Reply: rendered with `esc()` into the reply div (never raw
  `innerHTML`); line breaks are preserved by the `.ai-reply`
  CSS class (`white-space: pre-wrap`). The `history_id` is
  shown next to the success message. This endpoint verifies
  the history save (read-back) — a failed save is a 502,
  never a 200 — but if `history_id` is ever 0, the reply is
  shown AND the same "not saved" warning as in 3.1/3.2.
- Loading/error states: the button is disabled and shows
  "Thinking…" while the call runs (double-submit blocked);
  an error clears any stale reply. `400
  {"error":"invalid input"}` shows a friendly "Invalid
  input" message; `401` is handled by the shared `api()`
  (forced logout to Login); `501` explains that AI needs
  the C++ server; `502`/`503`/`504` show the server's
  message with a short note. No API key is ever sent,
  logged or shown by the frontend.
- Files: `dashboard/index.html`, `dashboard/app.js`,
  `tests/browser_test.py`, `tests/auth_gate_test.py`,
  `tests/mobile_test.py`. No `dashboard/style.css` change
  was needed: the 3.1 `textarea` and `.ai-reply` rules, the
  `.ai-opt-row` rules (reused for the subject rows) and the
  existing `input`/`select` styling (including the 44px
  mobile tap targets) already cover this form.

## Phase 3.4 — AI Problem Solver in the dashboard

The fourth AI section in the dashboard. It calls only
`POST /api/ai/problem-solver` (Phase 2.4) — no backend change
was needed for Phase 3.4.

- UI: a nav button `data-section="ai-problem"` in the existing
  "AI Assistant" group, and a section
  `<section id="ai-problem">` following the existing section
  pattern (`<h2>`, `.muted` description, `.card` with the
  form, action button, `<div id="aiProblemMsg">`, a warning
  div and the reply div). The section is protected by the
  existing auth gate: it is NOT in `PUBLIC_SECTIONS`
  (landing, auth only), the nav button is hidden by the
  logged-out body class, and the server still returns 401
  without a session.
- Form: a single problem textarea and a "Solve problem"
  button. The problem is the only field — there is no
  `input` alias in the UI (the server accepts it, but the
  UI only ever sends `problem`).
- Validation (client-side, mirrors the server): the problem
  is trimmed, non-empty, max **4000 UTF-8 CODE POINTS**
  (counted with `[...str].length`, NOT with `TextEncoder`
  bytes and NOT with `str.length`, so astral characters
  count as one). This is the key difference from 3.1–3.3:
  a 4000-Bengali-character problem is about 12000 bytes
  and is VALID — the 2.4 change to `gemini_client.cpp`
  (the 8000-character prompt budget counts code points)
  exists exactly so this works. Validation errors are
  shown immediately, before any network call.
- Newline sanitization: `\r`, `\n`, `\t` and other control
  characters (U+0000–U+001F, U+007F) are replaced with spaces
  BEFORE sending, because the backend's old JSON helpers
  (`jsonStringField`, Phase 2.1–2.4) do NOT decode escapes —
  a `\n` in the request body would otherwise arrive as the
  letter `n`. The sanitization helper is shared with
  Phase 3.1.
- Reply: rendered with `esc()` into the reply div (never raw
  `innerHTML`); line breaks are preserved by the `.ai-reply`
  CSS class (`white-space: pre-wrap`). The `history_id` is
  shown next to the success message. This endpoint verifies
  the history save (read-back) — a failed save is a 502,
  never a 200 — but if `history_id` is ever 0, the reply is
  shown AND the same "not saved" warning as in 3.1–3.3.
- Loading/error states: the button is disabled and shows
  "Thinking…" while the call runs (double-submit blocked);
  an error clears any stale reply. `400
  {"error":"invalid input"}` shows a friendly "Invalid
  input" message; `401` is handled by the shared `api()`
  (forced logout to Login); `501` explains that AI needs
  the C++ server; `502`/`503`/`504` show the server's
  message with a short note. No API key is ever sent,
  logged or shown by the frontend.
- Files: `dashboard/index.html`, `dashboard/app.js`,
  `tests/browser_test.py`, `tests/auth_gate_test.py`,
  `tests/mobile_test.py`. No `dashboard/style.css` change
  was needed: the 3.1 `textarea` and `.ai-reply` rules and
  the existing `input` styling (including the 44px mobile
  tap targets) already cover this form.

## Phase 3.5 — AI Budget Assistant in the dashboard

The fifth AI section in the dashboard. It calls only
`POST /api/ai/budget` (Phase 2.5) — no backend change
was needed for Phase 3.5.

- UI: a nav button `data-section="ai-budget"` in the existing
  "AI Assistant" group, and a section
  `<section id="ai-budget">` following the existing section
  pattern (`<h2>`, `.muted` description, `.card` with the
  form, action buttons, `<div id="aiBudgetMsg">`, a warning
  div and the reply div). The section is protected by the
  existing auth gate: it is NOT in `PUBLIC_SECTIONS`
  (landing, auth only), the nav button is hidden by the
  logged-out body class, and the server still returns 401
  without a session.
- Form: an income number input, dynamic expense rows (one row
  at first, "Add expense" adds up to 20, each row removable,
  category + amount), three savings-goal inputs (name, target,
  already saved) and an optional notes textarea. The "Review
  my budget" button sits in the same actions row as
  "Add expense".
- Validation (client-side, mirrors the server): at least one
  meaningful field is required — `{}` and `{"expenses": []}`
  alone are 400. **Income 0 counts as provided** (only an
  empty income field means "not provided"). Numbers are
  validated with a strict JSON-number shape (the same shapes
  the server's `parseStrictNumber` accepts: no leading zeros,
  no `+`, no `NaN`/`Infinity`, no `1e999`) and sent as JSON
  numbers, never strings. Each expense needs BOTH a category
  (non-empty, max 100 UTF-8 code points) and an amount
  (0–1,000,000,000); empty rows are ignored. A savings goal
  needs ALL THREE sub-fields (name max 200 code points,
  target over 0, saved 0 or more) or none at all. Notes are
  max 2000 UTF-8 code points. Validation errors are shown
  immediately, before any network call.
- Newlines are safe here: the budget route decodes JSON
  escapes properly (unlike 2.1–2.4), so notes keep their line
  breaks; control characters are still replaced with spaces
  for consistency, using the shared 3.1 helper.
- Reply: rendered with `esc()` into the reply div (never raw
  `innerHTML`); line breaks are preserved by the `.ai-reply`
  CSS class (`white-space: pre-wrap`). The `history_id` is
  shown next to the success message. This endpoint verifies
  the history save (read-back) — a failed save is a 502,
  never a 200 — but if `history_id` is ever 0, the reply is
  shown AND the same "not saved" warning as in 3.1–3.4. The
  server computes all figures deterministically (totals,
  remaining, deficit, savings rate, goal progress, months to
  goal) — Gemini never calculates, so the UI does not display
  figures separately.
- Loading/error states: the button is disabled and shows
  "Thinking…" while the call runs (double-submit blocked);
  an error clears any stale reply. `400
  {"error":"invalid input"}` shows a friendly "Invalid
  input" message; `401` is handled by the shared `api()`
  (forced logout to Login); `501` explains that AI needs
  the C++ server; `502`/`503`/`504` show the server's
  message with a short note. No API key is ever sent,
  logged or shown by the frontend.
- Files: `dashboard/index.html`, `dashboard/app.js`,
  `tests/browser_test.py`, `tests/auth_gate_test.py`,
  `tests/mobile_test.py`. No `dashboard/style.css` change
  was needed: the 3.1 `textarea`, `.ai-reply` and
  `.ai-opt-row` rules and the existing `input` styling
  (including the 44px mobile tap targets) already cover
  this form.

## Tests

```sh
python3 tests/gemini_test.py        # mock Gemini server; no real API call
python3 tests/ai_endpoints_test.py  # Daily Decision + history (mock)
```

`tests/gemini_test.py` builds the server, runs a C++ harness
against a local mock Gemini server (success, invalid JSON,
HTTP 500, HTTP 401, timeout, empty/oversized prompt, missing
key), checks the no-libcurl stub, and checks `/api/ai/health`
with and without a key. `tests/ai_endpoints_test.py` checks
the Daily Decision, Task Analyzer, Study Planner, Problem
Solver, Budget and Habit endpoints (auth, validation, failure
mapping, computed figures for Budget and Habit), history
storage and per-user isolation, and the Python server's 501
for `/api/ai/*`. The Budget checks include strict number
validation (strings, booleans, null, NaN, Infinity,
malformed numbers and trailing junk are rejected without
calling Gemini), Unicode-aware limits (2000 Bengali
characters accepted, 2001 rejected), the deficit wording,
the income-0 savings-rate N/A case, the 0.1 + 0.2
precision case, the maximum-size request inside the
8000 code point prompt budget, and the txt-mode
history-save failure (data dir removed mid-run -> 502).
The Habit checks include the validation matrix
(missing/empty/non-string/over-long habit, bad
target_streak, bad frequency, over-long input, bad
`today`), Unicode boundaries (100 Bengali characters
accepted, 101 rejected; input 2000/2001), the
server-computed figures read back from the prompt the
mock received (daily streak, gap and duplicate cases,
30-day rate, target reached; weekly streak, missed-week
reset, several logs in one week, Sunday-plus-Monday,
the 2025-12-29/2026-01-04 year-boundary week, 8-week
rate), the `today` timezone cases (server date +1/+2/−1
accepted, +3 rejected, malformed rejected, absent uses
the server date), future-dated logs, non-mutation of
habit data and of `/api/habits/streak`, and the
txt-mode history-save failure for the habit route.
The Postgres-mode history-save failure is verified
manually, not in the suite: DROP TABLE ai_history
mid-run -> 502, restart -> 200. The only key string in
the tests is the fake value `"test-key"`.
