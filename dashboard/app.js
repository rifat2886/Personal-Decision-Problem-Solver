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

async function api(path, options) {
  const res = await fetch(API_BASE + path, Object.assign({
    headers: {
      "Content-Type": "application/json",
      "Authorization": token ? "Bearer " + token : ""
    }
  }, options || {}));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && path !== "/api/login" && path !== "/api/register") {
      forceLogoutToLogin("Session expired. Please log in again.");
      throw new Error("Session expired. Please log in again.");
    }
    throw new Error(data.error || ("Request failed: " + res.status));
  }
  return data;
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
  if (name === "overview") loadOverview();
  if (name === "history") loadHistory();
  if (name === "tasks") loadTasks();
  if (name === "taskstatus") loadStatusList();
  if (name === "deadlines") loadDeadlines();
  if (name === "finance") loadTransactions();
  if (name === "savings") loadSavings();
  if (name === "habits") loadHabits();
  if (name === "profile") loadProfile();
  if (name === "admin") loadAdmin();
  if (name === "analytics") loadAnalytics();
  if (name === "settings") loadSettingsBackend();
}

document.querySelectorAll("nav button").forEach(b => {
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
    const data = await api("/api/register", { method: "POST", body: JSON.stringify({
      username: el("regUser").value.trim(), password: el("regPass").value }) });
    showMsg("regMsg", "Registered as " + data.username + " (" + data.role + "). Please log in.", true);
  } catch (e) { showMsg("regMsg", e.message, false); }
});

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
  if (!confirm("Restore will replace decisions with the backup. Continue?")) return;
  try {
    const r = await api("/api/restore", { method: "POST", body: "{}" });
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
