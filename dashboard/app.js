// Personal Decision & Problem Solver — dashboard frontend.
// All data comes from the backend on the same origin
// (http://127.0.0.1:8000): the C++ server by default, the Python
// server as a fallback. There is no demo or fake data: if the
// server is not running, every section shows its error instead of
// invented numbers.

let token = sessionStorage.getItem("pdps_token") || "";
let username = sessionStorage.getItem("pdps_user") || "";
// Auth gate: isLoggedIn is true ONLY after the server has verified
// a session (a successful login, or /api/me on page load/refresh).
// A token sitting in sessionStorage alone never shows the dashboard.
let isLoggedIn = false;
const PUBLIC_SECTIONS = ["landing", "auth"];

function el(id) { return document.getElementById(id); }

// SECURITY FIX: escape every user-controlled value before it is put
// into innerHTML. Without this, a decision/task title such as
// <img src=x onerror=...> would execute in another user's browser
// (stored XSS), because decisions and tasks are shared in one file.
function esc(v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function showMsg(id, text, ok) {
  const box = el(id);
  if (!box) return;
  const cls = ok ? "msg-ok" : "msg-err";
  if (id === "globalMsg") { box.innerHTML = `<div class="msg ${cls}"></div>`; box.firstChild.textContent = text; return; }
  box.className = "msg " + cls;
  box.textContent = text;
}

function clearMsg(id) {
  const box = el(id);
  if (box) { box.className = ""; box.textContent = ""; box.innerHTML = ""; }
}

// Theme: light/dark, saved in this browser only (localStorage).
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("pdps_theme", theme);
  const btn = el("themeBtn"); if (btn) btn.textContent = theme === "dark" ? "\u2600" : "\u263D";
  const sel = el("setTheme"); if (sel) sel.value = theme;
}
applyTheme(localStorage.getItem("pdps_theme") || "light");
el("themeBtn").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
// Mobile navigation drawer: open/close, backdrop tap and Escape all close it.
// Desktop layout is unchanged: the drawer styles only apply under 720px.
function setNav(open) {
  el("sidebar").classList.toggle("open", open);
  document.body.classList.toggle("nav-open", open);
  const btn = el("menuBtn"); if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
  const bd = el("navBackdrop"); if (bd) bd.classList.toggle("show", open);
}
el("menuBtn").addEventListener("click", () => setNav(!el("sidebar").classList.contains("open")));
const navBackdrop = el("navBackdrop"); if (navBackdrop) navBackdrop.addEventListener("click", () => setNav(false));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") setNav(false); });

function setLoggedIn(name) {
  username = name || "";
  el("who").textContent = name ? ("Logged in as " + name) : "";
  el("logoutBtn").classList.toggle("hidden", !name);
}

// Single place that flips the whole UI between logged-out and
// logged-in: body class (which hides protected nav buttons),
// topbar user text, and the Logout button.
function setAuthState(loggedIn, name) {
  isLoggedIn = loggedIn;
  document.body.classList.toggle("logged-in", loggedIn);
  document.body.classList.toggle("logged-out", !loggedIn);
  setLoggedIn(name || "");
  if (!loggedIn) setNav(false);
}

function clearSession() {
  token = "";
  sessionStorage.removeItem("pdps_token");
  sessionStorage.removeItem("pdps_user");
  setAuthState(false, "");
  // The AI history list is the previous user's data: never leave
  // it on screen after logout (it is reloaded on next login).
  // clearSession only ever runs from event handlers / promise
  // callbacks, i.e. after the whole script has evaluated, so the
  // aiHistoryEntries declaration below has already run.
  aiHistoryEntries = [];
  const aiList = el("aiHistoryList");
  if (aiList) aiList.innerHTML = "";
}

// Session expired / invalid on any protected call: drop the local
// token at once and send the user to the Login page (auth), never
// to a dashboard section.
function forceLogoutToLogin(message) {
  clearSession();
  if (message) showMsg("loginMsg", message, false);
  showSection("auth");
}

// API base (Route 2, Phase 1): by default "" (same origin, as
// before — local server, and the recommended Vercel /api proxy
// rewrite for production, which needs no CORS at all). For a
// direct call to a Render backend, set window.PDPS_API_BASE before
// app.js loads, for example via dashboard/api-config.js (see the
// .example file — do NOT commit a real backend URL with secrets):
//   <script>window.PDPS_API_BASE = "https://<render-service>.onrender.com";</script>
// The value is a plain origin, never a database string or secret.
const API_BASE = (typeof window !== "undefined" && window.PDPS_API_BASE ? String(window.PDPS_API_BASE) : "").replace(/\/$/, "");

// Backend-not-connected message (2026-11-06, iPhone preview 404
// investigation). On a Vercel preview there is NO backend yet:
// vercel.json rewrites only /, /index.html, /style.css and /app.js,
// and there is deliberately no /api rewrite, because no Render
// backend URL exists yet. So a same-origin /api/* call returns
// Vercel's static 404, not a backend error. Say that plainly
// instead of the cryptic "Request failed: 404", and never pretend
// the registration succeeded. When API_BASE is set (a real Render
// backend), a 404 is a real backend response and keeps the
// backend's own message.
const BACKEND_UNAVAILABLE_MSG = "Backend is not connected yet — this preview is frontend-only. No account was created. Register and Login will work after the Render backend is connected.";

async function api(path, options) {
  const res = await fetch(API_BASE + path, Object.assign({
    headers: {
      "Content-Type": "application/json",
      "Authorization": token ? "Bearer " + token : ""
    }
  }, options || {}));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 404 && !API_BASE)
      throw new Error(BACKEND_UNAVAILABLE_MSG);
    if (res.status === 401 && path !== "/api/login" && path !== "/api/register" && path !== "/api/auth/google") {
      forceLogoutToLogin("Session expired. Please log in again.");
      throw new Error("Session expired. Please log in again.");
    }
    throw new Error(data.error || ("Request failed: " + res.status));
  }
  return data;
}

// On page load, check the public /api/health endpoint. If it
// answers, a backend is connected and nothing changes. If it
// returns 404 on the same origin, this is a static-only preview:
// show the honest banner and disable Register/Login, so a tap
// cannot look like a registration attempt that "failed for no
// reason". Any other failure (server down, network error) leaves
// the buttons enabled, so a transient failure cannot lock the
// user out of a working local server.
async function checkBackend() {
  try {
    const res = await fetch(API_BASE + "/api/health");
    if (res.ok) { clearMsg("backendMsg"); return; }
    if (res.status !== 404) return;
  } catch (e) { return; }
  showMsg("backendMsg", BACKEND_UNAVAILABLE_MSG, false);
  const loginBtn = el("loginBtn"), regBtn = el("regBtn");
  if (loginBtn) loginBtn.disabled = true;
  if (regBtn) regBtn.disabled = true;
}

function showSection(name) {
  // Auth gate for navigation: before a verified login, only the
  // Welcome (landing) and Login / Register (auth) pages may open.
  // Any other request is redirected to Login. This is UI gating;
  // the server still rejects unauthenticated API calls with 401.
  if (!isLoggedIn && !PUBLIC_SECTIONS.includes(name)) name = "auth";
  document.querySelectorAll("section").forEach(s => s.classList.toggle("active", s.id === name));
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("active", b.dataset.section === name));
  setNav(false);
  if (name === "overview") { loadOverview(); updateAiWelcome(); }
  if (name === "history") loadHistory();
  if (name === "tasks") loadTasks();
  if (name === "taskstatus") loadStatusList();
  if (name === "deadlines") loadDeadlines();
  if (name === "finance") loadTransactions();
  if (name === "savings") loadSavings();
  if (name === "habits") loadHabits();
  if (name === "ai-history") loadAiHistory();
  if (name === "profile") loadProfile();
  if (name === "admin") loadAdmin();
  if (name === "analytics") loadAnalytics();
  if (name === "settings") loadSettingsBackend();
}

document.querySelectorAll("nav button").forEach(b => {
  b.addEventListener("click", () => showSection(b.dataset.section));
});

// AI welcome card (Overview): fills in the logged-in username from
// the session (the same source as #who / sessionStorage pdps_user)
// and links to the 6 AI sections via the existing showSection
// navigation. Overview is a protected section, so this card is
// only ever shown logged in; the auth gate is unchanged.
function updateAiWelcome() {
  const nameEl = el("aiWelcomeName");
  if (!nameEl) return;
  const stored = sessionStorage.getItem("pdps_user") || "";
  nameEl.textContent = stored.replace(/\s*\([^)]*\)$/, "");
}
document.querySelectorAll(".ai-welcome [data-section]").forEach(b => {
  b.addEventListener("click", () => showSection(b.dataset.section));
});

el("logoutBtn").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST", body: "{}" }); } catch (e) {}
  // Logout hides the dashboard at once: protected nav buttons are
  // hidden by the logged-out body class, and Welcome is shown.
  clearSession();
  showSection("landing");
});

// -- auth -----------------------------------------------------------
el("loginBtn").addEventListener("click", async () => {
  try {
    const data = await api("/api/login", { method: "POST", body: JSON.stringify({
      username: el("loginUser").value.trim(), password: el("loginPass").value }) });
    token = data.token;
    sessionStorage.setItem("pdps_token", token);
    sessionStorage.setItem("pdps_user", data.username);
    // The login response itself is the server verification that
    // unlocks the full dashboard.
    setAuthState(true, data.username + " (" + data.role + ")");
    showMsg("loginMsg", "Login successful.", true);
    showSection("overview");
  } catch (e) { showMsg("loginMsg", e.message, false); }
});

el("regBtn").addEventListener("click", async () => {
  try {
    // Confirm password (auth fix, 2026-11-09): a typo at registration
    // used to lock the account with no recovery, so the form asks
    // twice and the server rejects a mismatch (400).
    if (el("regPass").value !== el("regPassConfirm").value) {
      showMsg("regMsg", "Passwords do not match.", false);
      return;
    }
    const data = await api("/api/register", { method: "POST", body: JSON.stringify({
      username: el("regUser").value.trim(), password: el("regPass").value,
      confirm_password: el("regPassConfirm").value }) });
    showMsg("regMsg", "Registered as " + data.username + " (" + data.role + "). Please log in.", true);
  } catch (e) { showMsg("regMsg", e.message, false); }
});

// -- Google Sign-In (Phase 3) -------------------------------------
// The Google Identity Services script (loaded async in index.html)
// renders a "Sign in with Google" button into both auth cards.
// The button is shown only when the server says Google sign-in is
// enabled AND can verify tokens (config endpoint). When the GIS
// script never loads (offline, blocked, no network in tests) or
// the server has no client ID, the buttons and dividers stay
// hidden and the password forms keep working. Nothing here throws.
// The credential (ID token) is POSTed to /api/auth/google; the
// response is a normal app session, handled exactly like a
// password login (same token storage, same setAuthState).
let googleConfig = null;
async function handleGoogleCredential(response) {
  const credential = response && response.credential;
  if (!credential) { showMsg("loginMsg", "Google sign-in did not return a credential.", false); return; }
  try {
    const data = await api("/api/auth/google", { method: "POST", body: JSON.stringify({ credential }) });
    token = data.token;
    sessionStorage.setItem("pdps_token", token);
    sessionStorage.setItem("pdps_user", data.username);
    setAuthState(true, data.username + " (" + data.role + ")");
    showMsg("loginMsg", "Signed in with Google.", true);
    showSection("overview");
  } catch (e) { showMsg("loginMsg", e.message, false); }
}
async function initGoogleSignIn() {
  const loginBox = el("googleSignInLogin"), regBox = el("googleSignInReg");
  const dividers = document.querySelectorAll(".google-divider");
  const hide = () => {
    if (loginBox) loginBox.style.display = "none";
    if (regBox) regBox.style.display = "none";
    dividers.forEach(d => d.style.display = "none");
  };
  // Raw fetch (not api()): a 401/404/501 here must only hide the
  // buttons, never trigger the session-expiry logout flow.
  try {
    const res = await fetch(API_BASE + "/api/auth/google/config");
    if (!res.ok) { hide(); return; }
    googleConfig = await res.json();
  } catch (e) { hide(); return; }
  if (!googleConfig || !googleConfig.enabled || !googleConfig.available || !googleConfig.clientId) { hide(); return; }
  // The GIS script loads async from Google's CDN; wait up to 5 s
  // for it before giving up (it never arrives offline or in tests).
  const deadline = Date.now() + 5000;
  while (typeof google === "undefined" && Date.now() < deadline) {
    await new Promise(r => setTimeout(r, 100));
  }
  if (typeof google === "undefined" || !google.accounts || !google.accounts.id) { hide(); return; }
  google.accounts.id.initialize({ client_id: googleConfig.clientId, callback: handleGoogleCredential });
  if (loginBox) google.accounts.id.renderButton(loginBox, { theme: "outline", size: "large", width: 280 });
  if (regBox) google.accounts.id.renderButton(regBox, { theme: "outline", size: "large", width: 280 });
}

// -- overview -------------------------------------------------------
async function loadOverview() {
  el("overviewCards").innerHTML = '<div class="loading">Loading overview…</div>';
  try {
    const o = await api("/api/overview");
    el("overviewCards").innerHTML = [
      ["Decisions", o.decisions, "records in decisions.txt"], ["Tasks", o.tasks + " (" + o.tasksPending + " pending)", "in tasks.txt"],
      ["Balance", o.balance.toFixed(2), "income minus expense"], ["Income", o.income.toFixed(2), "total income"],
      ["Expense", o.expense.toFixed(2), "total expense"],
      ["Savings", o.savingsSaved.toFixed(2) + " / " + o.savingsTarget.toFixed(2), o.savingsGoals + " goal(s)"]
    ].map(([k, v, sub]) => `<div class="stat"><div class="label">${k}</div><div class="value">${v}</div><div class="sub">${sub}</div></div>`).join("");
    el("ovChart").innerHTML = chartHtml([
      { label: "Income", value: o.income, cls: "" },
      { label: "Expense", value: o.expense, cls: "expense" },
      { label: "Savings saved", value: o.savingsSaved, cls: "savings" }],
      Math.max(o.income, o.expense, o.savingsSaved, 1));
    const decisions = await api("/api/decisions");
    el("overviewDecisions").innerHTML = decisions.length ? "<table><tr><th>ID</th><th>Date</th><th>Type</th><th>Priority</th><th>Title</th><th></th></tr>" +
      decisions.slice(-20).reverse().map(d =>
        `<tr><td>${esc(d.id)}</td><td>${esc(d.date)}</td><td>${esc(d.type)}</td><td>${d.priority}</td><td>${esc(d.title)}</td>` +
        `<td><button class="btn btn-danger" onclick="deleteDecision(${d.id})">Delete</button></td></tr>`).join("") + "</table>"
      : "<div class='empty'>No decisions yet. Create one from Daily Decision, Tasks, or Priority.</div>";
  } catch (e) { showMsg("globalMsg", e.message, false); }
}

async function deleteDecision(id) {
  try {
    await api("/api/decisions/" + id, { method: "DELETE" });
    loadOverview();
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
window.deleteDecision = deleteDecision;

el("backupBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/backup", { method: "POST", body: "{}" });
    showMsg("backupMsg", "Backup created (" + r.backedUp + " decisions).", true);
  } catch (e) { showMsg("backupMsg", e.message, false); }
});
el("restoreBtn").addEventListener("click", async () => {
  if (!confirm("Restore will replace YOUR decisions with YOUR backup. Your current decisions that are not in the backup will be lost. Other users are not affected. Continue?")) return;
  try {
    const r = await api("/api/restore", { method: "POST", body: JSON.stringify({ confirm: true }) });
    showMsg("backupMsg", "Restored " + r.restored + " decisions.", true);
    loadOverview();
  } catch (e) { showMsg("backupMsg", e.message, false); }
});

// -- daily decision + multi-task ------------------------------------
el("ddBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/daily-decision", { method: "POST", body: JSON.stringify({
      availableTime: +el("ddAvailable").value, requiredTime: +el("ddRequired").value,
      urgency: +el("ddUrgency").value, importance: +el("ddImportance").value,
      energy: +el("ddEnergy").value }) });
    showMsg("ddMsg", "Suggestion: " + r.suggestion + " (score " + r.score + ", saved as decision " + r.record.id + ")", true);
  } catch (e) { showMsg("ddMsg", e.message, false); }
});

function addMtRow() {
  const div = document.createElement("div");
  div.className = "task-row";
  div.innerHTML = `<input placeholder="Task name" class="mt-name"><input type="number" min="1" max="10" placeholder="Urgency 1-10" class="mt-urgency"><input type="number" min="1" max="10" placeholder="Energy 1-10" class="mt-energy"><input type="number" min="1" max="1440" placeholder="Time (min)" class="mt-time">`;
  el("mtTasks").appendChild(div);
}
addMtRow(); addMtRow();
el("mtAdd").addEventListener("click", addMtRow);
el("mtBtn").addEventListener("click", async () => {
  const tasks = [];
  document.querySelectorAll("#mtTasks .task-row").forEach(row => {
    const name = row.querySelector(".mt-name").value.trim();
    if (name) tasks.push({ name, deadlineUrgency: +row.querySelector(".mt-urgency").value,
      energy: +row.querySelector(".mt-energy").value, time: +row.querySelector(".mt-time").value });
  });
  try {
    const r = await api("/api/multi-task", { method: "POST", body: JSON.stringify({
      availableEnergy: +el("mtEnergy").value, availableTime: +el("mtTime").value, tasks }) });
    showMsg("mtMsg", "Recommended: " + (r.recommended.map(t => t.name).join(", ") || "none") +
      " | Skipped: " + (r.skipped.map(t => t.name).join(", ") || "none") +
      " | Remaining energy " + r.remainingEnergy + ", time " + r.remainingTime + " min.", true);
  } catch (e) { showMsg("mtMsg", e.message, false); }
});

// -- AI Daily Decision (Phase 3.1) ----------------------------------
// POST /api/ai/daily-decision. Server contract (verified from
// cpp_server.cpp): input required, trimmed, non-empty, max 4000
// BYTES (std::string::size(), not code points — a Bengali
// character is 3 bytes); options optional, max 10, each trimmed,
// non-empty, max 500 BYTES; empty options are ignored by the
// server and are not sent at all here. The server's old JSON
// helpers do NOT decode escapes, so newlines, tabs and other
// control characters are replaced with spaces BEFORE sending —
// otherwise "\n" would arrive at the server as the letter "n".
// The reply is rendered with esc() only (never raw innerHTML).
// history_id 0 means the reply arrived but the history row was
// not saved (this endpoint has no save read-back check).
const AI_DAILY_MAX_INPUT_BYTES = 4000;
const AI_DAILY_MAX_OPTION_BYTES = 500;
const AI_DAILY_MAX_OPTIONS = 10;

function aiDailyByteLen(s) { return new TextEncoder().encode(s).length; }
function aiDailySanitize(s) { return s.replace(/[\x00-\x1F\x7F]/g, " "); }

function aiDailyOptCount() { return document.querySelectorAll("#aiDailyOptions .ai-opt-row").length; }
function aiDailySyncAddBtn() {
  el("aiDailyAddOpt").disabled = aiDailyOptCount() >= AI_DAILY_MAX_OPTIONS;
}
function addAiDailyOptRow() {
  if (aiDailyOptCount() >= AI_DAILY_MAX_OPTIONS) return;
  const div = document.createElement("div");
  div.className = "ai-opt-row";
  div.innerHTML = `<input placeholder="Option (optional)" class="ai-opt-input"><button type="button" class="btn btn-secondary ai-opt-remove">Remove</button>`;
  div.querySelector(".ai-opt-remove").addEventListener("click", () => { div.remove(); aiDailySyncAddBtn(); });
  el("aiDailyOptions").appendChild(div);
  aiDailySyncAddBtn();
}
addAiDailyOptRow();
el("aiDailyAddOpt").addEventListener("click", addAiDailyOptRow);

el("aiDailyBtn").addEventListener("click", async () => {
  const btn = el("aiDailyBtn");
  const replyBox = el("aiDailyReply");
  clearMsg("aiDailyMsg");
  clearMsg("aiDailyWarn");
  replyBox.innerHTML = "";
  // Client-side validation mirrors the server, so the user gets an
  // immediate error instead of a round trip that would fail anyway.
  const input = aiDailySanitize(el("aiDailyInput").value.trim());
  if (!input) { showMsg("aiDailyMsg", "Please describe the decision first.", false); return; }
  if (aiDailyByteLen(input) > AI_DAILY_MAX_INPUT_BYTES) {
    showMsg("aiDailyMsg", "Input is too long: maximum 4000 bytes (a Bengali character counts as 3 bytes).", false);
    return;
  }
  const options = [];
  let optionTooLong = false;
  document.querySelectorAll("#aiDailyOptions .ai-opt-input").forEach(inp => {
    const v = aiDailySanitize(inp.value.trim());
    if (!v) return; // empty rows are ignored, never sent
    if (aiDailyByteLen(v) > AI_DAILY_MAX_OPTION_BYTES) { optionTooLong = true; return; }
    options.push(v);
  });
  if (optionTooLong) {
    showMsg("aiDailyMsg", "An option is too long: maximum 500 bytes each (a Bengali character counts as 3 bytes).", false);
    return;
  }
  const body = { input };
  if (options.length) body.options = options;
  btn.disabled = true;
  const oldText = btn.textContent;
  btn.textContent = "Thinking…";
  replyBox.innerHTML = '<div class="loading">Thinking…</div>';
  try {
    const r = await api("/api/ai/daily-decision", { method: "POST", body: JSON.stringify(body) });
    replyBox.innerHTML = esc(r.reply || "");
    let msg = "AI suggestion received.";
    if (typeof r.history_id === "number") msg += " (history #" + r.history_id + ")";
    showMsg("aiDailyMsg", msg, true);
    if (r.history_id === 0) {
      showMsg("aiDailyWarn", "Note: the reply was received, but it was NOT saved to your AI history.", false);
    }
  } catch (e) {
    // A stale reply must never stay on screen after an error.
    replyBox.innerHTML = "";
    // api() already forces a logout on 401; the other messages come
    // from the server (data.error) and are shown with a short note.
    const m = e.message || "Request failed.";
    if (m === "invalid input") showMsg("aiDailyMsg", "Invalid input — please check the fields and try again.", false);
    else if (m === "AI requires the C++ server") showMsg("aiDailyMsg", "AI requires the C++ server — this Python fallback server cannot run AI features.", false);
    else if (m === "AI unavailable" || m === "AI configuration error" || m === "AI request limit reached") showMsg("aiDailyMsg", m + " Please try again later.", false);
    else if (m === "AI request timed out") showMsg("aiDailyMsg", "AI request timed out. Please try again.", false);
    else if (m === "AI request failed") showMsg("aiDailyMsg", "AI request failed. Please try again later.", false);
    else showMsg("aiDailyMsg", m, false);
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
  }
});

// -- AI Task Analyzer (Phase 3.2) ---------------------------------
// POST /api/ai/task-analyzer. Server contract (verified from
// cpp_server.cpp): description required, trimmed, non-empty, max
// 4000 BYTES (std::string::size(), not code points — same as
// 3.1); title optional, trimmed, non-empty, max 500 BYTES;
// urgency/importance optional strict integers 1-10, sent as JSON
// numbers; deadline optional free text, trimmed, non-empty, max
// 100 BYTES — the server does NO date validation, so the UI uses
// a plain text field, never a date picker; status optional, one
// of pending / in-progress / done (the server also accepts the
// aliases in_progress and completed, but the UI only ever sends
// the canonical values). Same escape quirk as 3.1: control
// characters are replaced with spaces BEFORE sending, because
// the server's old JSON helpers do not decode escapes.
// history_id 0 means the reply arrived but the history row was
// not saved (this endpoint has no save read-back check).
// Byte length and sanitization reuse the 3.1 helpers.
const AI_TASK_MAX_DESC_BYTES = 4000;
const AI_TASK_MAX_TITLE_BYTES = 500;
const AI_TASK_MAX_DEADLINE_BYTES = 100;

function aiTaskStrictInt(s) {
  if (!/^-?\d+$/.test(s)) return null;
  const n = Number(s);
  if (!Number.isInteger(n) || n < 1 || n > 10) return null;
  return n;
}

el("aiTaskBtn").addEventListener("click", async () => {
  const btn = el("aiTaskBtn");
  const replyBox = el("aiTaskReply");
  clearMsg("aiTaskMsg");
  clearMsg("aiTaskWarn");
  replyBox.innerHTML = "";
  // Client-side validation mirrors the server, so the user gets an
  // immediate error instead of a round trip that would fail anyway.
  const desc = aiDailySanitize(el("aiTaskDesc").value.trim());
  if (!desc) { showMsg("aiTaskMsg", "Please describe the task first.", false); return; }
  if (aiDailyByteLen(desc) > AI_TASK_MAX_DESC_BYTES) {
    showMsg("aiTaskMsg", "Description is too long: maximum 4000 bytes (a Bengali character counts as 3 bytes).", false);
    return;
  }
  const title = aiDailySanitize(el("aiTaskTitle").value.trim());
  if (title && aiDailyByteLen(title) > AI_TASK_MAX_TITLE_BYTES) {
    showMsg("aiTaskMsg", "Title is too long: maximum 500 bytes (a Bengali character counts as 3 bytes).", false);
    return;
  }
  const urgencyRaw = el("aiTaskUrgency").value.trim();
  const urgency = urgencyRaw === "" ? null : aiTaskStrictInt(urgencyRaw);
  if (urgencyRaw !== "" && urgency === null) {
    showMsg("aiTaskMsg", "Urgency must be a whole number from 1 to 10.", false);
    return;
  }
  const importanceRaw = el("aiTaskImportance").value.trim();
  const importance = importanceRaw === "" ? null : aiTaskStrictInt(importanceRaw);
  if (importanceRaw !== "" && importance === null) {
    showMsg("aiTaskMsg", "Importance must be a whole number from 1 to 10.", false);
    return;
  }
  const deadline = aiDailySanitize(el("aiTaskDeadline").value.trim());
  if (deadline && aiDailyByteLen(deadline) > AI_TASK_MAX_DEADLINE_BYTES) {
    showMsg("aiTaskMsg", "Deadline is too long: maximum 100 bytes (a Bengali character counts as 3 bytes).", false);
    return;
  }
  const status = el("aiTaskStatus").value;
  const body = { description: desc };
  if (title) body.title = title;
  if (urgency !== null) body.urgency = urgency;
  if (importance !== null) body.importance = importance;
  if (deadline) body.deadline = deadline;
  if (status) body.status = status;
  btn.disabled = true;
  const oldText = btn.textContent;
  btn.textContent = "Thinking…";
  replyBox.innerHTML = '<div class="loading">Thinking…</div>';
  try {
    const r = await api("/api/ai/task-analyzer", { method: "POST", body: JSON.stringify(body) });
    replyBox.innerHTML = esc(r.reply || "");
    let msg = "AI analysis received.";
    if (typeof r.history_id === "number") msg += " (history #" + r.history_id + ")";
    showMsg("aiTaskMsg", msg, true);
    if (r.history_id === 0) {
      showMsg("aiTaskWarn", "Note: the reply was received, but it was NOT saved to your AI history.", false);
    }
  } catch (e) {
    // A stale reply must never stay on screen after an error.
    replyBox.innerHTML = "";
    // api() already forces a logout on 401; the other messages come
    // from the server (data.error) and are shown with a short note.
    const m = e.message || "Request failed.";
    if (m === "invalid input") showMsg("aiTaskMsg", "Invalid input — please check the fields and try again.", false);
    else if (m === "AI requires the C++ server") showMsg("aiTaskMsg", "AI requires the C++ server — this Python fallback server cannot run AI features.", false);
    else if (m === "AI unavailable" || m === "AI configuration error" || m === "AI request limit reached") showMsg("aiTaskMsg", m + " Please try again later.", false);
    else if (m === "AI request timed out") showMsg("aiTaskMsg", "AI request timed out. Please try again.", false);
    else if (m === "AI request failed") showMsg("aiTaskMsg", "AI request failed. Please try again later.", false);
    else showMsg("aiTaskMsg", m, false);
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
  }
});

// -- AI Study Planner (Phase 3.3) ---------------------------------
// POST /api/ai/study-planner. Server contract (verified from
// cpp_server.cpp): subjects REQUIRED, a JSON array of strings,
// 1-10 items (checked before dedup), each trimmed, non-empty,
// max 200 BYTES; the server dedupes case-insensitively, and the
// UI does the same and says so. hours_per_day REQUIRED, a plain
// JSON number 0.5-24 — the server's jsonNumberField truncates
// exponents ("1e3" -> 1) and dotted junk ("3.5.2" -> 3.5), so the
// UI only ever sends a plain decimal number. exam_date optional,
// strict YYYY-MM-DD, a real calendar date, today-or-future by the
// SERVER's local date (the UI checks against the user's local
// date; the server is the authority). description optional,
// trimmed, non-empty, max 4000 BYTES (description wins over the
// "input" compat alias; the UI only sends "description"). Same
// escape quirk as 3.1/3.2: control characters are replaced with
// spaces BEFORE sending. This endpoint verifies the history save
// (read-back) — a failed save is a 502, never a 200 — but a
// history_id of 0 is still handled with the same warning.
// Byte length and sanitization reuse the 3.1 helpers.
const AI_STUDY_MAX_SUBJECTS = 10;
const AI_STUDY_MAX_SUBJECT_BYTES = 200;
const AI_STUDY_MAX_DESC_BYTES = 4000;

function aiStudySubjectCount() { return document.querySelectorAll("#aiStudySubjects .ai-opt-row").length; }
function aiStudySyncAddBtn() {
  el("aiStudyAddSubject").disabled = aiStudySubjectCount() >= AI_STUDY_MAX_SUBJECTS;
}
function addAiStudySubjectRow() {
  if (aiStudySubjectCount() >= AI_STUDY_MAX_SUBJECTS) return;
  const div = document.createElement("div");
  div.className = "ai-opt-row";
  div.innerHTML = `<input placeholder="Subject (e.g. Maths)" class="ai-subject-input"><button type="button" class="btn btn-secondary ai-opt-remove">Remove</button>`;
  div.querySelector(".ai-opt-remove").addEventListener("click", () => { div.remove(); aiStudySyncAddBtn(); });
  el("aiStudySubjects").appendChild(div);
  aiStudySyncAddBtn();
}
addAiStudySubjectRow();
el("aiStudyAddSubject").addEventListener("click", addAiStudySubjectRow);

function aiStudyValidHours(s) {
  // Plain decimal only: no exponent, no sign, no trailing junk.
  if (!/^(\d+(\.\d+)?|\.\d+)$/.test(s)) return null;
  const n = Number(s);
  if (!Number.isFinite(n) || n < 0.5 || n > 24) return null;
  return n;
}
function aiStudyValidExamDate(s) {
  // Strict YYYY-MM-DD, real calendar date, today-or-future
  // by the user's local date.
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return false;
  const y = Number(m[1]), mo = Number(m[2]), d = Number(m[3]);
  if (mo < 1 || mo > 12 || d < 1) return false;
  const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
  const dim = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1];
  if (d > dim) return false;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return new Date(y, mo - 1, d) >= today;
}

el("aiStudyBtn").addEventListener("click", async () => {
  const btn = el("aiStudyBtn");
  const replyBox = el("aiStudyReply");
  clearMsg("aiStudyMsg");
  clearMsg("aiStudyWarn");
  replyBox.innerHTML = "";
  // Client-side validation mirrors the server, so the user gets an
  // immediate error instead of a round trip that would fail anyway.
  const subjects = [];
  let subjectTooLong = false;
  document.querySelectorAll("#aiStudySubjects .ai-subject-input").forEach(inp => {
    const v = aiDailySanitize(inp.value.trim());
    if (!v) return; // empty rows are ignored, never sent
    if (aiDailyByteLen(v) > AI_STUDY_MAX_SUBJECT_BYTES) { subjectTooLong = true; return; }
    subjects.push(v);
  });
  if (subjectTooLong) {
    showMsg("aiStudyMsg", "A subject is too long: maximum 200 bytes each (a Bengali character counts as 3 bytes).", false);
    return;
  }
  if (!subjects.length) { showMsg("aiStudyMsg", "Please add at least one subject first.", false); return; }
  if (subjects.length > AI_STUDY_MAX_SUBJECTS) {
    showMsg("aiStudyMsg", "Too many subjects: maximum 10.", false);
    return;
  }
  // Dedupe case-insensitively, first occurrence wins (like the server).
  const seen = new Set(), deduped = [];
  subjects.forEach(s => { const k = s.toLowerCase(); if (!seen.has(k)) { seen.add(k); deduped.push(s); } });
  const dupCount = subjects.length - deduped.length;
  const hoursRaw = el("aiStudyHours").value.trim();
  const hours = hoursRaw === "" ? null : aiStudyValidHours(hoursRaw);
  if (hours === null) {
    showMsg("aiStudyMsg", "Hours per day must be a number from 0.5 to 24.", false);
    return;
  }
  const examDate = el("aiStudyExam").value.trim();
  if (examDate && !aiStudyValidExamDate(examDate)) {
    showMsg("aiStudyMsg", "Exam date must be a valid date, today or in the future (YYYY-MM-DD).", false);
    return;
  }
  const desc = aiDailySanitize(el("aiStudyDesc").value.trim());
  if (desc && aiDailyByteLen(desc) > AI_STUDY_MAX_DESC_BYTES) {
    showMsg("aiStudyMsg", "Description is too long: maximum 4000 bytes (a Bengali character counts as 3 bytes).", false);
    return;
  }
  const body = { subjects: deduped, hours_per_day: hours };
  if (examDate) body.exam_date = examDate;
  if (desc) body.description = desc;
  btn.disabled = true;
  const oldText = btn.textContent;
  btn.textContent = "Thinking…";
  replyBox.innerHTML = '<div class="loading">Thinking…</div>';
  try {
    const r = await api("/api/ai/study-planner", { method: "POST", body: JSON.stringify(body) });
    replyBox.innerHTML = esc(r.reply || "");
    let msg = "AI study plan received (" + deduped.length + (deduped.length === 1 ? " subject" : " subjects") + ").";
    if (typeof r.history_id === "number") msg += " (history #" + r.history_id + ")";
    showMsg("aiStudyMsg", msg, true);
    let warn = "";
    if (dupCount) warn = "Note: " + dupCount + (dupCount === 1 ? " duplicate subject was" : " duplicate subjects were") + " removed.";
    if (r.history_id === 0) warn = "Note: the reply was received, but it was NOT saved to your AI history.";
    if (warn) showMsg("aiStudyWarn", warn, false);
  } catch (e) {
    // A stale reply must never stay on screen after an error.
    replyBox.innerHTML = "";
    // api() already forces a logout on 401; the other messages come
    // from the server (data.error) and are shown with a short note.
    const m = e.message || "Request failed.";
    if (m === "invalid input") showMsg("aiStudyMsg", "Invalid input — please check the fields and try again.", false);
    else if (m === "AI requires the C++ server") showMsg("aiStudyMsg", "AI requires the C++ server — this Python fallback server cannot run AI features.", false);
    else if (m === "AI unavailable" || m === "AI configuration error" || m === "AI request limit reached") showMsg("aiStudyMsg", m + " Please try again later.", false);
    else if (m === "AI request timed out") showMsg("aiStudyMsg", "AI request timed out. Please try again.", false);
    else if (m === "AI request failed") showMsg("aiStudyMsg", "AI request failed. Please try again later.", false);
    else showMsg("aiStudyMsg", m, false);
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
  }
});

// -- AI Problem Solver (Phase 3.4) ---------------------------------
// POST /api/ai/problem-solver. Server contract (verified from
// cpp_server.cpp): problem REQUIRED, trimmed, non-empty, max
// 4000 UTF-8 CODE POINTS — counted as characters, NOT bytes
// (the server uses utf8CodePoints(); a 4000-Bengali-char problem
// is about 12000 bytes and is VALID — the 2.4 change to
// gemini_client.cpp counts the prompt budget in code points
// exactly so this works). The "input" compat alias exists, but
// the UI only sends "problem". Same escape quirk as 3.1-3.3:
// control characters are replaced with spaces BEFORE sending,
// because the server's old JSON helpers do not decode escapes.
// This endpoint verifies the history save (read-back) — a failed
// save is a 502, never a 200 — but a history_id of 0 is still
// handled with the same warning. Sanitization reuses the 3.1
// helper; the code-point count is new (spreading a string counts
// code points, so astral characters count as one).
const AI_PROBLEM_MAX_CODE_POINTS = 4000;

function aiProblemCodePoints(s) { return [...s].length; }

el("aiProblemBtn").addEventListener("click", async () => {
  const btn = el("aiProblemBtn");
  const replyBox = el("aiProblemReply");
  clearMsg("aiProblemMsg");
  clearMsg("aiProblemWarn");
  replyBox.innerHTML = "";
  // Client-side validation mirrors the server, so the user gets an
  // immediate error instead of a round trip that would fail anyway.
  const problem = aiDailySanitize(el("aiProblemDesc").value.trim());
  if (!problem) { showMsg("aiProblemMsg", "Please describe the problem first.", false); return; }
  if (aiProblemCodePoints(problem) > AI_PROBLEM_MAX_CODE_POINTS) {
    showMsg("aiProblemMsg", "Problem is too long: maximum 4000 characters.", false);
    return;
  }
  const body = { problem };
  btn.disabled = true;
  const oldText = btn.textContent;
  btn.textContent = "Thinking…";
  replyBox.innerHTML = '<div class="loading">Thinking…</div>';
  try {
    const r = await api("/api/ai/problem-solver", { method: "POST", body: JSON.stringify(body) });
    replyBox.innerHTML = esc(r.reply || "");
    let msg = "AI solution received.";
    if (typeof r.history_id === "number") msg += " (history #" + r.history_id + ")";
    showMsg("aiProblemMsg", msg, true);
    if (r.history_id === 0) {
      showMsg("aiProblemWarn", "Note: the reply was received, but it was NOT saved to your AI history.", false);
    }
  } catch (e) {
    // A stale reply must never stay on screen after an error.
    replyBox.innerHTML = "";
    // api() already forces a logout on 401; the other messages come
    // from the server (data.error) and are shown with a short note.
    const m = e.message || "Request failed.";
    if (m === "invalid input") showMsg("aiProblemMsg", "Invalid input — please check the fields and try again.", false);
    else if (m === "AI requires the C++ server") showMsg("aiProblemMsg", "AI requires the C++ server — this Python fallback server cannot run AI features.", false);
    else if (m === "AI unavailable" || m === "AI configuration error" || m === "AI request limit reached") showMsg("aiProblemMsg", m + " Please try again later.", false);
    else if (m === "AI request timed out") showMsg("aiProblemMsg", "AI request timed out. Please try again.", false);
    else if (m === "AI request failed") showMsg("aiProblemMsg", "AI request failed. Please try again later.", false);
    else showMsg("aiProblemMsg", m, false);
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
  }
});

// -- AI Budget Assistant (Phase 3.5) ------------------------------
// POST /api/ai/budget. Server contract (verified from
// cpp_server.cpp): all fields optional, but at least one
// meaningful field is required ({} and {"expenses": []} alone
// are 400). `income` is a strict JSON number 0–1e9 — and
// income 0 COUNTS as provided, so it must never be treated
// as empty. `expenses` is an array of at most 20 items, each
// {category (non-empty, max 100 UTF-8 code points), amount
// (number 0–1e9)} — both required per item. `savings_goal`
// needs ALL THREE sub-fields {name (max 200 code points),
// target (>0, max 1e9), saved (>=0, max 1e9)} or none at all.
// `input` is optional, max 2000 UTF-8 code points. Numbers are
// sent as JSON numbers, never strings. Newlines are SAFE here
// (the budget route decodes escapes properly, unlike 2.1–2.4),
// but control characters are still replaced with spaces for
// consistency. The server computes every figure
// deterministically (totals, remaining, deficit, savings rate,
// goal progress, months to goal) — Gemini never calculates,
// so the UI only renders the reply. This endpoint verifies
// the history save (read-back) — a failed save is a 502,
// never a 200 — but a history_id of 0 is still handled with
// the same warning. Code points are counted with
// [...str].length, bytes are never used here.
const AI_BUDGET_MAX_EXPENSES = 20;
const AI_BUDGET_MAX_AMOUNT = 1000000000;
const AI_BUDGET_MAX_CATEGORY_CODE_POINTS = 100;
const AI_BUDGET_MAX_GOAL_NAME_CODE_POINTS = 200;
const AI_BUDGET_MAX_INPUT_CODE_POINTS = 2000;

function aiBudgetCodePoints(s) { return [...s].length; }

// Strict JSON-number shape, like the server's parseStrictNumber:
// optional -, no leading zeros, optional fraction, optional
// exponent. Returns a finite Number, or null when the text is
// not a valid JSON number (strings, NaN, Infinity, "01",
// "+100", "1.2.3", "1e999" are all rejected).
function aiBudgetValidNumber(raw) {
  if (!/^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$/.test(raw)) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function aiBudgetExpenseCount() { return document.querySelectorAll("#aiBudgetExpenses .ai-opt-row").length; }
function aiBudgetSyncAddBtn() {
  el("aiBudgetAddExpense").disabled = aiBudgetExpenseCount() >= AI_BUDGET_MAX_EXPENSES;
}
function addAiBudgetExpenseRow() {
  if (aiBudgetExpenseCount() >= AI_BUDGET_MAX_EXPENSES) return;
  const div = document.createElement("div");
  div.className = "ai-opt-row";
  div.innerHTML = `<input placeholder="Category (e.g. Food)" class="ai-exp-category"><input type="number" placeholder="Amount" min="0" max="1000000000" step="0.01" class="ai-exp-amount"><button type="button" class="btn btn-secondary ai-opt-remove">Remove</button>`;
  div.querySelector(".ai-opt-remove").addEventListener("click", () => { div.remove(); aiBudgetSyncAddBtn(); });
  el("aiBudgetExpenses").appendChild(div);
  aiBudgetSyncAddBtn();
}
addAiBudgetExpenseRow();
el("aiBudgetAddExpense").addEventListener("click", addAiBudgetExpenseRow);

el("aiBudgetBtn").addEventListener("click", async () => {
  const btn = el("aiBudgetBtn");
  const replyBox = el("aiBudgetReply");
  clearMsg("aiBudgetMsg");
  clearMsg("aiBudgetWarn");
  replyBox.innerHTML = "";
  // Client-side validation mirrors the server, so the user gets an
  // immediate error instead of a round trip that would fail anyway.
  // Income 0 counts as provided — only an empty field means "not
  // provided".
  const incomeRaw = el("aiBudgetIncome").value.trim();
  let income = null;
  if (incomeRaw !== "") {
    income = aiBudgetValidNumber(incomeRaw);
    if (income === null || income < 0 || income > AI_BUDGET_MAX_AMOUNT) {
      showMsg("aiBudgetMsg", "Income must be a number from 0 to 1,000,000,000.", false);
      return;
    }
  }
  const expenses = [];
  let expenseError = "";
  document.querySelectorAll("#aiBudgetExpenses .ai-opt-row").forEach(row => {
    if (expenseError) return;
    const category = aiDailySanitize(row.querySelector(".ai-exp-category").value.trim());
    const amountRaw = row.querySelector(".ai-exp-amount").value.trim();
    if (!category && !amountRaw) return; // empty rows are ignored, never sent
    if (!category) { expenseError = "Each expense needs a category."; return; }
    if (!amountRaw) { expenseError = "Each expense needs an amount."; return; }
    if (aiBudgetCodePoints(category) > AI_BUDGET_MAX_CATEGORY_CODE_POINTS) {
      expenseError = "An expense category is too long: maximum 100 characters.";
      return;
    }
    const amount = aiBudgetValidNumber(amountRaw);
    if (amount === null || amount < 0 || amount > AI_BUDGET_MAX_AMOUNT) {
      expenseError = "Expense amounts must be numbers from 0 to 1,000,000,000.";
      return;
    }
    expenses.push({ category, amount });
  });
  if (expenseError) { showMsg("aiBudgetMsg", expenseError, false); return; }
  if (expenses.length > AI_BUDGET_MAX_EXPENSES) {
    showMsg("aiBudgetMsg", "Too many expenses: maximum 20.", false);
    return;
  }
  // Savings goal: all three sub-fields or none at all.
  const goalName = aiDailySanitize(el("aiBudgetGoalName").value.trim());
  const goalTargetRaw = el("aiBudgetGoalTarget").value.trim();
  const goalSavedRaw = el("aiBudgetGoalSaved").value.trim();
  const goalFilled = goalName !== "" || goalTargetRaw !== "" || goalSavedRaw !== "";
  let goal = null;
  if (goalFilled) {
    if (!goalName || goalTargetRaw === "" || goalSavedRaw === "") {
      showMsg("aiBudgetMsg", "A savings goal needs all three fields: name, target and the amount already saved.", false);
      return;
    }
    if (aiBudgetCodePoints(goalName) > AI_BUDGET_MAX_GOAL_NAME_CODE_POINTS) {
      showMsg("aiBudgetMsg", "Savings goal name is too long: maximum 200 characters.", false);
      return;
    }
    const target = aiBudgetValidNumber(goalTargetRaw);
    if (target === null || target <= 0 || target > AI_BUDGET_MAX_AMOUNT) {
      showMsg("aiBudgetMsg", "Savings goal target must be a number over 0 and up to 1,000,000,000.", false);
      return;
    }
    const saved = aiBudgetValidNumber(goalSavedRaw);
    if (saved === null || saved < 0 || saved > AI_BUDGET_MAX_AMOUNT) {
      showMsg("aiBudgetMsg", "The amount already saved must be a number from 0 to 1,000,000,000.", false);
      return;
    }
    goal = { name: goalName, target, saved };
  }
  const input = aiDailySanitize(el("aiBudgetInput").value.trim());
  if (input && aiBudgetCodePoints(input) > AI_BUDGET_MAX_INPUT_CODE_POINTS) {
    showMsg("aiBudgetMsg", "Extra notes are too long: maximum 2000 characters.", false);
    return;
  }
  // At least one meaningful field is required — income 0 counts.
  if (incomeRaw === "" && !expenses.length && !goal && !input) {
    showMsg("aiBudgetMsg", "Please enter an income, at least one expense, a savings goal or a note first.", false);
    return;
  }
  const body = {};
  if (incomeRaw !== "") body.income = income;
  if (expenses.length) body.expenses = expenses;
  if (goal) body.savings_goal = goal;
  if (input) body.input = input;
  btn.disabled = true;
  const oldText = btn.textContent;
  btn.textContent = "Thinking…";
  replyBox.innerHTML = '<div class="loading">Thinking…</div>';
  try {
    const r = await api("/api/ai/budget", { method: "POST", body: JSON.stringify(body) });
    replyBox.innerHTML = esc(r.reply || "");
    let msg = "AI budget review received.";
    if (typeof r.history_id === "number") msg += " (history #" + r.history_id + ")";
    showMsg("aiBudgetMsg", msg, true);
    if (r.history_id === 0) {
      showMsg("aiBudgetWarn", "Note: the reply was received, but it was NOT saved to your AI history.", false);
    }
  } catch (e) {
    // A stale reply must never stay on screen after an error.
    replyBox.innerHTML = "";
    // api() already forces a logout on 401; the other messages come
    // from the server (data.error) and are shown with a short note.
    const m = e.message || "Request failed.";
    if (m === "invalid input") showMsg("aiBudgetMsg", "Invalid input — please check the fields and try again.", false);
    else if (m === "AI requires the C++ server") showMsg("aiBudgetMsg", "AI requires the C++ server — this Python fallback server cannot run AI features.", false);
    else if (m === "AI unavailable" || m === "AI configuration error" || m === "AI request limit reached") showMsg("aiBudgetMsg", m + " Please try again later.", false);
    else if (m === "AI request timed out") showMsg("aiBudgetMsg", "AI request timed out. Please try again.", false);
    else if (m === "AI request failed") showMsg("aiBudgetMsg", "AI request failed. Please try again later.", false);
    else showMsg("aiBudgetMsg", m, false);
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
  }
});

// -- AI Habit Assistant (Phase 3.6) -------------------------------
// POST /api/ai/habit. Server contract (verified from
// cpp_server.cpp): `habit` REQUIRED, trimmed, non-empty, max
// 100 UTF-8 code points, no control characters and no `|`.
// `target_streak` is optional, a strict integer 1–365.
// `frequency` is "daily" (default) or "weekly". `input` is
// optional, max 2000 UTF-8 code points. `today` is optional, a
// strict YYYY-MM-DD within +/-2 days of the SERVER's local
// date (empty means "use the server date"). Newlines are SAFE
// here (the habit route decodes escapes properly, unlike
// 2.1–2.4), but control characters are still replaced with
// spaces for consistency. The server computes the real streaks
// from the caller's OWN habit log — read-only, the log is
// never changed — and Gemini never calculates, so the UI only
// renders the reply. This endpoint verifies the history save
// (read-back) — a failed save is a 502, never a 200 — but a
// history_id of 0 is still handled with the same warning.
// Code points are counted with [...str].length, bytes are
// never used here.
const AI_HABIT_MAX_CODE_POINTS = 100;
const AI_HABIT_MAX_INPUT_CODE_POINTS = 2000;
const AI_HABIT_MIN_TARGET = 1;
const AI_HABIT_MAX_TARGET = 365;

function aiHabitCodePoints(s) { return [...s].length; }

// Strict integer: digits only, no sign, no fraction, no
// exponent, no trailing junk. Returns the Number, or null.
function aiHabitValidTarget(s) {
  if (!/^\d+$/.test(s)) return null;
  const n = Number(s);
  if (!Number.isFinite(n) || n < AI_HABIT_MIN_TARGET || n > AI_HABIT_MAX_TARGET) return null;
  return n;
}
function aiHabitValidToday(s) {
  // Strict YYYY-MM-DD, real calendar date, within +/-2 days
  // of the user's local date. The server re-validates against
  // its own date and is the authority — a server 400 here
  // surfaces as the friendly "Invalid input" message.
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return false;
  const y = Number(m[1]), mo = Number(m[2]), d = Number(m[3]);
  if (mo < 1 || mo > 12 || d < 1) return false;
  const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
  const dim = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1];
  if (d > dim) return false;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((new Date(y, mo - 1, d) - today) / 86400000);
  return diff >= -2 && diff <= 2;
}

el("aiHabitBtn").addEventListener("click", async () => {
  const btn = el("aiHabitBtn");
  const replyBox = el("aiHabitReply");
  clearMsg("aiHabitMsg");
  clearMsg("aiHabitWarn");
  replyBox.innerHTML = "";
  // Client-side validation mirrors the server, so the user gets an
  // immediate error instead of a round trip that would fail anyway.
  const habit = aiDailySanitize(el("aiHabitName").value.trim());
  if (!habit) { showMsg("aiHabitMsg", "Please enter a habit first.", false); return; }
  if (habit.includes("|")) { showMsg("aiHabitMsg", "The habit name cannot contain the | character.", false); return; }
  if (aiHabitCodePoints(habit) > AI_HABIT_MAX_CODE_POINTS) {
    showMsg("aiHabitMsg", "Habit name is too long: maximum 100 characters.", false);
    return;
  }
  const targetRaw = el("aiHabitTarget").value.trim();
  let target = null;
  if (targetRaw !== "") {
    target = aiHabitValidTarget(targetRaw);
    if (target === null) {
      showMsg("aiHabitMsg", "Target streak must be a whole number from 1 to 365.", false);
      return;
    }
  }
  const frequency = el("aiHabitFrequency").value;
  if (frequency !== "daily" && frequency !== "weekly") {
    showMsg("aiHabitMsg", "Frequency must be daily or weekly.", false);
    return;
  }
  const today = el("aiHabitToday").value.trim();
  if (today && !aiHabitValidToday(today)) {
    showMsg("aiHabitMsg", "Reference date must be a valid date within 2 days of today (YYYY-MM-DD).", false);
    return;
  }
  const input = aiDailySanitize(el("aiHabitInput").value.trim());
  if (input && aiHabitCodePoints(input) > AI_HABIT_MAX_INPUT_CODE_POINTS) {
    showMsg("aiHabitMsg", "Extra notes are too long: maximum 2000 characters.", false);
    return;
  }
  const body = { habit, frequency };
  if (target !== null) body.target_streak = target;
  if (today) body.today = today;
  if (input) body.input = input;
  btn.disabled = true;
  const oldText = btn.textContent;
  btn.textContent = "Thinking…";
  replyBox.innerHTML = '<div class="loading">Thinking…</div>';
  try {
    const r = await api("/api/ai/habit", { method: "POST", body: JSON.stringify(body) });
    replyBox.innerHTML = esc(r.reply || "");
    let msg = "AI habit advice received.";
    if (typeof r.history_id === "number") msg += " (history #" + r.history_id + ")";
    showMsg("aiHabitMsg", msg, true);
    if (r.history_id === 0) {
      showMsg("aiHabitWarn", "Note: the reply was received, but it was NOT saved to your AI history.", false);
    }
  } catch (e) {
    // A stale reply must never stay on screen after an error.
    replyBox.innerHTML = "";
    // api() already forces a logout on 401; the other messages come
    // from the server (data.error) and are shown with a short note.
    const m = e.message || "Request failed.";
    if (m === "invalid input") showMsg("aiHabitMsg", "Invalid input — please check the fields and try again.", false);
    else if (m === "AI requires the C++ server") showMsg("aiHabitMsg", "AI requires the C++ server — this Python fallback server cannot run AI features.", false);
    else if (m === "AI unavailable" || m === "AI configuration error" || m === "AI request limit reached") showMsg("aiHabitMsg", m + " Please try again later.", false);
    else if (m === "AI request timed out") showMsg("aiHabitMsg", "AI request timed out. Please try again.", false);
    else if (m === "AI request failed") showMsg("aiHabitMsg", "AI request failed. Please try again later.", false);
    else showMsg("aiHabitMsg", m, false);
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
  }
});

// -- AI History (Phase 3.7) ----------------------------------------
// GET /api/ai/history (limit 50, newest first) + DELETE
// /api/ai/history/{id}. Only the caller's own rows are ever
// returned (owner-filtered server-side; ADMIN gets no exception).
// Entries are rendered with esc(), never raw innerHTML; responses
// keep their line breaks via the .ai-reply CSS class. The list is
// loaded when the section opens and after a delete; the filter
// re-renders the already-loaded entries without a network call.
const AI_HISTORY_FEATURES = {
  "daily-decision": "Daily Decision", "task-analyzer": "Task Analyzer",
  "study-planner": "Study Planner", "problem-solver": "Problem Solver",
  "budget": "Budget", "habit": "Habit"
};
let aiHistoryEntries = [];

async function loadAiHistory() {
  const list = el("aiHistoryList");
  const filter = el("aiHistoryFilter");
  clearMsg("aiHistoryMsg");
  list.innerHTML = '<div class="loading">Loading AI history…</div>';
  filter.disabled = true;
  try {
    const data = await api("/api/ai/history?limit=50");
    aiHistoryEntries = Array.isArray(data.history) ? data.history : [];
    renderAiHistory();
  } catch (e) {
    // A stale list must never stay on screen after an error.
    // api() already forces a logout on 401.
    aiHistoryEntries = [];
    list.innerHTML = "";
    showMsg("aiHistoryMsg", e.message || "Request failed.", false);
  } finally {
    filter.disabled = false;
  }
}
function renderAiHistory() {
  const list = el("aiHistoryList");
  const filter = el("aiHistoryFilter").value;
  const shown = filter === "all" ? aiHistoryEntries
    : aiHistoryEntries.filter(e => e.feature === filter);
  if (!shown.length) {
    list.innerHTML = aiHistoryEntries.length
      ? "<div class='empty'>No entries for this feature yet.</div>"
      : "<div class='empty'>No AI history yet.</div>";
    return;
  }
  list.innerHTML = shown.map(e =>
    `<div class="ai-history-entry" data-id="${e.id}">` +
    `<div class="ai-history-head"><b>${esc(AI_HISTORY_FEATURES[e.feature] || e.feature)}</b> ` +
    `<span class="muted">${esc(e.created_at || "")}</span> ` +
    `<button class="btn btn-danger" onclick="deleteAiHistory(${e.id})">Delete</button></div>` +
    `<div class="muted">You asked:</div><div class="ai-reply">${esc(e.prompt || "")}</div>` +
    `<div class="muted">AI answered:</div><div class="ai-reply">${esc(e.response || "")}</div></div>`
  ).join("");
}
async function deleteAiHistory(id) {
  if (!window.confirm("Delete this AI history entry?")) return;
  let msg = null, ok = true;
  try {
    await api("/api/ai/history/" + id, { method: "DELETE" });
    msg = "Entry deleted.";
  } catch (e) {
    // 404 means the entry is already gone (another tab, or a
    // second delete). Any other error keeps the list as it is.
    if ((e.message || "") === "History entry not found.") {
      msg = "That entry was already removed.";
      ok = false;
    } else {
      // api() already forces a logout on 401; any other error
      // keeps the list as it is, with the server message shown.
      showMsg("aiHistoryMsg", e.message || "Request failed.", false);
      return;
    }
  }
  // Always re-read the list from the server (like the Decision and
  // Task deletes do): what is on screen must be the server truth,
  // never a locally-filtered copy that can silently come back on
  // the next refresh. (Template-delete bug, 2026-11-10: the old
  // code filtered the local list only, so a delete the server did
  // not carry out still looked deleted until the next load.)
  await loadAiHistory();
  showMsg("aiHistoryMsg", msg, ok);
}
window.deleteAiHistory = deleteAiHistory;
el("aiHistoryFilter").addEventListener("change", renderAiHistory);
el("aiHistoryRefreshBtn").addEventListener("click", loadAiHistory);

// -- tasks ----------------------------------------------------------
async function loadTasks() {
  el("taskList").innerHTML = '<div class="loading">Loading tasks…</div>';
  try {
    const tasks = await api("/api/tasks");
    el("taskList").innerHTML = tasks.length ? "<table><tr><th>Title</th><th>Score</th><th>Deadline</th><th>Status</th><th></th></tr>" +
      tasks.map(t => `<tr><td>${esc(t.title)}</td><td>${t.score}</td><td>${esc(t.deadline || "Not set")}</td><td>${esc(t.status)}</td><td>` +
        `<button class="btn btn-primary" onclick="setTaskStatus(${t.id},'Completed')">Complete</button>` +
        `<button class="btn btn-danger" onclick="deleteTask(${t.id})">Delete</button></td></tr>`).join("") + "</table>"
      : "<div class='empty'>No tasks yet. Add your first task above.</div>";
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
async function setTaskStatus(id, status) {
  try { await api("/api/tasks/" + id, { method: "PATCH", body: JSON.stringify({ status }) }); loadTasks(); loadStatusList(); }
  catch (e) { showMsg("globalMsg", e.message, false); }
}
async function deleteTask(id) {
  try { await api("/api/tasks/" + id, { method: "DELETE" }); loadTasks(); loadStatusList(); }
  catch (e) { showMsg("globalMsg", e.message, false); }
}
window.setTaskStatus = setTaskStatus; window.deleteTask = deleteTask;

el("taskAddBtn").addEventListener("click", async () => {
  try {
    await api("/api/tasks", { method: "POST", body: JSON.stringify({
      title: el("taskTitle").value.trim(), urgency: +el("taskUrgency").value,
      importance: +el("taskImportance").value, deadline: el("taskDeadline").value }) });
    showMsg("taskMsg", "Task added.", true); loadTasks();
  } catch (e) { showMsg("taskMsg", e.message, false); }
});

// -- priority -------------------------------------------------------
el("prBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/priority", { method: "POST", body: JSON.stringify({
      urgency: +el("prUrgency").value, importance: +el("prImportance").value }) });
    showMsg("prMsg", "Priority Score: " + r.score + "/50 — " + r.level, true);
  } catch (e) { showMsg("prMsg", e.message, false); }
});

// -- budget ---------------------------------------------------------
el("budBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/budget?income=" + encodeURIComponent(el("budIncome").value) +
      "&expenses=" + encodeURIComponent(el("budExpenses").value));
    showMsg("budMsg", "Remaining balance: " + r.remaining.toFixed(2) + " | Decision: " + r.decision, true);
  } catch (e) { showMsg("budMsg", e.message, false); }
});

// -- finance --------------------------------------------------------
async function loadTransactions() {
  try {
    const txs = await api("/api/transactions");
    const income = txs.filter(t => t.type === "income").reduce((s, t) => s + t.amount, 0);
    const expense = txs.filter(t => t.type === "expense").reduce((s, t) => s + t.amount, 0);
    el("txList").innerHTML = "<p>Balance: <b>" + (income - expense).toFixed(2) + "</b> (income " + income.toFixed(2) + ", expense " + expense.toFixed(2) + ")</p>" +
      (txs.length ? "<table><tr><th>Date</th><th>Type</th><th>Category</th><th>Amount</th><th>Note</th></tr>" +
        txs.map(t => `<tr><td>${esc(t.date)}</td><td>${esc(t.type)}</td><td>${esc(t.category)}</td><td>${t.amount}</td><td>${esc(t.note)}</td></tr>`).join("") + "</table>"
        : "<div class='empty'>No transactions yet.</div>");
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
el("txBtn").addEventListener("click", async () => {
  try {
    await api("/api/transactions", { method: "POST", body: JSON.stringify({
      date: el("txDate").value, type: el("txType").value, category: el("txCategory").value.trim(),
      amount: +el("txAmount").value, note: el("txNote").value }) });
    showMsg("txMsg", "Transaction saved.", true); loadTransactions();
  } catch (e) { showMsg("txMsg", e.message, false); }
});

// -- savings --------------------------------------------------------
async function loadSavings() {
  try {
    const goals = await api("/api/savings");
    el("svList").innerHTML = goals.length ? "<table><tr><th>Goal</th><th>Target</th><th>Saved</th><th>Remaining</th></tr>" +
      goals.map(g => `<tr><td>${esc(g.name)}</td><td>${g.target}</td><td>${g.saved}</td><td>${(g.target - g.saved).toFixed(2)}</td></tr>`).join("") + "</table>"
      : "<div class='empty'>No savings goals yet.</div>";
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
el("svBtn").addEventListener("click", async () => {
  try {
    await api("/api/savings", { method: "POST", body: JSON.stringify({
      name: el("svName").value.trim(), target: +el("svTarget").value }) });
    showMsg("svMsg", "Goal added.", true); loadSavings();
  } catch (e) { showMsg("svMsg", e.message, false); }
});
el("svAddBtn").addEventListener("click", async () => {
  try {
    const g = await api("/api/savings/add", { method: "POST", body: JSON.stringify({
      name: el("svAddName").value.trim(), amount: +el("svAddAmount").value }) });
    showMsg("svAddMsg", "Updated " + g.name + ": saved " + g.saved + " of " + g.target, true); loadSavings();
  } catch (e) { showMsg("svAddMsg", e.message, false); }
});

// -- habits ---------------------------------------------------------
async function loadHabits() {
  try {
    const habits = await api("/api/habits");
    el("hbList").innerHTML = habits.length ? "<table><tr><th>Habit</th><th>Recorded dates</th></tr>" +
      habits.map(h => `<tr><td>${esc(h.habit)}</td><td>${esc(h.dates.join(", "))}</td></tr>`).join("") + "</table>"
      : "<div class='empty'>No habit records yet.</div>";
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
el("hbBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/habits", { method: "POST", body: JSON.stringify({
      habit: el("hbName").value.trim(), date: el("hbDate").value }) });
    showMsg("hbMsg", "Recorded. Total " + r.total + ", consecutive streak " + r.streak + " day(s).", true); loadHabits();
  } catch (e) { showMsg("hbMsg", e.message, false); }
});
el("hbCheckBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/habits/streak?habit=" + encodeURIComponent(el("hbCheck").value.trim()));
    showMsg("hbCheckMsg", r.habit + ": total " + r.total + ", consecutive streak " + r.streak + " day(s), latest " + (r.latest || "—"), true);
  } catch (e) { showMsg("hbCheckMsg", e.message, false); }
});

// -- reports --------------------------------------------------------
async function showReport(url) {
  try {
    const r = await api(url);
    showMsg("repMsg", r.label + ": " + r.count + " transactions, income " + r.income.toFixed(2) +
      ", expense " + r.expense.toFixed(2) + ", balance " + r.balance.toFixed(2) + ". " +
      r.transactions.map(t => t.date + " " + t.type + " " + t.amount).join("; "), true);
  } catch (e) { showMsg("repMsg", e.message, false); }
}
el("repMonthBtn").addEventListener("click", () => showReport("/api/reports?month=" + encodeURIComponent(el("repMonth").value.trim())));
el("repWeekBtn").addEventListener("click", () => showReport("/api/reports?week_end=" + encodeURIComponent(el("repWeek").value)));


// -- new sections ---------------------------------------------------
// Search & History: same decisions.txt, filtered by keyword/type.
async function loadHistory() {
  el("histList").innerHTML = '<div class="loading">Searching history…</div>';
  try {
    const q = new URLSearchParams({ search: el("histSearch").value.trim(), type: el("histType").value });
    let ds = await api("/api/decisions?" + q.toString());
    if (el("histSort").value === "priority") ds = ds.slice().sort((a, b) => b.priority - a.priority);
    else ds = ds.slice().reverse();
    el("histList").innerHTML = ds.length ? "<table><tr><th>ID</th><th>Date</th><th>Type</th><th>Priority</th><th>Title</th></tr>" +
      ds.map(d => `<tr><td>${esc(d.id)}</td><td>${esc(d.date)}</td><td>${esc(d.type)}</td><td>${d.priority}</td><td>${esc(d.title)}</td></tr>`).join("") + "</table>"
      : "<div class='empty'>No matching decisions. Try a different keyword, or create a decision first.</div>";
    showMsg("histMsg", ds.length + " matching decision(s).", true);
  } catch (e) { showMsg("histMsg", e.message, false); }
}
el("histBtn").addEventListener("click", loadHistory);

// Task Status: same tasks.txt, status dropdown mirrors task_status.cpp.
async function loadStatusList() {
  const box = el("statusList"); if (!box) return;
  box.innerHTML = '<div class="loading">Loading task statuses…</div>';
  try {
    const tasks = await api("/api/tasks");
    box.innerHTML = tasks.length ? "<table><tr><th>Title</th><th>Score</th><th>Deadline</th><th>Status</th></tr>" +
      tasks.map(t => `<tr><td>${esc(t.title)}</td><td>${t.score}</td><td>${esc(t.deadline || "Not set")}</td><td><select onchange="setTaskStatus(${t.id}, this.value)">` +
        ["Pending", "In Progress", "Completed"].map(s => `<option value="${s}"${s === t.status ? " selected" : ""}>${s}</option>`).join("") + "</select></td></tr>").join("") + "</table>"
      : "<div class='empty'>No tasks yet. Add a task in Task Management first.</div>";
  } catch (e) { showMsg("globalMsg", e.message, false); }
}

// Deadline Alerts: mirrors deadline_alert.cpp.
async function loadDeadlines() {
  el("dlList").innerHTML = '<div class="loading">Checking deadlines…</div>';
  try {
    const today = el("dlDate").value;
    const ds = await api("/api/deadlines" + (today ? "?today=" + encodeURIComponent(today) : ""));
    const badge = a => a === "OVERDUE" ? "badge-danger" : a === "DUE TODAY" ? "badge-warn" : a === "UPCOMING" ? "badge" : "badge-warn";
    el("dlList").innerHTML = ds.length ? "<table><tr><th>Title</th><th>Deadline</th><th>Status</th><th>Alert</th></tr>" +
      ds.map(d => `<tr><td>${esc(d.title)}</td><td>${esc(d.deadline || "Not set")}</td><td>${esc(d.status)}</td><td><span class="badge ${badge(d.alert)}">${esc(d.alert)}</span></td></tr>`).join("") + "</table>"
      : "<div class='empty'>No open tasks with deadlines. Completed tasks are skipped, as in the C++ module.</div>";
    showMsg("dlMsg", ds.length + " open task(s) checked.", true);
  } catch (e) { showMsg("dlMsg", e.message, false); }
}
el("dlBtn").addEventListener("click", loadDeadlines);

// Decision Explanation: mirrors decision_explanation.cpp.
el("exBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/decision-explanation", { method: "POST", body: JSON.stringify({
      urgency: +el("exUrgency").value, importance: +el("exImportance").value }) });
    showMsg("exMsg", r.formula + ". " + r.calculation + ". " + r.explanation + " Recommendation: " + r.recommendation, true);
  } catch (e) { showMsg("exMsg", e.message, false); }
});

// Study Planner: mirrors study_planner.cpp (calculated, not saved).
el("spBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/study-planner", { method: "POST", body: JSON.stringify({
      subject: el("spSubject").value.trim(), days: +el("spDays").value, hours: +el("spHours").value }) });
    showMsg("spMsg", "Total planned hours: " + r.totalHours + " (" + r.days + " days x " + r.hoursPerDay + " hour(s) per day).", true);
    el("spList").innerHTML = "<table><tr><th>Day</th><th>Plan</th></tr>" +
      r.plan.map(p => `<tr><td>${p.day}</td><td>${esc(p.text)}</td></tr>`).join("") + "</table>";
  } catch (e) { showMsg("spMsg", e.message, false); }
});

// Time Allocation: mirrors time_allocation.cpp.
el("taBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/time-allocation", { method: "POST", body: JSON.stringify({
      sleep: +el("taSleep").value, study: +el("taStudy").value, work: +el("taWork").value, other: +el("taOther").value }) });
    const warn = r.warning ? " Warning: " + r.warning : " Remaining: " + r.remaining + " hour(s).";
    showMsg("taMsg", "Total allocated: " + r.total + " hour(s)." + warn, !r.warning);
  } catch (e) { showMsg("taMsg", e.message, false); }
});

// User Profile: mirrors showProfile(); admins also get the user list.
async function loadProfile() {
  try {
    const me = await api("/api/me");
    el("profileInfo").innerHTML = `<p><b>Username:</b> ${esc(me.username)}</p><p><b>Role:</b> <span class="badge">${esc(me.role)}</span></p>`;
    try {
      const users = await api("/api/users");
      el("profileUsers").innerHTML = "<h3>Registered users (ADMIN only)</h3><table><tr><th>Username</th><th>Role</th></tr>" +
        users.map(u => `<tr><td>${esc(u.username)}</td><td>${esc(u.role)}</td></tr>`).join("") + "</table>";
    } catch (e) {
      el("profileUsers").innerHTML = "<div class='empty'>User list is available to ADMIN only.</div>";
    }
  } catch (e) { showMsg("globalMsg", e.message, false); }
}

// Settings: theme (browser only), backend info, password change.
async function loadSettingsBackend() {
  try {
    const info = await api("/api/info");
    el("setBackend").innerHTML = `<p><b>Backend:</b> ${esc(info.backend)} (${esc(info.server)})</p><p><b>Shared data files:</b> ${info.dataFiles.map(esc).join(", ")}</p><p class="muted">The dashboard and the C++ console app read and write the same files in the same formats.</p>`;
  } catch (e) { el("setBackend").innerHTML = "<div class='empty'>Backend info unavailable: " + esc(e.message) + "</div>"; }
}
el("setThemeBtn").addEventListener("click", () => {
  applyTheme(el("setTheme").value);
  showMsg("setThemeMsg", "Theme saved in this browser.", true);
});
el("cpBtn").addEventListener("click", async () => {
  try {
    await api("/api/change-password", { method: "POST", body: JSON.stringify({
      currentPassword: el("cpCurrent").value, newPassword: el("cpNew").value }) });
    showMsg("cpMsg", "Password changed successfully.", true);
    el("cpCurrent").value = ""; el("cpNew").value = "";
  } catch (e) { showMsg("cpMsg", e.message, false); }
});


el("heroLoginBtn").addEventListener("click", () => showSection("auth"));
el("heroRegBtn").addEventListener("click", () => showSection("auth"));

// -- charts (real data only, pure CSS bars, no library) --------------
function chartHtml(rows, max) {
  if (!rows.length) return "<div class='empty'>No data yet.</div>";
  return rows.map(r => `<div class="chart-bar"><span class="label">${esc(r.label)}</span><span class="bar ${r.cls || ""}" style="width:${max > 0 ? Math.round(r.value / max * 100) : 0}%"></span><span class="value">${r.value.toFixed(2)}</span></div>`).join("");
}
async function loadAnalytics() {
  try {
    const txs = await api("/api/transactions");
    const byMonth = {};
    for (const t of txs) {
      const m = t.date.slice(0, 7);
      if (!byMonth[m]) byMonth[m] = { income: 0, expense: 0 };
      if (t.type === "income") byMonth[m].income += t.amount; else byMonth[m].expense += t.amount;
    }
    const months = Object.keys(byMonth).sort();
    let html = "";
    let max = 0;
    for (const m of months) max = Math.max(max, byMonth[m].income, byMonth[m].expense);
    for (const m of months) {
      html += `<h4>${esc(m)}</h4>` + chartHtml([
        { label: "Income", value: byMonth[m].income, cls: "" },
        { label: "Expense", value: byMonth[m].expense, cls: "expense" }], max);
    }
    el("anChart").innerHTML = html || "<div class='empty'>No transactions yet.</div>";
    const sv = await api("/api/savings");
    let smax = 0; for (const g of sv) smax = Math.max(smax, g.target, g.saved);
    el("anSavings").innerHTML = sv.length ? sv.map(g => `<h4>${esc(g.name)}</h4>` + chartHtml([
      { label: "Target", value: g.target, cls: "" },
      { label: "Saved", value: g.saved, cls: "savings" }], smax)).join("") : "<div class='empty'>No savings goals yet.</div>";
  } catch (e) { el("anChart").innerHTML = "<div class='empty'>" + esc(e.message) + "</div>"; }
}

// -- team-completion sections ---------------------------------------
// Compare Options (Nuriya, menu 12): not saved, like the console.
el("cmpBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/compare-options", { method: "POST", body: JSON.stringify({
      name1: el("cmpName1").value.trim(), benefit1: +el("cmpBenefit1").value, cost1: +el("cmpCost1").value, risk1: +el("cmpRisk1").value,
      name2: el("cmpName2").value.trim(), benefit2: +el("cmpBenefit2").value, cost2: +el("cmpCost2").value, risk2: +el("cmpRisk2").value }) });
    const sug = r.equal ? "Both options have equal scores." : "Suggested option: " + r.suggested;
    showMsg("cmpMsg", r.name1 + " Score: " + r.score1 + " | " + r.name2 + " Score: " + r.score2 + ". " + sug, true);
  } catch (e) { showMsg("cmpMsg", e.message, false); }
});

// Problem Solver (Sweety, menu 35): saved as a Problem record.
el("psBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/problem-solver", { method: "POST", body: JSON.stringify({
      problem: el("psName").value.trim(), difficulty: +el("psDifficulty").value, time: +el("psTime").value }) });
    showMsg("psMsg", "Suggestion: " + r.suggestion + " (saved as decision " + r.record.id + ")", true);
  } catch (e) { showMsg("psMsg", e.message, false); }
});

// Admin Panel (Rifat, menu 5): usernames + roles only.
async function loadAdmin() {
  try {
    const a = await api("/api/admin");
    el("adminInfo").innerHTML = `<p><b>Total users:</b> ${a.total} (${a.admins} ADMIN, ${a.users} USER)</p><table><tr><th>Username</th><th>Role</th></tr>` +
      a.list.map(u => `<tr><td>${esc(u.username)}</td><td>${esc(u.role)}</td></tr>`).join("") + "</table>";
  } catch (e) {
    el("adminInfo").innerHTML = "<div class='empty'>Admin panel is available to ADMIN only. (" + esc(e.message) + ")</div>";
  }
}

// Daily Summary (Sweety, menu 36) + Export (menus 26-27), in Reports.
el("dsBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/daily-summary", { method: "POST", body: JSON.stringify({
      income: +el("dsIncome").value, expenses: +el("dsExpenses").value,
      habitsCompleted: +el("dsCompleted").value, habitsPlanned: +el("dsPlanned").value }) });
    showMsg("dsMsg", "Balance: " + r.balance.toFixed(2) + " | Habit completion: " + r.habitRate.toFixed(2) + "%. Saved to daily_report.txt.", true);
  } catch (e) { showMsg("dsMsg", e.message, false); }
});
async function downloadExport(fmt, filename) {
  try {
    const r = await api("/api/export?format=" + fmt);
    const blob = new Blob([r.content], { type: fmt === "csv" ? "text/csv" : "text/plain" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = r.filename || filename;
    a.click(); URL.revokeObjectURL(a.href);
    showMsg("xpMsg", "Exported " + (r.filename || filename) + ".", true);
  } catch (e) { showMsg("xpMsg", e.message, false); }
}
el("exTxtBtn").addEventListener("click", () => downloadExport("txt", "financial_report.txt"));
el("exCsvBtn").addEventListener("click", () => downloadExport("csv", "financial_report.csv"));

// Habit Decision (menu 40) + Streak Calculator (menu 41), in Habits.
el("hdBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/habit-decision", { method: "POST", body: JSON.stringify({
      completed: +el("hdCompleted").value, planned: +el("hdPlanned").value }) });
    showMsg("hdMsg", "Today's completion: " + r.percentage.toFixed(2) + "%. " + r.message, true);
  } catch (e) { showMsg("hdMsg", e.message, false); }
});
el("hsBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/habit-streak-calc", { method: "POST", body: JSON.stringify({
      previousDays: +el("hsPrev").value, completedToday: +el("hsToday").value }) });
    showMsg("hsMsg", "Current streak: " + r.streak + " day(s). " + r.message, true);
  } catch (e) { showMsg("hsMsg", e.message, false); }
});

// Savings Calculator (menu 39), in Savings.
el("scBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/savings-calculator", { method: "POST", body: JSON.stringify({
      target: +el("scTarget").value, current: +el("scCurrent").value, monthly: +el("scMonthly").value }) });
    showMsg("scMsg", r.message ? r.message : "Amount remaining: " + r.remaining.toFixed(2) + " | Estimated time: " + r.months + " month(s).", true);
  } catch (e) { showMsg("scMsg", e.message, false); }
});

// Error Log (menu 33), in History.
el("elBtn").addEventListener("click", async () => {
  try {
    const lines = await api("/api/error-log");
    el("elList").innerHTML = lines.length ? "<table><tr><th>Log line</th></tr>" + lines.map(l => `<tr><td>${esc(l)}</td></tr>`).join("") + "</table>"
      : "<div class='empty'>No errors logged yet.</div>";
  } catch (e) { el("elList").innerHTML = "<div class='empty'>" + esc(e.message) + "</div>"; }
});

// -- init -----------------------------------------------------------
// Start logged out, on Welcome, with protected nav hidden — even if
// a token is in sessionStorage. The dashboard is shown ONLY if the
// server verifies that token with /api/me. A stale, forged, or
// expired token therefore never shows the dashboard on refresh:
// /api/me returns 401, api() forces a logout to the Login page,
// and the local token is cleared. If the server is unreachable,
// the page stays on Welcome and no dashboard data is shown.
// Capture the stored credentials BEFORE setAuthState(false, ""),
// because setLoggedIn("") clears the username variable.
const storedToken = token, storedUser = username;
setAuthState(false, "");
showSection("landing");
checkBackend();
initGoogleSignIn();
if (storedToken && storedUser) {
  api("/api/me").then(me => {
    username = me.username;
    sessionStorage.setItem("pdps_user", me.username);
    setAuthState(true, me.username + " (" + me.role + ")");
    showSection("overview");
  }).catch(() => {
    // 401 case is already handled by api(): forced logout to Login.
    // Any other failure (server down) simply leaves the page on
    // Welcome with the dashboard hidden.
  });
}
