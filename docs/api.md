# API Reference — Personal Decision & Problem Solver

**Server documented:** `dashboard/cpp_server.cpp` (C++ backend, 2,748 lines), branch
`phase4-backend-integration` (from `main` at `c698060`). The Python fallback
server (`dashboard/server.py`) implements the same data API over txt files;
differences are noted in §8.

**Status: the Render deployment is BLOCKED** (a live creation attempt on
2026-11-09 demanded a credit/debit card at Free service creation; no service
exists, no card was added). The demo base URL is the local server
`http://127.0.0.1:8000/`. No URL is invented here.

## 1. Conventions

- **Base URL:** the server origin (same origin serves the dashboard and the
  API). Locally `http://127.0.0.1:8000`; in production the Render service URL.
  The frontend reads it from `window.PDPS_API_BASE` (default `""` = same origin).
- **Auth:** after login, send `Authorization: Bearer <token>` on every
  authenticated request. The token lives in `sessionStorage` in the dashboard.
- **Bodies:** JSON objects. Request bodies are capped at 1 MiB (larger → 413).
- **Error shape:** all errors are `{"error":"<message>"}` with an HTTP status.
  Error messages never contain a password or the Gemini API key.
- **Unknown endpoint:** 404 `{"error":"Unknown API endpoint."}`.
- **Unknown/extra JSON fields are silently ignored** by every route.
- **Numbers:** money is formatted with two decimals (`fmtNum`); `-0.00` is
  normalised to `0.00`.

### Common status codes

| Code | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 400 | Validation failed (message explains the rule) |
| 401 | No valid session — `{"error":"Please log in first."}` (or "Invalid username or password." on login) |
| 403 | Logged in, but ADMIN-only (users/admin endpoints) |
| 404 | Not found — also used for cross-user access (a row belonging to another user is reported as not found, never as forbidden) |
| 413 | Request body over 1 MiB |
| 429 | Login rate limit (5 failed logins per username in 300 s) |
| 501 | Python server only: AI endpoints are not implemented there |
| 502 | AI request failed (incl. AI history save failure in 2.3–2.6) |
| 503 | AI unavailable / misconfigured / rate-limited (see §7) |
| 504 | AI request timed out |

## 2. Public endpoints (no login needed)

### `GET /api/health`

Health check (used by Render). Returns backend type and storage mode, nothing else.

```json
{"ok": true, "backend": "C++", "storage": "postgres"}
```

`storage` is `"postgres"` when `DATABASE_URL` is set, otherwise `"txt"`.
Python server: `{"ok": true, "backend": "Python", "storage": "txt"}`.

### `POST /api/register`

```json
{"username": "alice", "password": "Alice1234"}
```

- Username: non-empty, no whitespace, control characters, or `|`.
- Password: at least 8 characters, with a letter and a digit.
- Optional `confirm_password`: when supplied it must equal `password`, otherwise 400 `"Passwords do not match."` (auth fix, 2026-11-09 — the dashboard form always sends it).
- **The first registered user becomes `ADMIN`; every later user is `USER`.**
- Success: **201** `{"username": "alice", "role": "ADMIN"}`.
- Existing username → 400 `"Username already exists."`
- Database save failure (Postgres mode only) → 500 `"Could not create the account. Please try again later."` (registration bug fix, 2026-11-09 — this used to be wrongly reported as "already exists"; the real database error is printed to the server console, never sent to the client).
- User store cannot be read (dead database, or `users.txt` exists but is unreadable) → 500 `"Could not create the account. Please try again later."`, no account is created, and no `ADMIN` is granted (C1/C2 fix, 2026-11-10 — the store failure used to look like "no users yet", so the next registrant became `ADMIN`). A missing `users.txt` is genuinely empty: the first registrant is `ADMIN`.

### `POST /api/login`

```json
{"username": "alice", "password": "Alice1234"}
```

- Success: **200** `{"username": "alice", "role": "ADMIN", "token": "<session token>"}`.
- Sessions are in-memory tokens with a 12-hour TTL. They do not survive a
  server restart.
- Wrong credentials → 401 `"Invalid username or password."` (and the failure
  is counted for rate limiting).
- 5 failed attempts for one username in 300 s → 429 `"Too many failed
  logins. Try again later."`
- A plaintext legacy credential that matches is upgraded to a PBKDF2 hash on
  this login.

### `POST /api/logout`

No body needed. Erases the Bearer token if one is sent.

```json
{"ok": true}
```

## 3. Authenticated endpoints — session and overview

Every endpoint in §§3–6 requires a valid session (401 otherwise).

### `GET /api/me`

```json
{"username": "alice", "role": "ADMIN"}
```

### `GET /api/overview`

Dashboard summary counts for the caller only (owner-filtered).

```json
{
  "username": "alice", "role": "ADMIN",
  "decisions": 3, "tasks": 5, "tasksPending": 2,
  "income": 10000.00, "expense": 1000.00, "balance": 9000.00,
  "savingsGoals": 1, "savingsTarget": 10000.00, "savingsSaved": 1000.00,
  "habits": {"Reading": 4}
}
```

### `GET /api/info`

```json
{"backend": "C++", "server": "cpp_server.cpp", "storage": "postgres",
 "dataFiles": ["users.txt", "decisions.txt", "tasks.txt", "transactions.txt",
  "savings_goals.txt", "habit_log.txt", "daily_report.txt",
  "financial_report.txt", "financial_report.csv", "error_log.txt"]}
```

## 4. Authenticated endpoints — decisions, tasks, money, habits

All list endpoints return **only the caller's own rows** (plus legacy ownerless
rows visible only to a sole user). Cross-user access returns 404.

### Decisions

**`GET /api/decisions`** — optional query `?search=<text>` (matches title or
type, case-insensitive) and `?type=<type>`. Returns an array:

```json
[{"id": "1", "date": "2026-11-09", "type": "Daily", "priority": 43,
  "title": "Daily decision: Complete this task first."}]
```

Note: the response has **no `owner` field**.

**`POST /api/decisions`** — `{"type": "Daily", "priority": 43, "title": "..."}`.
`type` defaults to `"Daily"` when empty; `priority` must be 0–1000; `title`
is required. Success: **201** with the created decision object.

**`DELETE /api/decisions/{id}`** — success: 200 `{"deleted": "1"}`.
Someone else's id or a missing id → 404 `"Decision ID not found."`
If the store cannot be rewritten, the delete answers 500
`"Could not delete the decision. Please try again later."` instead of a
false 200 (template-delete fix, 2026-11-10).

### Daily decision, priority, multi-task

**`POST /api/daily-decision`** — the non-AI calculator (menu 9).
Request: `{"availableTime": 120, "requiredTime": 60, "urgency": 8,
"importance": 9, "energy": 7}`. Ranges: time 1–1440, urgency/importance/energy
1–10. Score = urgency×2 + importance×3 (max 50). Response:

```json
{"suggestion": "Complete this task first.", "score": 43,
 "record": {"id": "1", "date": "2026-11-09", "type": "Daily",
  "priority": 43, "title": "Daily decision: Complete this task first."}}
```

The suggestion branches: required > available → "Divide the task into smaller
parts."; urgency ≥ 8 and importance ≥ 8 → "Complete this task first.";
importance ≥ 8 and energy ≤ 4 → "Take a short break, then do this task.";
urgency ≥ 7 → "Complete this task soon."; otherwise "Schedule this task for later."
The decision is saved as type `Daily`.

**`POST /api/priority`** — `{"urgency": 8, "importance": 9}` (both 1–10).
Response: `{"score": 43, "max": 50, "level": "VERY HIGH"}`.
Levels: ≥ 40 VERY HIGH, ≥ 30 HIGH, ≥ 20 MEDIUM, otherwise LOW.

**`POST /api/multi-task`** — `{"availableEnergy": 50, "availableTime": 240,
"tasks": [{"name": "Maths", "deadlineUrgency": 9, "energy": 20, "time": 60}]}`.
1–20 tasks; energy 1–100; time 1–1440; per task urgency/energy 1–10, time
1–1440. Tasks are stably sorted by deadline urgency (descending) and accepted
while the energy/time budgets fit; each accepted task is saved as a `MultiTask`
decision with priority urgency×5. Response:
`{"recommended": [...], "skipped": [...], "remainingEnergy": 30,
"remainingTime": 180}`.

### Tasks

**`GET /api/tasks`** — array of:

```json
[{"id": "1", "title": "Finish maths homework", "urgency": 8,
  "importance": 9, "deadline": "2026-11-14", "status": "Pending",
  "score": 43}]
```

`score` is urgency×2 + importance×3.

**`POST /api/tasks`** — `{"title": "...", "urgency": 8, "importance": 9,
"deadline": "2026-11-14"}`. Title required; urgency/importance 1–10;
deadline must be a real `YYYY-MM-DD` date or blank. New tasks start as
`"Pending"`. Success: **201** with the task object.

**`PATCH /api/tasks/{id}`** — `{"status": "In Progress"}`. Status must be
`Pending`, `In Progress`, or `Completed`. Someone else's id → 404
`"Task not found."`

**`DELETE /api/tasks/{id}`** — 200 `{"deleted": "1"}`; someone else's id → 404.
If the store cannot be rewritten, the delete answers 500
`"Could not delete the task. Please try again later."` instead of a false
200 (template-delete fix, 2026-11-10).

### Budget and transactions

**`GET /api/budget?income=10000&expenses=1000`** — both query params required,
numbers ≥ 0. Response:

```json
{"income": 10000.00, "expenses": 1000.00, "remaining": 9000.00,
 "decision": "Save money for the future."}
```

Decision: remaining < 0 → `"Reduce expenses."`; = 0 → `"Income equals
expenses."`; > 0 → `"Save money for the future."` This endpoint only
calculates; it does not save anything.

**`GET /api/transactions`** — array of
`{"date": "2026-11-09", "type": "income", "category": "Salary",
"amount": 10000.00, "note": ""}`.

**`POST /api/transactions`** — `{"date": "2026-11-09", "type": "income",
"category": "Salary", "amount": 10000, "note": ""}`. Date must be a real
`YYYY-MM-DD`; type `income` or `expense`; category non-empty; amount ≥ 0.
Success: **201** with the transaction object.

### Savings goals

**`GET /api/savings`** — `[{"name": "laptop", "target": 10000.00, "saved": 1000.00}]`.

**`POST /api/savings`** — `{"name": "laptop", "target": 10000}`. Target must
be > 0; a goal with the same name for this user → 400. Success: **201**.

**`POST /api/savings/add`** — `{"name": "laptop", "amount": 1000}`. Amount
must be > 0. Unknown goal → 404 `"Goal not found."`

### Habits

**`GET /api/habits`** — grouped by habit:
`[{"habit": "Reading", "dates": ["2026-11-07", "2026-11-08", "2026-11-09"]}]`.

**`POST /api/habits`** — `{"habit": "Reading", "date": "2026-11-09"}`. Date
defaults to today when omitted; must be a real `YYYY-MM-DD`. Success: **201**
with the streak object (same shape as below).

**`GET /api/habits/streak?habit=Reading`** — habit name required.

```json
{"habit": "Reading", "total": 3, "streak": 3, "latest": "2026-11-09"}
```

`streak` counts consecutive days ending at the latest log date. No logs →
`{"habit": "Reading", "total": 0, "streak": 0, "latest": null}`.

### Reports, backup, restore, export

**`GET /api/reports?month=2026-11`** or **`?week_end=2026-11-09`** — one of
the two is required. `month` must be `YYYY-MM`; `week_end` a real date (the
7-day window ending on it). Response:
`{"label": "Monthly report for 2026-11", "transactions": [...],
"income": 10000.00, "expense": 1000.00, "balance": 9000.00, "count": 2}`.

**`POST /api/backup`** — backs up only the caller's own decisions; other
users' backup rows and hidden legacy rows are untouched. Response:
200 `{"backedUp": 3}`. No decision file (txt mode) → 400.

**`POST /api/restore`** — `{"confirm": true}` is required in the body;
without it → 400 and nothing changes. Replaces only the caller's decisions
with their backup; other users' decisions are preserved; malformed rows and
id collisions are skipped and counted. Response:
200 `{"restored": 3, "skipped": 0}`. No backup for this user → 400 and
nothing changes. The backup itself is never deleted by a restore.

**`GET /api/export?format=txt|csv`** — `format` defaults to `txt`.
Response: 200 `{"format": "txt", "filename": "financial_report.txt",
"content": "PERSONAL FINANCIAL REPORT\n..."}`. TXT = header + raw
pipe-delimited lines; CSV = `Date,Type,Category,Amount,Note` header with the
note quoted. Owner-filtered; in txt mode the file is also written to the data
dir.

### Study planner, time allocation, explanation, deadlines, compare

**`POST /api/study-planner`** (non-AI calculator) — `{"subject": "Maths",
"days": 30, "hours": 2}`. Days 1–365, hours 1–24. Response:
`{"subject": "Maths", "days": 30, "hoursPerDay": 2, "totalHours": 60,
"plan": [{"day": 1, "text": "Day 1: Maths - 2 hour(s)"}, ...]}`.

**`POST /api/time-allocation`** — `{"sleep": 8, "study": 6, "work": 4,
"other": 2}`. Each 0–24. Response includes `total`, `remaining` (24 − total),
and `warning` (`"Total exceeds 24 hours!"` when total > 24, else `null`).

**`POST /api/decision-explanation`** — `{"urgency": 8, "importance": 9}`.
Response: `{"urgency": 8, "importance": 9, "score": 43,
"formula": "Formula: (Urgency x 2) + (Importance x 3)",
"calculation": "Calculation: (8 x 2) + (9 x 3) = 43/50",
"explanation": "Very high priority.", "recommendation": "Complete this task first."}`

**`GET /api/deadlines`** — optional `?today=YYYY-MM-DD` (defaults to the
server date). Returns the caller's non-completed tasks with an `alert`:
`OVERDUE`, `DUE TODAY`, `UPCOMING`, or `CHECK` (malformed deadline).

**`POST /api/compare-options`** — `{"name1": "A", "benefit1": 8, "cost1": 3,
"risk1": 2, "name2": "B", "benefit2": 6, "cost2": 4, "risk2": 3}`. All six
numbers 1–10. Score = benefit×3 − cost − risk. Response:
`{"name1": "A", "score1": 19, "name2": "B", "score2": 11, "suggested": "A",
"equal": false}` (`suggested` is `null` on a tie).

### Problem solver, daily summary, habit calculators, error log

**`POST /api/problem-solver`** (non-AI calculator) — `{"problem": "Noisy
roommate", "difficulty": 3, "time": 30}`. Difficulty 1–5, time > 0 minutes.
Response: `{"suggestion": "...", "record": {...}}` — the problem is saved as
a `Problem` decision record. Suggestion branches: difficulty ≤ 2 and time ≥ 15
→ "Solve the problem step by step."; difficulty ≥ 4 → "Divide the problem into
smaller tasks."; time < 15 → "Make a short and simple plan."; otherwise
"Plan your work and start solving."

**`POST /api/daily-summary`** — `{"income": 10000, "expenses": 1000,
"habitsCompleted": 3, "habitsPlanned": 4}`. Appends a daily report line and
returns `{"income": 10000.00, "expenses": 1000.00, "balance": 9000.00,
"habitRate": 75.00}`.

**`POST /api/habit-decision`** — `{"completed": 3, "planned": 4}`. Returns
`{"percentage": 75.00, "message": "Good progress! Keep going."}` (all done →
"Excellent! You completed all planned habits."; under 50% → "Try making a
simpler plan tomorrow."). Nothing is saved.

**`POST /api/habit-streak-calc`** — `{"previousDays": 4, "completedToday": 1}`.
Returns `{"streak": 5, "message": ""}` (completedToday 0 → streak 0 and
"Start a new streak tomorrow!"). Nothing is saved.

**`POST /api/savings-calculator`** — `{"target": 10000, "current": 1000,
"monthly": 1500}`. Returns `{"remaining": 9000.00, "months": 6, "message": ""}`
(goal reached → `{"remaining": 0, "months": 0, "message": "Congratulations!
Your goal is complete."}`). Nothing is saved.

**`GET /api/error-log`** — array of generic log lines (strings). By design,
any logged-in user receives these lines; log messages never contain passwords.

## 5. Admin endpoints

**`GET /api/users`** — ADMIN only (others → 403 `"Only an ADMIN can list
users."`). Returns username and role only, never passwords:
`[{"username": "alice", "role": "ADMIN"}, {"username": "bob", "role": "USER"}]`.

**`GET /api/admin`** — ADMIN only (others → 403 `"Only an ADMIN can view the
admin panel."`). Response:
`{"total": 2, "admins": 1, "users": 1, "list": [{"username": "alice",
"role": "ADMIN"}, ...]}`.

**`POST /api/change-password`** — `{"currentPassword": "...", "newPassword":
"..."}`. Wrong current password → 400. New password needs 8+ characters with
a letter and a digit. Success: 200 `{"ok": true}`.

There is **no** promote/demote/reset-password endpoint (deliberate).

## 6. AI endpoints (C++ server only)

All AI endpoints require a login (401 otherwise) and return
`{"error":"invalid input"}` with status 400 on validation failure — the
rejected value is never echoed, and Gemini is never called. Unknown fields
are ignored. History is saved **only on Gemini success**; the stored prompt
is the user's data (never the server instruction, never the key).

Success shape (all six feature endpoints):

```json
{"reply": "<Gemini reply text>", "history_id": 12}
```

`history_id` is the `ai_history` row id. In Postgres mode a failed save is a
502 (2.3–2.6) or `history_id: 0` (2.1/2.2 — see quirks in §7).

### `GET /api/ai/health`

```json
{"available": true, "configured": true, "model": "gemini-3-flash-preview"}
```

`available` = the libcurl client was compiled in; `configured` = a
`GEMINI_API_KEY` is set. The key is never in the response.

### `GET /api/ai/history?limit=50`

Newest first, only the caller's own rows. `limit` is clamped to 1–100
(default 50). Empty: `{"history": []}`.

```json
{"history": [{"id": 12, "feature": "daily-decision",
  "prompt": "Should I study maths or physics tonight?",
  "response": "Study maths tonight because ...",
  "created_at": "2026-11-09 14:30:00"}]}
```

### `DELETE /api/ai/history/{id}`

Deletes only the caller's own row. Success: 200 `{"deleted": true}`.
Someone else's row, a missing id, or a non-numeric id → 404
`{"error":"History entry not found."}` The dashboard re-reads the
history list from the server after a delete (template-delete fix,
2026-11-10): the list on screen is always the server truth, never a
locally-filtered copy that could come back on refresh.

### `POST /api/ai/daily-decision` — AI Daily Decision Assistant

```json
{"input": "Should I study maths or physics tonight?",
 "options": ["maths", "physics"]}
```

- `input`: required, trimmed, non-empty, **≤ 4,000 bytes**.
- `options`: optional array of strings, max 10, each ≤ 500 bytes; an empty
  array is valid.
- Gemini is asked for one clear recommendation with short reasons.
- Feature name in history: `daily-decision`. Stored prompt: input, plus
  `" [options: maths; physics]"` when options are given.
- **No history read-back verification** (see §7).

### `POST /api/ai/task-analyzer` — AI Task Analyzer

```json
{"description": "Finish maths homework before Friday",
 "title": "Maths homework", "urgency": 8, "importance": 9,
 "deadline": "2026-11-14", "status": "pending"}
```

- `description`: required (or `input` as a compatibility alias;
  `description` wins when both are present), **≤ 4,000 bytes**.
- `title`: optional, ≤ 500 bytes. `urgency` / `importance`: optional strict
  integers 1–10 (rejects `10.5`, `"high"`, trailing junk).
- `deadline`: optional, ≤ 100 bytes. **It is NOT date-validated** — any
  string up to 100 bytes is accepted (see §7).
- `status`: optional, must be `pending`, `in-progress`, or `done`;
  aliases `in_progress` → `in-progress`, `completed` → `done`.
- Gemini is asked for five sections: Task Analysis, Priority Recommendation,
  Urgency Assessment, Suggested Next Action, Explanation.
- Feature name in history: `task-analyzer`.
- **No history read-back verification** (see §7).

### `POST /api/ai/study-planner` — AI Study Planner

```json
{"subjects": ["Maths", "Physics"], "hours_per_day": 2,
 "exam_date": "2026-12-01", "description": "Final exams"}
```

- `subjects`: **required**, array of strings, 1–10, each non-empty after
  trim, ≤ 200 bytes; duplicates are removed case-insensitively (first
  occurrence kept).
- `hours_per_day`: **required**, a JSON number, 0.5–24. Send a plain number,
  never a string.
- `exam_date`: optional, strict `YYYY-MM-DD`, a real date, today or in the
  future (by the **server's** local date).
- `description` / `input`: optional, ≤ 4,000 bytes (`description` wins).
- Gemini is asked for five sections: Study Plan, Daily Schedule, Subject
  Priorities, Revision Strategy, Explanation.
- Feature name in history: `study-planner`.
- **History-save read-back verification: yes.** A failed save → 502.

### `POST /api/ai/problem-solver` — AI Problem Solver

```json
{"problem": "My roommate plays loud music while I study."}
```

- `problem`: required (or `input` as a compatibility alias; `problem` wins),
  **≤ 4,000 UTF-8 code points** (not bytes — 4,000 Bengali characters are
  accepted).
- Gemini is asked for five sections: Problem Analysis, Possible Solutions,
  Recommended Solution, Action Steps, Explanation.
- Feature name in history: `problem-solver`. Stored prompt: the problem text
  only.
- **History-save read-back verification: yes.** A failed save → 502.

### `POST /api/ai/budget` — AI Budget Assistant

```json
{"income": 10000,
 "expenses": [{"category": "Food", "amount": 3000}],
 "savings_goal": {"name": "laptop", "target": 50000, "saved": 10000},
 "input": "I want to save faster."}
```

- The body must be a JSON object; all fields are optional, but **at least
  one meaningful field is required** (`{}` → 400; `{"expenses": []}` alone
  → 400).
- `income`: strict JSON number, 0–1,000,000,000. Strings, booleans, null,
  `NaN`, `Infinity`, `01`, `+100`, `1.2.3`, `1e999` are rejected; `1e2` is
  accepted as 100. **Income 0 counts as a meaningful field.**
- `expenses`: array, max 20 items; each item needs `category` (non-empty,
  ≤ 100 code points) and `amount` (number 0–1e9).
- `savings_goal`: when present, **all three** sub-fields are required:
  `name` (≤ 200 code points), `target` (> 0, ≤ 1e9), `saved` (≥ 0, ≤ 1e9;
  may exceed target).
- `input`: optional, ≤ 2,000 code points.
- **Gemini never calculates.** The server computes the figures
  deterministically (2-decimal rounding): total expenses, remaining, savings
  rate (N/A when income is absent or 0), goal progress %, months to goal
  (N/A unless remaining > 0 and the goal is unreached; `"0.00 (goal already
  reached)"` when reached). A negative remaining is shown explicitly as
  `"-1500.00 (DEFICIT: expenses exceed income by 1500.00)"`.
- Gemini is asked for five sections: Income & Expense Analysis, Budget Plan,
  Savings Goal Progress, Spending Recommendations, Explanation.
- Feature name in history: `budget`.
- **History-save read-back verification: yes.** A failed save → 502.

### `POST /api/ai/habit` — AI Habit Assistant

```json
{"habit": "Reading", "target_streak": 30, "frequency": "daily",
 "input": "I keep forgetting at night.", "today": "2026-11-09"}
```

- `habit`: **required**, trimmed, non-empty, ≤ 100 UTF-8 code points;
  control characters or `|` → 400.
- `target_streak`: optional strict integer 1–365.
- `frequency`: optional `"daily"` (default) or `"weekly"`.
- `input`: optional, ≤ 2,000 code points.
- `today`: optional strict `YYYY-MM-DD`, **within ±2 days of the server's
  local date** (else 400). The server date is the authority, not the user's
  local date.
- Server-side figures (read-only on habit data; Gemini only advises):
  daily streak = consecutive days; weekly streak = consecutive active ISO
  weeks (Monday–Sunday); completion rate = last 30 days / 30 (daily) or last
  8 weeks / 8 (weekly); longest streak; days/weeks since last log. A habit
  with no logs is valid (total 0, streak 0).
- Gemini is asked for five sections: Habit Analysis, Streak Assessment,
  Improvement Plan, Motivation & Tips, Explanation.
- Feature name in history: `habit`.
- **History-save read-back verification: yes.** A failed save → 502.

## 7. AI error mapping and verified contract quirks

### Error mapping (all six AI feature endpoints)

| Gemini client error | HTTP | Message |
|---|---|---|
| `not_configured` (no key) / `unavailable` (no libcurl) | 503 | `"AI unavailable"` |
| `auth_error` (bad key / 401 from Google) | 503 | `"AI configuration error"` |
| `rate_limited` (HTTP 429 from Google) | 503 | `"AI request limit reached"` |
| `timeout` | 504 | `"AI request timed out"` |
| anything else (incl. invalid response, history-save failure in 2.3–2.6) | 502 | `"AI request failed"` |
| validation failure (any endpoint) | 400 | `"invalid input"` (value never echoed) |
| no session | 401 | `"Please log in first."` |

### Model configuration

- Default model: **`gemini-3-flash-preview`** (verified working live,
  2026-11-09). Override with the `GEMINI_MODEL` environment variable (only
  `[A-Za-z0-9._-]` accepted; anything else falls back to the default).
- `gemini-2.0-flash` and `gemini-2.5-flash` are **retired** (API 404).
- `gemini-3.8-flash` is the **production target**: it exists, but on
  2026-11-09 it answered 503 (high demand) on every attempt, so it is not
  the default yet. Select it with `GEMINI_MODEL` once it serves reliably.
- Timeouts: connect 10 s; total `GEMINI_TIMEOUT_SECS` (clamped 1–120,
  default 30). Prompt budget: 8,000 UTF-8 code points. Response cap: 1 MiB.

### Verified quirks (the frontend and any API client must respect these)

1. **Bytes vs code points.** Endpoints 2.1–2.3 (daily-decision, task-analyzer,
   study-planner) count length in **bytes**; only 2.4–2.6 (problem-solver,
   budget, habit) count **UTF-8 code points**. A 4,000-Bengali-character
   problem is accepted by problem-solver but would be rejected by
   daily-decision.
2. **Escape quirk (2.1–2.4).** The string reader used by daily-decision,
   task-analyzer, study-planner, and problem-solver does **not** decode JSON
   escapes: a `\n` in the request body arrives as the literal letter `n`,
   and `\uXXXX` stays literal. Only budget and habit decode escapes
   properly. Clients should replace newlines/tabs/control characters with
   spaces before sending text to 2.1–2.4.
3. **History-save verification differs.** Study-planner, problem-solver,
   budget, and habit verify the saved row (read-back) before returning 200;
   a failed save is a 502. Daily-decision and task-analyzer do **not**
   verify: in Postgres mode a failed save still returns 200 with
   `history_id: 0`, and in txt mode a failed save can return a success id
   with nothing persisted (pre-existing Phase 2.1 behaviour). Clients must
   treat `history_id: 0` as "reply OK, history may not contain it".
4. **Task `deadline` has no date validation** (any string ≤ 100 bytes).
   The non-AI `POST /api/tasks` deadline *is* validated — do not confuse them.
5. **Budget edges.** Income `0` counts as a meaningful field;
   `savings_goal` requires all three sub-fields when present;
   `{"expenses": []}` alone → 400; `{}` → 400.
6. **Habit `today` is ±2 days of the server date**, not the user's local date.
7. **Study `hours_per_day`** must be sent as a plain JSON number, never a
   string. (The number reader truncates exponents and trailing junk, e.g.
   `1e3` is read as `1`.)
8. **Unknown fields are silently ignored** on every endpoint.

## 8. Python fallback server differences

`dashboard/server.py` implements the same data endpoints over txt files.
Differences from the C++ server:

- Any `/api/ai/*` request → **501** `{"error":"AI requires the C++ server"}`
  (after the 401 check without a login).
- `/api/health` reports `{"ok": true, "backend": "Python", "storage": "txt"}`.
- Storage is always txt; there is no Postgres mode.
- Sessions are in-memory per server and are **not shared** with the C++
  server — run only one server at a time.

## 9. Environment variables (server)

| Variable | Meaning | Default |
|---|---|---|
| `PORT` | Port the C++ server listens on (explicit `--port` wins) | `8000` |
| `DATABASE_URL` | Postgres connection string. Set → Postgres mode (fail fast if unreachable). Unset → txt mode. Never logged. | unset (txt) |
| `CORS_ORIGINS` | Comma-separated exact origins allowed to call `/api` cross-origin (`*` is ignored with a warning) | unset (same-origin only) |
| `GEMINI_API_KEY` | Gemini API key. Read fresh per call by the C++ backend only. Never in the repo, a file, a log, or a response. | unset (AI not configured → 503) |
| `GEMINI_MODEL` | Model name in the request URL | `gemini-3-flash-preview` |
| `GEMINI_API_BASE_URL` | Gemini API base URL (test seam: point at a mock server) | `https://generativelanguage.googleapis.com/v1beta` |
| `GEMINI_TIMEOUT_SECS` | Total Gemini request timeout, clamped 1–120 s | `30` |

C++ server CLI: `cpp_server [--port 8000] [--host 127.0.0.1] [--data-dir PATH]`
(`--host 0.0.0.0` is required on Render).
