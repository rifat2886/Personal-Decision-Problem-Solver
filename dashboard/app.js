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
  if (id === "globalMsg") { box.innerHTML = `<div class="msg ${cls}"></div>`; box.firstChild.textContent = text; replayAnim(box.firstChild, "animate__fadeIn", 350); return; }
  box.className = "msg " + cls;
  box.textContent = text;
  // Success slides in; errors shake instead — only one animation
  // at a time, because two animations both driving `transform`
  // would fight and the shake would lose. The slide-in class is
  // re-applied fresh each time (replay pattern) so repeat
  // messages animate again.
  if (ok) {
    box.classList.remove("anim-msg-in");
    void box.offsetWidth;
    box.classList.add("anim-msg-in");
  } else {
    replayAnim(box, "animate__shakeX", 500);
  }
}

function clearMsg(id) {
  const box = el(id);
  if (box) { box.className = ""; box.textContent = ""; box.innerHTML = ""; }
}

// -- motion (dashboard animations) ----------------------------------
// Animate.css 4.1.1 is vendored as dashboard/animate.min.css and
// linked in index.html (never a CDN). The helpers below wire it
// up, plus the hand-tuned JS effects (typing, count-up). Every
// helper checks REDUCED_MOTION first: with the OS "reduce
// motion" setting on, nothing animates — content appears at its
// final state at once. The CSS kill-switch in style.css covers
// the stylesheet side of the same promise.
// Delays are deliberately uneven (0, 70, 130, 210, 280, 360, 420,
// 500ms): a fixed 50ms step looks machine-made; varied gaps read
// as a hand dealing cards.
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const ANIM_DELAYS = [0, 70, 130, 210, 280, 360, 420, 500];

// Restart one Animate.css animation on an element: remove the
// classes, force a reflow, add them back. The classes are left in
// place afterwards (a finished animation has no visual effect),
// which also keeps the applied animation observable for tests.
// ms overrides the library's 1s default via its own CSS variable.
function replayAnim(elm, cls, ms) {
  if (!elm || REDUCED_MOTION) return;
  elm.classList.remove("animate__animated", cls);
  void elm.offsetWidth; // reflow: restarting the same animation
  if (ms) elm.style.setProperty("--animate-duration", (ms / 1000) + "s");
  elm.classList.add("animate__animated", cls);
}

// Stagger a section's cards: first 8 cards get anim-card with
// varied delays; later cards animate with no delay. Called from
// showSection on every navigation (the animation restarts because
// display:none took the section out of the render tree). The
// classes are applied even under reduced motion — the CSS
// kill-switch collapses them to an instant snap, which is the
// behaviour the browser test checks.
function staggerCards(section) {
  if (!section) return;
  section.querySelectorAll(".card").forEach((card, i) => {
    card.classList.add("anim-card");
    card.style.setProperty("--anim-delay", (i < ANIM_DELAYS.length ? ANIM_DELAYS[i] : 0) + "ms");
  });
}

// Stagger list rows (table rows or history entries): opacity-only
// fade, first 10 rows staggered, the rest plain. Called after a
// list renders. Table rows cannot be transformed, so anim-row is
// opacity-only by design (see style.css). As with staggerCards,
// the classes are applied even under reduced motion and the CSS
// kill-switch collapses them.
function staggerRows(container, selector) {
  if (!container) return;
  container.querySelectorAll(selector).forEach((row, i) => {
    if (i >= 10) return;
    row.classList.add("anim-row");
    row.style.setProperty("--anim-delay", ANIM_DELAYS[i % ANIM_DELAYS.length] + "ms");
  });
}

// AI reply typing: reveal the text in word-sized chunks so it
// reads like someone typing, not a wall appearing at once. The
// split keeps each chunk's trailing whitespace attached, so the
// final textContent is byte-identical to the reply (line breaks
// included). Long replies type faster (bigger chunks) so the
// whole effect finishes in about 2 seconds. The blinking caret
// comes from the .typing class in style.css. Reduced motion:
// the full text appears at once, no caret.
function stopTyping(elm) {
  if (elm && elm._pdpsTypeTimer) { clearInterval(elm._pdpsTypeTimer); elm._pdpsTypeTimer = null; }
  if (elm) elm.classList.remove("typing");
}
function typeInto(elm, text) {
  if (!elm) return;
  stopTyping(elm);
  const full = String(text || "");
  if (REDUCED_MOTION || !full) { elm.textContent = full; return; }
  const chunks = full.split(/(?<=\s)/);
  const perTick = Math.max(1, Math.ceil(chunks.length / 120));
  let shown = 0;
  elm.textContent = "";
  elm.classList.add("typing");
  elm._pdpsTypeTimer = setInterval(() => {
    shown += perTick;
    if (shown >= chunks.length) {
      stopTyping(elm);
      elm.textContent = full;
      return;
    }
    elm.textContent = chunks.slice(0, shown).join("");
  }, 16);
}

// Count-up: animate a number from `from` (default 0) to its
// target over ~750ms with an ease-out cubic, so it lands softly.
// Used for Overview stat values, the donut centre and the
// savings ring centres via [data-countup] attributes (see
// runCountUps), and for the habit ring % from its previous value.
// Reduced motion: the final value is written at once.
function countUp(elm, target, decimals, suffix, from) {
  const fmt = v => v.toFixed(decimals) + (suffix || "");
  if (!elm) return;
  if (REDUCED_MOTION) { elm.textContent = fmt(target); return; }
  const startVal = (typeof from === "number" && isFinite(from)) ? from : 0;
  const start = performance.now(), dur = 750;
  const step = now => {
    const t = Math.min((now - start) / dur, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    elm.textContent = fmt(startVal + (target - startVal) * eased);
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function runCountUps(root) {
  if (!root) return;
  root.querySelectorAll("[data-countup]").forEach(elm => {
    countUp(elm, parseFloat(elm.dataset.countup) || 0,
      parseInt(elm.dataset.decimals || "0", 10), elm.dataset.suffix || "");
  });
}

// AI "thinking" indicator: an infinite-loop loader — a gradient
// light travelling forever around a figure-8 path (pure inline
// SVG, no GIF, no image file, no CDN), with a short label.
// Replaces the old three-dot indicator. The gradient (Panze
// pink→blue) is defined in the SVG itself; the runner's stroke
// is set as a presentation attribute so it always resolves,
// while the dash travel lives in style.css (loopTravel). With
// reduced motion the CSS kill-switch freezes the runner and the
// indicator is static.
const LOOP_PATH = "M24 12 C21 6 15 4 11 6 C6 8 4 12 7 16 C10 20 18 19 24 12 C30 5 38 4 41 8 C44 12 42 16 37 18 C33 20 27 18 24 12 Z";
function aiThinkingHtml() {
  return '<div class="ai-thinking" role="status"><svg class="loop-loader" viewBox="0 0 48 24" aria-hidden="true"><defs><linearGradient id="loopGrad" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#B05AB9"/><stop offset="100%" stop-color="#215ACA"/></linearGradient></defs><path class="loop-track" d="' + LOOP_PATH + '"/><path class="loop-runner" d="' + LOOP_PATH + '" stroke="url(#loopGrad)"/></svg><span>AI is thinking…</span></div>';
}

// Skeleton loading rows: grey bars with a slow light sweep, used
// while a list loads (see style.css). Three rows read as "a list
// is coming"; the last one is shorter, like a real list's tail.
function skeletonHtml() {
  return '<div class="skeleton-row"></div><div class="skeleton-row"></div><div class="skeleton-row short"></div>';
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
  // Cards in the newly shown section stagger in (anim-card); the
  // section itself slides in via CSS (section.active). Called
  // synchronously here, before the browser paints, so the
  // animation starts from the first frame.
  staggerCards(el(name));
  setNav(false);
  if (name === "overview") { loadOverview(); updateAiWelcome(); }
  if (name === "history") loadHistory();
  if (name === "tasks") loadTasks();
  if (name === "taskstatus") loadStatusList();
  if (name === "deadlines") loadDeadlines();
  if (name === "finance") loadTransactions();
  if (name === "budget") loadBudgetCategories();
  if (name === "study") loadStudyPlans();
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

// Primary buttons pulse briefly on click (0.45s) — a visible
// "I heard you" before the page reacts. One delegated listener
// covers every primary button, including ones rendered later
// (task Complete, AI Ask buttons). No disabled check is needed:
// a button that was already disabled never fires the event at
// all, while the AI buttons disable themselves inside their own
// click handler (which runs before this bubble-phase listener)
// and must still pulse.
document.addEventListener("click", e => {
  const b = e.target.closest ? e.target.closest(".btn-primary") : null;
  if (b) replayAnim(b, "animate__pulse", 450);
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
// Button loading state (Login / Register): while the auth request
// is in flight the button shows a small inline loop spinner, is
// disabled, and then returns to exactly its previous content and
// disabled state. The previous disabled state is restored (not
// blindly cleared) because checkBackend() disables these buttons
// when no backend is connected.
function setBtnLoading(btn, loading, label) {
  if (!btn) return;
  if (loading) {
    if (btn.dataset.loading) return;
    btn.dataset.loading = "1";
    btn.dataset.oldHtml = btn.innerHTML;
    btn.dataset.wasDisabled = btn.disabled ? "1" : "0";
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span>' + label;
  } else {
    if (!btn.dataset.loading) return;
    btn.innerHTML = btn.dataset.oldHtml;
    btn.disabled = btn.dataset.wasDisabled === "1";
    delete btn.dataset.loading;
    delete btn.dataset.oldHtml;
    delete btn.dataset.wasDisabled;
  }
}
el("loginBtn").addEventListener("click", async () => {
  const btn = el("loginBtn");
  setBtnLoading(btn, true, "Logging in…");
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
  } catch (e) {
    showMsg("loginMsg", e.message, false);
    // A failed login shakes the login card — the error cannot be missed.
    replayAnim(el("loginBtn").closest(".card"), "animate__shakeX", 500);
  } finally {
    setBtnLoading(btn, false);
  }
});

el("regBtn").addEventListener("click", async () => {
  // Client-side validation first: a mismatch never reaches the
  // server, so it must not show the loading state either.
  if (el("regPass").value !== el("regPassConfirm").value) {
    showMsg("regMsg", "Passwords do not match.", false);
    replayAnim(el("regBtn").closest(".card"), "animate__shakeX", 500);
    return;
  }
  const btn = el("regBtn");
  setBtnLoading(btn, true, "Registering…");
  try {
    // Confirm password (auth fix, 2026-11-09): a typo at registration
    // used to lock the account with no recovery, so the form asks
    // twice and the server rejects a mismatch (400).
    const data = await api("/api/register", { method: "POST", body: JSON.stringify({
      username: el("regUser").value.trim(), password: el("regPass").value,
      confirm_password: el("regPassConfirm").value }) });
    showMsg("regMsg", "Registered as " + data.username + " (" + data.role + "). Please log in.", true);
  } catch (e) {
    showMsg("regMsg", e.message, false);
    replayAnim(el("regBtn").closest(".card"), "animate__shakeX", 500);
  } finally {
    setBtnLoading(btn, false);
  }
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
  el("overviewCards").innerHTML = skeletonHtml();
  try {
    const o = await api("/api/overview");
    // Stat values count up from 0 (runCountUps via gxAnimateIn
    // below); the number after the count is the suffix text, so
    // "5 (2 pending)" and "250.00 / 1000.00" keep their shape.
    const stats = [
      { label: "Decisions", target: o.decisions, decimals: 0, suffix: "", sub: "records in decisions.txt" },
      { label: "Tasks", target: o.tasks, decimals: 0, suffix: " (" + o.tasksPending + " pending)", sub: "in tasks.txt" },
      { label: "Balance", target: o.balance, decimals: 2, suffix: "", sub: "income minus expense" },
      { label: "Income", target: o.income, decimals: 2, suffix: "", sub: "total income" },
      { label: "Expense", target: o.expense, decimals: 2, suffix: "", sub: "total expense" },
      { label: "Savings", target: o.savingsSaved, decimals: 2, suffix: " / " + o.savingsTarget.toFixed(2), sub: o.savingsGoals + " goal(s)" }
    ];
    el("overviewCards").innerHTML = stats.map((s, i) =>
      `<div class="stat anim-card" style="--anim-delay:${ANIM_DELAYS[i]}ms"><div class="label">${s.label}</div>` +
      `<div class="value" data-countup="${s.target}" data-decimals="${s.decimals}" data-suffix="${esc(s.suffix)}">0${s.decimals ? ".00" : ""}${esc(s.suffix)}</div>` +
      `<div class="sub">${s.sub}</div></div>`).join("");
    gxAnimateIn(el("overviewCards"));
    el("ovChart").innerHTML = chartHtml([
      { label: "Income", value: o.income, cls: "" },
      { label: "Expense", value: o.expense, cls: "expense" },
      { label: "Savings saved", value: o.savingsSaved, cls: "savings" }],
      Math.max(o.income, o.expense, o.savingsSaved, 1));
    // Dashboard graphics: donut, task bars and trend from the same
    // real data (tasks + transactions fetched once here).
    const ovTasks = await api("/api/tasks");
    const ovTxs = await api("/api/transactions");
    const ovIncome = ovTxs.filter(t => t.type === "income").reduce((s, t) => s + t.amount, 0);
    const ovExpense = ovTxs.filter(t => t.type === "expense").reduce((s, t) => s + t.amount, 0);
    el("ovDonut").innerHTML = gxDonutHtml(ovIncome, ovExpense);
    el("ovTasks").innerHTML = gxTaskBarsHtml(ovTasks);
    el("ovTrend").innerHTML = gxTrendHtml(ovTxs);
    gxAnimateIn(el("ovDonut")); gxAnimateIn(el("ovTasks")); gxAnimateIn(el("ovTrend"));
    const decisions = await api("/api/decisions");
    el("overviewDecisions").innerHTML = decisions.length ? "<table><tr><th>ID</th><th>Date</th><th>Type</th><th>Priority</th><th>Title</th><th></th></tr>" +
      decisions.slice(-20).reverse().map(d =>
        `<tr><td>${esc(d.id)}</td><td>${esc(d.date)}</td><td>${esc(d.type)}</td><td>${d.priority}</td><td>${esc(d.title)}</td>` +
        `<td><button class="btn btn-danger" onclick="deleteDecision(${d.id})">Delete</button></td></tr>`).join("") + "</table>"
      : "<div class='empty'>No decisions yet. Create one from Daily Decision, Tasks, or Priority.</div>";
    staggerRows(el("overviewDecisions"), "tr");
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
  stopTyping(replyBox);
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
  const btnLabel = btn.querySelector(".ai-btn-label");
  const oldText = btnLabel.textContent;
  btn.classList.add("ai-busy");
  btnLabel.textContent = "Thinking…";
  replyBox.innerHTML = aiThinkingHtml();
  try {
    const r = await api("/api/ai/daily-decision", { method: "POST", body: JSON.stringify(body) });
    typeInto(replyBox, r.reply || "");
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
    btn.classList.remove("ai-busy");
    btnLabel.textContent = oldText;
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
  stopTyping(replyBox);
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
  const btnLabel = btn.querySelector(".ai-btn-label");
  const oldText = btnLabel.textContent;
  btn.classList.add("ai-busy");
  btnLabel.textContent = "Thinking…";
  replyBox.innerHTML = aiThinkingHtml();
  try {
    const r = await api("/api/ai/task-analyzer", { method: "POST", body: JSON.stringify(body) });
    typeInto(replyBox, r.reply || "");
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
    btn.classList.remove("ai-busy");
    btnLabel.textContent = oldText;
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
  stopTyping(replyBox);
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
  const btnLabel = btn.querySelector(".ai-btn-label");
  const oldText = btnLabel.textContent;
  btn.classList.add("ai-busy");
  btnLabel.textContent = "Thinking…";
  replyBox.innerHTML = aiThinkingHtml();
  try {
    const r = await api("/api/ai/study-planner", { method: "POST", body: JSON.stringify(body) });
    typeInto(replyBox, r.reply || "");
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
    btn.classList.remove("ai-busy");
    btnLabel.textContent = oldText;
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
  stopTyping(replyBox);
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
  const btnLabel = btn.querySelector(".ai-btn-label");
  const oldText = btnLabel.textContent;
  btn.classList.add("ai-busy");
  btnLabel.textContent = "Thinking…";
  replyBox.innerHTML = aiThinkingHtml();
  try {
    const r = await api("/api/ai/problem-solver", { method: "POST", body: JSON.stringify(body) });
    typeInto(replyBox, r.reply || "");
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
    btn.classList.remove("ai-busy");
    btnLabel.textContent = oldText;
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
  stopTyping(replyBox);
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
  const btnLabel = btn.querySelector(".ai-btn-label");
  const oldText = btnLabel.textContent;
  btn.classList.add("ai-busy");
  btnLabel.textContent = "Thinking…";
  replyBox.innerHTML = aiThinkingHtml();
  try {
    const r = await api("/api/ai/budget", { method: "POST", body: JSON.stringify(body) });
    typeInto(replyBox, r.reply || "");
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
    btn.classList.remove("ai-busy");
    btnLabel.textContent = oldText;
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
  stopTyping(replyBox);
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
  const btnLabel = btn.querySelector(".ai-btn-label");
  const oldText = btnLabel.textContent;
  btn.classList.add("ai-busy");
  btnLabel.textContent = "Thinking…";
  replyBox.innerHTML = aiThinkingHtml();
  try {
    const r = await api("/api/ai/habit", { method: "POST", body: JSON.stringify(body) });
    typeInto(replyBox, r.reply || "");
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
    btn.classList.remove("ai-busy");
    btnLabel.textContent = oldText;
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
  list.innerHTML = skeletonHtml();
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
  staggerRows(list, ".ai-history-entry");
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
// The task the user has just marked done: its status cell gets the
// popping checkmark on the next render only (loadTasks clears it
// after rendering, so later renders keep the plain mark).
let justCompletedTask = null;
function taskStatusCell(t) {
  if (t.status !== "Completed") return esc(t.status);
  // Task ids are STRINGS in the API (cpp_server.cpp: struct Task
  // has `string id`), but the inline onclick passes a number
  // literal — compare as strings or the pop never matches.
  const pop = (justCompletedTask !== null && String(t.id) === justCompletedTask) ? " done-pop" : "";
  return '<span class="done-mark' + pop + '">\u2713 Completed</span>';
}
async function loadTasks() {
  el("taskList").innerHTML = skeletonHtml();
  try {
    const tasks = await api("/api/tasks");
    el("taskList").innerHTML = tasks.length ? "<table><tr><th>Title</th><th>Score</th><th>Deadline</th><th>Status</th><th></th></tr>" +
      tasks.map(t => `<tr><td>${esc(t.title)}</td><td>${t.score}</td><td>${esc(t.deadline || "Not set")}</td><td>${taskStatusCell(t)}</td><td>` +
        `<button class="btn btn-primary" onclick="setTaskStatus(${t.id},'Completed')">Complete</button>` +
        `<button class="btn btn-danger" onclick="deleteTask(${t.id})">Delete</button></td></tr>`).join("") + "</table>"
      : "<div class='empty'>No tasks yet. Add your first task above.</div>";
    staggerRows(el("taskList"), "tr");
    justCompletedTask = null;
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
async function setTaskStatus(id, status) {
  try {
    await api("/api/tasks/" + id, { method: "PATCH", body: JSON.stringify({ status }) });
    if (status === "Completed") justCompletedTask = String(id);
    loadTasks(); loadStatusList();
  }
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
// Expense-by-category bars (Budget section): from the user's real
// transactions, re-rendered whenever the section opens.
async function loadBudgetCategories() {
  try {
    const txs = await api("/api/transactions");
    el("budCats").innerHTML = gxCategoryBarsHtml(txs);
    gxAnimateIn(el("budCats"));
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
el("budBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/budget?income=" + encodeURIComponent(el("budIncome").value) +
      "&expenses=" + encodeURIComponent(el("budExpenses").value));
    showMsg("budMsg", "Remaining balance: " + r.remaining.toFixed(2) + " | Decision: " + r.decision, true);
  } catch (e) { showMsg("budMsg", e.message, false); }
});

// -- finance --------------------------------------------------------
// Last loaded transactions/goals, so Edit can pre-fill the form.
let txCache = [];
let goalCache = [];
let editingTxId = null;
let editingGoalId = null;
async function loadTransactions() {
  try {
    const txs = await api("/api/transactions");
    txCache = txs;
    const income = txs.filter(t => t.type === "income").reduce((s, t) => s + t.amount, 0);
    const expense = txs.filter(t => t.type === "expense").reduce((s, t) => s + t.amount, 0);
    el("txList").innerHTML = "<p>Balance: <b>" + (income - expense).toFixed(2) + "</b> (income " + income.toFixed(2) + ", expense " + expense.toFixed(2) + ")</p>" +
      (txs.length ? "<table><tr><th>Date</th><th>Type</th><th>Category</th><th>Amount</th><th>Note</th><th></th></tr>" +
        txs.map(t => `<tr><td>${esc(t.date)}</td><td>${esc(t.type)}</td><td>${esc(t.category)}</td><td>${t.amount}</td><td>${esc(t.note)}</td><td><button class="btn btn-secondary" onclick="editTransaction(${t.id})">Edit</button> <button class="btn btn-danger" onclick="deleteTransaction(${t.id})">Delete</button></td></tr>`).join("") + "</table>"
        : "<div class='empty'>No transactions yet.</div>");
    staggerRows(el("txList"), "tr");
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
async function deleteTransaction(id) {
  if (!window.confirm("Delete this transaction?")) return;
  try { await api("/api/transactions/" + id, { method: "DELETE" }); loadTransactions(); loadOverview(); }
  catch (e) { showMsg("globalMsg", e.message, false); }
}
window.deleteTransaction = deleteTransaction;
function editTransaction(id) {
  const t = txCache.find(x => x.id === id);
  if (!t) return;
  el("txDate").value = t.date; el("txType").value = t.type;
  el("txCategory").value = t.category; el("txAmount").value = t.amount;
  el("txNote").value = t.note;
  editingTxId = id;
  el("txBtn").textContent = "Save changes";
  el("txCancelBtn").style.display = "";
  el("txMsg").textContent = "";
  el("txDate").focus();
}
window.editTransaction = editTransaction;
function cancelTxEdit() {
  editingTxId = null;
  el("txDate").value = ""; el("txType").value = "income";
  el("txCategory").value = ""; el("txAmount").value = ""; el("txNote").value = "";
  el("txBtn").textContent = "Add transaction";
  el("txCancelBtn").style.display = "none";
  el("txMsg").textContent = "";
}
el("txCancelBtn").addEventListener("click", cancelTxEdit);
el("txBtn").addEventListener("click", async () => {
  try {
    const body = { date: el("txDate").value, type: el("txType").value,
      category: el("txCategory").value.trim(), amount: +el("txAmount").value,
      note: el("txNote").value };
    if (editingTxId !== null) {
      await api("/api/transactions/" + editingTxId, { method: "PATCH", body: JSON.stringify(body) });
      cancelTxEdit();
      showMsg("txMsg", "Transaction updated.", true);
      loadTransactions(); loadOverview();
    } else {
      await api("/api/transactions", { method: "POST", body: JSON.stringify(body) });
      showMsg("txMsg", "Transaction saved.", true); loadTransactions();
    }
  } catch (e) { showMsg("txMsg", e.message, false); }
});

// -- savings --------------------------------------------------------
async function loadSavings() {
  try {
    const goals = await api("/api/savings");
    goalCache = goals;
    el("svList").innerHTML = goals.length ? "<table><tr><th>Goal</th><th>Target</th><th>Saved</th><th>Remaining</th><th></th></tr>" +
      goals.map(g => `<tr><td>${esc(g.name)}</td><td>${g.target}</td><td>${g.saved}</td><td>${(g.target - g.saved).toFixed(2)}</td><td><button class="btn btn-secondary" onclick="editGoal(${g.id})">Edit</button></td></tr>`).join("") + "</table>"
      : "<div class='empty'>No savings goals yet.</div>";
    staggerRows(el("svList"), "tr");
    el("svRings").innerHTML = gxSavingsRingsHtml(goals);
    gxAnimateIn(el("svRings"));
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
function editGoal(id) {
  const g = goalCache.find(x => x.id === id);
  if (!g) return;
  // The name is the goal's unique key and is never edited.
  el("svName").value = g.name; el("svName").disabled = true;
  el("svTarget").value = g.target;
  el("svSaved").value = g.saved;
  el("svSavedLabel").style.display = "";
  editingGoalId = id;
  el("svBtn").textContent = "Save changes";
  el("svCancelBtn").style.display = "";
  el("svMsg").textContent = "";
  el("svTarget").focus();
}
window.editGoal = editGoal;
function cancelGoalEdit() {
  editingGoalId = null;
  el("svName").value = ""; el("svName").disabled = false;
  el("svTarget").value = ""; el("svSaved").value = "";
  el("svSavedLabel").style.display = "none";
  el("svBtn").textContent = "Add goal";
  el("svCancelBtn").style.display = "none";
  el("svMsg").textContent = "";
}
el("svCancelBtn").addEventListener("click", cancelGoalEdit);
el("svBtn").addEventListener("click", async () => {
  try {
    if (editingGoalId !== null) {
      await api("/api/savings/" + editingGoalId, { method: "PATCH", body: JSON.stringify({
        target: +el("svTarget").value, saved: +el("svSaved").value }) });
      cancelGoalEdit();
      showMsg("svMsg", "Goal updated.", true);
      loadSavings(); loadOverview();
    } else {
      await api("/api/savings", { method: "POST", body: JSON.stringify({
        name: el("svName").value.trim(), target: +el("svTarget").value }) });
      showMsg("svMsg", "Goal added.", true); loadSavings();
    }
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
// Previous habit-ring % (for the count-up start and the
// heartbeat: the ring only celebrates when the % has risen).
let lastHbPct = 0;
// The habit the user has just marked done: its row gets the
// popping checkmark on the next render only (loadHabits clears
// it after rendering).
let justRecordedHabit = null;
async function loadHabits() {
  try {
    const habits = await api("/api/habits");
    el("hbList").innerHTML = habits.length ? "<table><tr><th>Habit</th><th>Recorded dates</th></tr>" +
      habits.map(h => {
        const pop = (justRecordedHabit && justRecordedHabit === h.habit)
          ? ' <span class="done-mark done-pop">\u2713</span>' : "";
        return `<tr><td>${esc(h.habit)}${pop}</td><td>${esc(h.dates.join(", "))}</td></tr>`;
      }).join("") + "</table>"
      : "<div class='empty'>No habit records yet.</div>";
    staggerRows(el("hbList"), "tr");
    justRecordedHabit = null;
    // Habit ring (Panze style): overall completion over the last 30
    // days, from the SAME data as the table above — distinct dates
    // with at least one completion across all of this user's habits,
    // in the window [today-29, today]. Same window definition as
    // the server's AI habit 30-day rate (cpp_server.cpp
    // habitAiStats), aggregated over all habits instead of one. No
    // fake data: an empty log is 0%.
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const start = new Date(today); start.setDate(start.getDate() - 29);
    const active = new Set();
    habits.forEach(h => h.dates.forEach(d => {
      const dt = new Date(d + "T00:00:00");
      if (!isNaN(dt) && dt >= start && dt <= today) active.add(d);
    }));
    const pct = Math.round(active.size * 100 / 30);
    const fill = el("hbRingFill");
    if (fill) fill.style.strokeDashoffset = String(2 * Math.PI * 52 * (1 - pct / 100));
    // The % counts up from its previous value, and when it has
    // risen the ring gives one happy heartbeat.
    countUp(el("hbRingPct"), pct, 0, "%", lastHbPct);
    const ringWrap = fill ? fill.closest(".ring-wrap") : null;
    if (ringWrap && pct > lastHbPct && pct > 0) replayAnim(ringWrap, "animate__heartBeat", 900);
    lastHbPct = pct;
    el("hbRingCaption").textContent = habits.length
      ? active.size + " active day" + (active.size === 1 ? "" : "s") + " in the last 30 days"
      : "No habit records yet — mark a habit done to start your ring.";
    // Dashboard graphics: 7-day bars + 30-day heatmap from the same
    // active-day set. The streak uses the full log (allDates), not
    // the 30-day window, so a streak longer than 30 days is honest.
    const allDates = new Set();
    habits.forEach(h => h.dates.forEach(d => allDates.add(d)));
    el("hbWeek").innerHTML = gxWeekHtml(active, allDates);
    el("hbHeat").innerHTML = gxHeatHtml(active);
    gxAnimateIn(el("hbWeek"));
  } catch (e) { showMsg("globalMsg", e.message, false); }
}
el("hbBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/habits", { method: "POST", body: JSON.stringify({
      habit: el("hbName").value.trim(), date: el("hbDate").value }) });
    justRecordedHabit = el("hbName").value.trim();
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
  el("histList").innerHTML = skeletonHtml();
  try {
    const q = new URLSearchParams({ search: el("histSearch").value.trim(), type: el("histType").value });
    let ds = await api("/api/decisions?" + q.toString());
    if (el("histSort").value === "priority") ds = ds.slice().sort((a, b) => b.priority - a.priority);
    else ds = ds.slice().reverse();
    el("histList").innerHTML = ds.length ? "<table><tr><th>ID</th><th>Date</th><th>Type</th><th>Priority</th><th>Title</th></tr>" +
      ds.map(d => `<tr><td>${esc(d.id)}</td><td>${esc(d.date)}</td><td>${esc(d.type)}</td><td>${d.priority}</td><td>${esc(d.title)}</td></tr>`).join("") + "</table>"
      : "<div class='empty'>No matching decisions. Try a different keyword, or create a decision first.</div>";
    staggerRows(el("histList"), "tr");
    showMsg("histMsg", ds.length + " matching decision(s).", true);
  } catch (e) { showMsg("histMsg", e.message, false); }
}
el("histBtn").addEventListener("click", loadHistory);

// Task Status: same tasks.txt, status dropdown mirrors task_status.cpp.
async function loadStatusList() {
  const box = el("statusList"); if (!box) return;
  box.innerHTML = skeletonHtml();
  try {
    const tasks = await api("/api/tasks");
    box.innerHTML = tasks.length ? "<table><tr><th>Title</th><th>Score</th><th>Deadline</th><th>Status</th></tr>" +
      tasks.map(t => `<tr><td>${esc(t.title)}</td><td>${t.score}</td><td>${esc(t.deadline || "Not set")}</td><td><select onchange="setTaskStatus(${t.id}, this.value)">` +
        ["Pending", "In Progress", "Completed"].map(s => `<option value="${s}"${s === t.status ? " selected" : ""}>${s}</option>`).join("") + "</select></td></tr>").join("") + "</table>"
      : "<div class='empty'>No tasks yet. Add a task in Task Management first.</div>";
    staggerRows(box, "tr");
  } catch (e) { showMsg("globalMsg", e.message, false); }
}

// Deadline Alerts: mirrors deadline_alert.cpp.
async function loadDeadlines() {
  el("dlList").innerHTML = skeletonHtml();
  try {
    const today = el("dlDate").value;
    const ds = await api("/api/deadlines" + (today ? "?today=" + encodeURIComponent(today) : ""));
    const badge = a => a === "OVERDUE" ? "badge-danger" : a === "DUE TODAY" ? "badge-warn" : a === "UPCOMING" ? "badge" : "badge-warn";
    el("dlList").innerHTML = ds.length ? "<table><tr><th>Title</th><th>Deadline</th><th>Status</th><th>Alert</th></tr>" +
      ds.map(d => `<tr><td>${esc(d.title)}</td><td>${esc(d.deadline || "Not set")}</td><td>${esc(d.status)}</td><td><span class="badge ${badge(d.alert)}">${esc(d.alert)}</span></td></tr>`).join("") + "</table>"
      : "<div class='empty'>No open tasks with deadlines. Completed tasks are skipped, as in the C++ module.</div>";
    staggerRows(el("dlList"), "tr");
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

// Study Planner: saved plans with per-day progress, Exam Countdown
// plans, and Smart Revision (+1/+3/+7 days). The old calculate-only
// POST /api/study-planner still exists server-side (the console
// module mirrors it), but the dashboard now uses /api/study-plans.
const SP_MAX_TOPICS = 10;
function spTopicCount() { return document.querySelectorAll("#spTopics .ai-opt-row").length; }
function spSyncAddTopicBtn() {
  el("spAddTopic").disabled = spTopicCount() >= SP_MAX_TOPICS;
}
function addSpTopicRow() {
  if (spTopicCount() >= SP_MAX_TOPICS) return;
  const div = document.createElement("div");
  div.className = "ai-opt-row";
  div.innerHTML = `<input placeholder="Topic" class="ai-opt-input"><button type="button" class="btn btn-secondary ai-opt-remove">Remove</button>`;
  div.querySelector(".ai-opt-remove").addEventListener("click", () => { div.remove(); spSyncAddTopicBtn(); });
  el("spTopics").appendChild(div);
  spSyncAddTopicBtn();
}
addSpTopicRow();
el("spAddTopic").addEventListener("click", addSpTopicRow);

async function loadStudyPlans() {
  try {
    const plans = await api("/api/study-plans");
    if (!plans.length) {
      el("spList").innerHTML = "<div class='empty'>No study plans yet. Create one above.</div>";
      return;
    }
    // Fetch each plan's full schedule (plans are few; the list
    // endpoint returns summaries without day rows).
    const full = [];
    for (const p of plans) full.push(await api("/api/study-plans/" + p.id));
    el("spList").innerHTML = full.map(p => {
      const first = p.schedule.length ? p.schedule[0].date : p.startDate;
      const last = p.schedule.length ? p.schedule[p.schedule.length - 1].date : p.startDate;
      const exam = p.examDate ? `<p><b>Exam:</b> ${esc(p.examDate)} (countdown plan)</p>` : "";
      const rows = p.schedule.map(d => {
        const label = d.kind === "revision" ? "Revision" : ("Day " + d.dayIndex);
        return `<tr><td><input type="checkbox" ${d.done ? "checked" : ""} onchange="tickStudyDay(${p.id}, ${d.id}, this.checked)"></td><td>${esc(d.date)}</td><td>${label}</td><td>${esc(d.topic)}</td><td>${d.hours} hour(s)</td></tr>`;
      }).join("");
      return `<div class="sp-plan"><h3>${esc(p.subject)}</h3>` +
        `<p>${esc(first)} &ndash; ${esc(last)} &middot; ${p.hoursPerDay} hour(s)/day &middot; Progress: ${p.doneDays}/${p.totalDays} (${p.progressPct}%)</p>` +
        gxStudyProgressHtml(p) +
        exam +
        `<table><tr><th>Done</th><th>Date</th><th>Day</th><th>Topic</th><th>Hours</th></tr>${rows}</table>` +
        `<div class="actions"><button class="btn btn-danger" onclick="deleteStudyPlan(${p.id})">Delete plan</button></div></div>`;
    }).join("");
    gxAnimateIn(el("spList"));
  } catch (e) { showMsg("spMsg", e.message, false); }
}
async function tickStudyDay(planId, dayId, done) {
  try {
    await api("/api/study-plans/" + planId + "/days/" + dayId, { method: "PATCH", body: JSON.stringify({ done }) });
    loadStudyPlans();
  } catch (e) { showMsg("spMsg", e.message, false); loadStudyPlans(); }
}
window.tickStudyDay = tickStudyDay;
async function deleteStudyPlan(id) {
  if (!window.confirm("Delete this study plan and all its days?")) return;
  try { await api("/api/study-plans/" + id, { method: "DELETE" }); loadStudyPlans(); }
  catch (e) { showMsg("spMsg", e.message, false); }
}
window.deleteStudyPlan = deleteStudyPlan;
el("spBtn").addEventListener("click", async () => {
  try {
    // Client-side validation mirrors the server, so the user gets
    // an immediate error instead of a round trip that would fail
    // anyway. The exam date itself is NOT checked here: the server
    // clock decides what "future" means (near midnight the user's
    // local date and the server date can differ by a day).
    const subject = aiDailySanitize(el("spSubject").value.trim());
    const hours = el("spHours").value === "" ? NaN : Number(el("spHours").value);
    if (!subject || [...subject].length > 200 || !Number.isInteger(hours) || hours < 1 || hours > 24) {
      showMsg("spMsg", "A plan needs a subject (up to 200 characters) and hours 1-24.", false);
      return;
    }
    const examDate = el("spExamDate").value;
    const body = { subject, hours };
    if (examDate) {
      const topics = [];
      let topicTooLong = false;
      document.querySelectorAll("#spTopics .ai-opt-input").forEach(inp => {
        const v = aiDailySanitize(inp.value.trim());
        if (v) { if ([...v].length > 100) topicTooLong = true; else if (!topics.includes(v)) topics.push(v); }
      });
      if (topicTooLong) { showMsg("spMsg", "Each topic must be 1-100 characters.", false); return; }
      if (!topics.length) { showMsg("spMsg", "A countdown plan needs 1-10 topics.", false); return; }
      body.examDate = examDate;
      body.topics = topics;
    } else {
      const days = el("spDays").value === "" ? NaN : Number(el("spDays").value);
      if (!Number.isInteger(days) || days < 1 || days > 365) {
        showMsg("spMsg", "Days must be 1-365.", false);
        return;
      }
      body.days = days;
    }
    const r = await api("/api/study-plans", { method: "POST", body: JSON.stringify(body) });
    showMsg("spMsg", "Plan saved: " + r.subject + " (" + r.totalDays + " days, " + (r.days * r.hoursPerDay) + " total hours).", true);
    el("spSubject").value = ""; el("spDays").value = ""; el("spHours").value = ""; el("spExamDate").value = "";
    document.querySelectorAll("#spTopics .ai-opt-input").forEach(inp => { inp.value = ""; });
    loadStudyPlans();
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

// -- dashboard graphics (real data only, pure SVG/CSS, no library) --
// Every gx* helper renders from data the section loaders already
// fetched — never sample or hard-coded values. Empty data renders
// an .empty message, never a broken chart (a zero-income budget is
// 0%, a missing target is 0%). Animated elements render at 0 and
// animate to their real value on the next frame: gxAnimateIn
// applies the target values stored in data-* attributes, and the
// CSS transitions (0.5s) do the animation. Tooltips are pure CSS
// ([data-tip]) on HTML elements and native <title> inside SVG.
function gxDateKey(d) {
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}
function gxAnimateIn(root) {
  if (!root) return;
  requestAnimationFrame(() => {
    root.querySelectorAll(".gx-fill[data-w]").forEach(b => { b.style.width = b.dataset.w + "%"; });
    root.querySelectorAll(".gx-progress > div[data-w]").forEach(b => { b.style.width = b.dataset.w + "%"; });
    root.querySelectorAll(".gx-week .b[data-h]").forEach(b => { b.style.height = b.dataset.h + "%"; });
    root.querySelectorAll(".gx-donut-spent[data-len]").forEach(c => { c.setAttribute("stroke-dasharray", c.dataset.len + " 339.29"); });
    root.querySelectorAll(".gx-donut-left[data-len]").forEach(c => {
      c.setAttribute("stroke-dasharray", c.dataset.len + " 339.29");
      c.setAttribute("stroke-dashoffset", c.dataset.off);
    });
    root.querySelectorAll(".ring-fill[data-off]").forEach(c => { c.style.strokeDashoffset = c.dataset.off; });
    // Count-up numbers (Overview stats, donut centre, KPI tiles,
    // savings ring centres) start from 0 on the same frame.
    runCountUps(root);
  });
}
// Consecutive-day streak across ALL of the user's habits, from the
// full log (not the 30-day window): walk back from today, or from
// yesterday when today has no completion yet.
function gxStreak(allDates) {
  const d = new Date(); d.setHours(0, 0, 0, 0);
  if (!allDates.has(gxDateKey(d))) d.setDate(d.getDate() - 1);
  let s = 0;
  while (allDates.has(gxDateKey(d))) { s++; d.setDate(d.getDate() - 1); }
  return s;
}
// Budget donut (Overview): spent vs remaining of total income.
// r=54, circumference 339.29. Overspend fills the whole ring pink
// and the negative remaining shows in red.
function gxDonutHtml(income, expense) {
  if (income <= 0 && expense <= 0) return "<div class='empty'>No transactions yet. Add one from Income / Expense.</div>";
  const C = 2 * Math.PI * 54;
  const remaining = income - expense;
  const spentFrac = income > 0 ? Math.min(expense / income, 1) : 1;
  const spentLen = (C * spentFrac).toFixed(2);
  const leftLen = (C - C * spentFrac).toFixed(2);
  const spentPct = income > 0 ? Math.min(Math.round(expense / income * 100), 100) : 100;
  const leftPct = Math.max(0, 100 - spentPct);
  const neg = remaining < 0 ? " style=\"fill:var(--danger)\"" : "";
  return `<div class="gx-donut-row gx-fade"><svg class="gx-donut" width="140" height="140" viewBox="0 0 140 140" role="img" aria-label="Budget donut: spent ${spentPct}% of income"><g transform="rotate(-90 70 70)"><circle class="gx-donut-track" cx="70" cy="70" r="54" /><circle class="gx-donut-spent" cx="70" cy="70" r="54" stroke-dasharray="0 339.29" data-len="${spentLen}"><title>Spent: ${expense.toFixed(2)} (${spentPct}%)</title></circle><circle class="gx-donut-left" cx="70" cy="70" r="54" stroke-dasharray="0 339.29" data-len="${leftLen}" data-off="${(-C * spentFrac).toFixed(2)}"><title>Remaining: ${remaining.toFixed(2)} (${leftPct}%)</title></circle></g><text x="70" y="66" text-anchor="middle" font-size="18" class="gx-donut-center"${neg} data-countup="${remaining}" data-decimals="2">0.00</text><text x="70" y="86" text-anchor="middle" font-size="12" class="gx-donut-sub">remaining</text></svg><div><div class="gx-big">${income.toFixed(2)}</div><div class="muted">total income</div><ul class="gx-legend"><li data-tip="Spent: ${expense.toFixed(2)}"><span class="gx-dot spent"></span>Spent: ${expense.toFixed(2)} (${spentPct}%)</li><li data-tip="Remaining: ${remaining.toFixed(2)}"><span class="gx-dot left"></span>Remaining: ${remaining.toFixed(2)} (${leftPct}%)</li></ul></div></div>`;
}
// Task status bars (Overview): done vs pending, plus KPI tiles for
// the top-scoring task and the nearest open deadline.
function gxTaskBarsHtml(tasks) {
  if (!tasks.length) return "<div class='empty'>No tasks yet. Add your first task from Task Management.</div>";
  const done = tasks.filter(t => t.status === "Completed").length;
  const pending = tasks.length - done;
  const donePct = Math.round(done / tasks.length * 100);
  const pendPct = 100 - donePct;
  let top = null;
  tasks.forEach(t => { if (!top || t.score > top.score) top = t; });
  const dated = tasks.filter(t => t.deadline && t.status !== "Completed").sort((a, b) => a.deadline.localeCompare(b.deadline));
  const next = dated.length ? dated[0] : null;
  return `<div class="gx-fade"><div class="gx-bar-row" data-tip="Completed: ${done} of ${tasks.length} tasks"><span class="lbl">Done</span><span class="gx-track"><span class="gx-fill green" data-w="${donePct}" style="width:0%"></span></span><span class="val">${done} / ${tasks.length}</span></div><div class="gx-bar-row" data-tip="Pending: ${pending} of ${tasks.length} tasks"><span class="lbl">Pending</span><span class="gx-track"><span class="gx-fill amber" data-w="${pendPct}" style="width:0%"></span></span><span class="val">${pending} / ${tasks.length}</span></div><div class="gx-kpi-row"><div class="gx-kpi"><div class="n" data-countup="${top.score}">0</div><div class="l">Top score — ${esc(top.title)}</div></div><div class="gx-kpi"><div class="n">${next ? esc(next.deadline) : "—"}</div><div class="l">${next ? "Nearest deadline — " + esc(next.title) : "No upcoming deadline"}</div></div></div></div>`;
}
// Monthly trend (Overview): income vs expense lines over the last
// 6 calendar months, months with no data at 0. Pure SVG, viewBox
// 0 0 600 240, plot area x 48..576, y 16..196.
function gxTrendHtml(txs) {
  const now = new Date();
  const months = [];
  for (let i = 5; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push({ key: d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0"),
      label: d.toLocaleString("en-US", { month: "short" }) + " " + String(d.getFullYear()).slice(2) });
  }
  const sums = {};
  months.forEach(m => { sums[m.key] = { income: 0, expense: 0 }; });
  let any = false;
  txs.forEach(t => {
    const k = (t.date || "").slice(0, 7);
    if (sums[k]) { any = true; if (t.type === "income") sums[k].income += t.amount; else sums[k].expense += t.amount; }
  });
  if (!any) return "<div class='empty'>No transactions in the last 6 months.</div>";
  const max = Math.max(1, ...months.map(m => Math.max(sums[m.key].income, sums[m.key].expense)));
  const x = i => 48 + i * 105.6;
  const y = v => 196 - (v / max) * 180;
  const pts = months.map((m, i) => ({ xi: x(i), yi: y(sums[m.key].income), ye: y(sums[m.key].expense) }));
  const line = key => pts.map(p => p.xi + "," + p[key]).join(" ");
  const area = key => `M48,196 L${line(key)} L576,196 Z`;
  let grid = "";
  [0, 0.25, 0.5, 0.75, 1].forEach(f => {
    grid += `<line class="gridline" x1="48" y1="${y(max * f)}" x2="576" y2="${y(max * f)}" /><text x="44" y="${y(max * f) + 4}" text-anchor="end">${(max * f).toFixed(0)}</text>`;
  });
  let labels = "";
  months.forEach((m, i) => { labels += `<text x="${x(i)}" y="216" text-anchor="middle">${esc(m.label)}</text>`; });
  let dots = "";
  months.forEach((m, i) => {
    dots += `<circle class="pt-inc" cx="${x(i)}" cy="${y(sums[m.key].income)}" r="4"><title>${esc(m.label)}: income ${sums[m.key].income.toFixed(2)}</title></circle>`;
    dots += `<circle class="pt-exp" cx="${x(i)}" cy="${y(sums[m.key].expense)}" r="4"><title>${esc(m.label)}: expense ${sums[m.key].expense.toFixed(2)}</title></circle>`;
  });
  return `<div class="gx-fade"><svg class="gx-trend" viewBox="0 0 600 240" role="img" aria-label="Monthly income vs expense trend, last 6 months">${grid}${labels}<path class="area-inc" d="${area("yi")}" /><path class="area-exp" d="${area("ye")}" /><polyline class="line-inc" points="${line("yi")}" /><polyline class="line-exp" points="${line("ye")}" />${dots}</svg><ul class="gx-legend"><li><span class="gx-dot inc"></span>Income</li><li><span class="gx-dot exp"></span>Expense</li></ul></div>`;
}
// Expense by category (Budget): one horizontal bar per category,
// sorted by amount, % of total spending.
function gxCategoryBarsHtml(txs) {
  const byCat = {};
  let total = 0;
  txs.forEach(t => {
    if (t.type !== "expense") return;
    total += t.amount;
    byCat[t.category] = (byCat[t.category] || 0) + t.amount;
  });
  if (total <= 0) return "<div class='empty'>No expenses yet. Add one from Income / Expense.</div>";
  const cats = Object.keys(byCat).sort((a, b) => byCat[b] - byCat[a]);
  return `<div class="gx-fade">` + cats.map(c => {
    const pct = Math.round(byCat[c] / total * 100);
    return `<div class="gx-bar-row" data-tip="${esc(c)}: ${byCat[c].toFixed(2)} (${pct}% of spending)"><span class="lbl">${esc(c)}</span><span class="gx-track"><span class="gx-fill" data-w="${pct}" style="width:0%"></span></span><span class="val">${byCat[c].toFixed(2)} · ${pct}%</span></div>`;
  }).join("") + `</div>`;
}
// 7-day habit bars (Habit Tracker): one bar per day in the last 7
// days, from the same active-day set as the 30-day ring.
function gxWeekHtml(active, allDates) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today); d.setDate(d.getDate() - i);
    const key = gxDateKey(d);
    days.push({ key, label: d.toLocaleString("en-US", { weekday: "short" }), done: active.has(key) });
  }
  const doneCount = days.filter(d => d.done).length;
  const cols = days.map(d => `<div class="col"><div class="b${d.done ? "" : " off"}" data-h="${d.done ? 78 : 18}" style="height:0%" data-tip="${d.key}: ${d.done ? "done" : "no record"}"></div><span class="d">${d.label}</span></div>`).join("");
  return `<div class="gx-fade"><div class="gx-week">${cols}</div><p style="margin:12px 0 0"><span class="gx-pill">${doneCount} / 7 days</span> <span class="muted">· current streak: ${gxStreak(allDates)} day(s)</span></p></div>`;
}
// 30-day heatmap (Habit Tracker): GitHub-style grid, 7 per row,
// oldest first, from the same active-day set as the ring.
function gxHeatHtml(active) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  let cells = "";
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today); d.setDate(d.getDate() - i);
    const key = gxDateKey(d);
    cells += `<div class="gx-heat-cell${active.has(key) ? " on" : ""}${i === 0 ? " today" : ""}" data-tip="${key}: ${active.has(key) ? "done" : "no record"}"></div>`;
  }
  return `<div class="gx-heat gx-fade">${cells}</div><p class="muted" style="margin:10px 0 0">${active.size} active day${active.size === 1 ? "" : "s"} in the last 30 days${active.size ? "" : " — mark a habit done to start"}.</p>`;
}
// Per-goal savings rings (Savings): saved/target %, same ring
// pattern as the habit ring (r=40, circumference 251.33). The
// centre shows the true % (over 100% when saved exceeds target);
// the ring fill itself caps at 100%.
function gxSavingsRingsHtml(goals) {
  if (!goals.length) return "<div class='empty'>No savings goals yet.</div>";
  return `<div class="gx-rings gx-fade">` + goals.map(g => {
    const pct = g.target > 0 ? Math.round(g.saved / g.target * 100) : 0;
    const off = (2 * Math.PI * 40 * (1 - Math.min(pct, 100) / 100)).toFixed(2);
    // A goal at 100%+ celebrates: the ring pulses twice (CSS
    // .goal-complete) and a "Goal reached!" badge appears.
    const complete = pct >= 100;
    return `<div class="gx-ring-item${complete ? " goal-complete" : ""}" data-goal="${esc(g.name)}" data-pct="${pct}"><div class="gx-ring-sm"><svg viewBox="0 0 96 96" role="img" aria-label="Savings ring for ${esc(g.name)}: ${pct}%"><defs><linearGradient id="svGrad${g.id}" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" class="ring-stop-a" /><stop offset="100%" class="ring-stop-b" /></linearGradient></defs><circle class="ring-track" cx="48" cy="48" r="40" /><circle class="ring-fill" cx="48" cy="48" r="40" style="stroke: url(#svGrad${g.id})" data-off="${off}" /></svg><div class="ring-center"><span data-countup="${pct}" data-suffix="%">0%</span></div></div><div><div><b>${esc(g.name)}</b>${complete ? ' <span class="badge badge-ok">Goal reached!</span>' : ""}</div><div class="muted">${g.saved.toFixed(2)} / ${g.target.toFixed(2)} saved</div></div></div>`;
  }).join("") + `</div>`;
}
// Study plan progress bar + day timeline strip (Study Planner):
// one cell per schedule day — done (filled), revision (pink
// border), today (outline). Rendered inside loadStudyPlans.
function gxStudyProgressHtml(p) {
  const todayKey = gxDateKey(new Date());
  const cells = p.schedule.map(d => {
    const label = d.kind === "revision" ? "Revision" : ("Day " + d.dayIndex);
    const cls = "cell" + (d.done ? " done" : "") + (d.kind === "revision" ? " rev" : "") + (d.date === todayKey ? " today" : "");
    return `<div class="${cls}" data-tip="${esc(d.date)} · ${label} · ${esc(d.topic)} · ${d.done ? "done" : "not done"}"></div>`;
  }).join("");
  return `<div class="gx-progress"><div data-w="${p.progressPct}" style="width:0%"></div></div><div class="gx-timeline">${cells}</div>`;
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
