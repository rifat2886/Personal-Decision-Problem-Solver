// Personal Decision & Problem Solver — dashboard frontend.
// All data comes from server.py on the same origin (http://127.0.0.1:8000).
// There is no demo or fake data: if the server is not running, every
// section shows its error instead of invented numbers.

let token = sessionStorage.getItem("pdps_token") || "";
let username = sessionStorage.getItem("pdps_user") || "";

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
  box.className = "msg " + (ok ? "ok" : "err");
  box.textContent = text;
}

function clearMsg(id) {
  const box = el(id);
  if (box) { box.className = ""; box.textContent = ""; }
}

async function api(path, options) {
  const res = await fetch(path, Object.assign({
    headers: {
      "Content-Type": "application/json",
      "Authorization": token ? "Bearer " + token : ""
    }
  }, options || {}));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ("Request failed: " + res.status));
  return data;
}

function setLoggedIn(name) {
  username = name || "";
  el("who").textContent = name ? ("Logged in as " + name) : "";
  el("logoutBtn").classList.toggle("hidden", !name);
}

function showSection(name) {
  document.querySelectorAll("section").forEach(s => s.classList.toggle("active", s.id === name));
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("active", b.dataset.section === name));
  if (name === "overview") loadOverview();
  if (name === "tasks") loadTasks();
  if (name === "finance") loadTransactions();
  if (name === "savings") loadSavings();
  if (name === "habits") loadHabits();
}

document.querySelectorAll("nav button").forEach(b => {
  b.addEventListener("click", () => showSection(b.dataset.section));
});

el("logoutBtn").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST", body: "{}" }); } catch (e) {}
  token = ""; username = "";
  sessionStorage.removeItem("pdps_token");
  sessionStorage.removeItem("pdps_user");
  setLoggedIn("");
  showSection("auth");
});

// -- auth -----------------------------------------------------------
el("loginBtn").addEventListener("click", async () => {
  try {
    const data = await api("/api/login", { method: "POST", body: JSON.stringify({
      username: el("loginUser").value.trim(), password: el("loginPass").value }) });
    token = data.token;
    sessionStorage.setItem("pdps_token", token);
    sessionStorage.setItem("pdps_user", data.username);
    setLoggedIn(data.username + " (" + data.role + ")");
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
  try {
    const o = await api("/api/overview");
    el("overviewCards").innerHTML = [
      ["Decisions", o.decisions], ["Tasks", o.tasks + " (" + o.tasksPending + " pending)"],
      ["Balance", o.balance.toFixed(2)], ["Income", o.income.toFixed(2)],
      ["Expense", o.expense.toFixed(2)],
      ["Savings", o.savingsSaved.toFixed(2) + " / " + o.savingsTarget.toFixed(2) + " (" + o.savingsGoals + " goals)"]
    ].map(([k, v]) => `<div class="card"><div class="muted">${k}</div><p class="big">${v}</p></div>`).join("");
    const decisions = await api("/api/decisions");
    el("overviewDecisions").innerHTML = decisions.length ? "<table><tr><th>ID</th><th>Date</th><th>Type</th><th>Priority</th><th>Title</th><th></th></tr>" +
      decisions.slice(-20).reverse().map(d =>
        `<tr><td>${esc(d.id)}</td><td>${esc(d.date)}</td><td>${esc(d.type)}</td><td>${d.priority}</td><td>${esc(d.title)}</td>` +
        `<td><button class="primary small danger" onclick="deleteDecision(${d.id})">Delete</button></td></tr>`).join("") + "</table>"
      : "<p class='muted'>No decisions yet. Create one from Daily Decision, Tasks, or Priority.</p>";
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
  try {
    const tasks = await api("/api/tasks");
    el("taskList").innerHTML = tasks.length ? "<table><tr><th>Title</th><th>Score</th><th>Deadline</th><th>Status</th><th></th></tr>" +
      tasks.map(t => `<tr><td>${esc(t.title)}</td><td>${t.score}</td><td>${esc(t.deadline || "Not set")}</td><td>${esc(t.status)}</td><td>` +
        (t.status === "Pending" ? `<button class="primary small" onclick="setTaskStatus(${t.id},'Completed')">Complete</button>` : "") +
        `<button class="primary small danger" onclick="deleteTask(${t.id})">Delete</button></td></tr>`).join("") + "</table>"
      : "<p class='muted'>No tasks yet.</p>";
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
async function setTaskStatus(id, status) {
  try { await api("/api/tasks/" + id, { method: "PATCH", body: JSON.stringify({ status }) }); loadTasks(); }
  catch (e) { showMsg("globalMsg", e.message, false); }
}
async function deleteTask(id) {
  try { await api("/api/tasks/" + id, { method: "DELETE" }); loadTasks(); }
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
        : "<p class='muted'>No transactions yet.</p>");
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
      : "<p class='muted'>No savings goals yet.</p>";
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
      : "<p class='muted'>No habit records yet.</p>";
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

// -- init -----------------------------------------------------------
if (token && username) {
  setLoggedIn(username);
  showSection("overview");
} else {
  setLoggedIn("");
}
