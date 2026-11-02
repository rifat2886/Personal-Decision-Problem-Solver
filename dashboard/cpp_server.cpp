// Personal Decision & Problem Solver — C++ dashboard API server.
//
// This is the C++ backend for dashboard/index.html. It replaces the
// Python bridge (dashboard/server.py, kept as a fallback) with a real
// C++ HTTP server, so the dashboard is served and answered by C++
// code, not by a Python process.
//
// Build (from the repository root):
//   Linux:   g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server dashboard/cpp_server.cpp
//   Windows (MinGW): x86_64-w64-mingw32-g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server.exe dashboard/cpp_server.cpp -lws2_32
//   Windows (MSVC):  cl /std:c++17 /EHsc dashboard\cpp_server.cpp ws2_32.lib
// Run (from the repository root, so the data files are the same ones
// the C++ console app reads):
//   ./cpp_server            # http://127.0.0.1:8000/
//   ./cpp_server --port 8001 --data-dir /path/to/data
//
// The API is intentionally identical to server.py (same paths, same
// JSON fields, same validation, same formulas), so dashboard/app.js
// works unchanged against either server. Only one server should run
// on a port at a time.
//
// Data files and formats (identical to the C++ console app):
//   users.txt         username password ROLE
//   decisions.txt     id|date|type|priority|title
//   transactions.txt  date|type|category|amount|note
//   savings_goals.txt name|target|saved
//   habit_log.txt     habit|date
//   tasks.txt         id|title|urgency|importance|deadline|status
//       (dashboard extension; the console task list is in-memory only)
//
// Concurrency: API requests are serialised by a server mutex, and
// decisions/savings/transactions/habits/tasks writes also take an
// flock on "<file>.lock" in the data directory. The console app uses
// the same lock files (see file_lock.h) for those operations, so a
// dashboard write and a console-app write to the same file cannot
// interleave and lose an update.
//
// Security, stated honestly:
// - Passwords stay in the C++ plain-text format (users.txt), because
//   changing it would break existing console users. This server
//   binds to 127.0.0.1 only and must NOT be exposed to the internet.
// - Sessions are in-memory random tokens (random_device plus a
//   counter), never passwords, never written to a file, and never
//   returned except at login.
// - Static serving is limited to index.html, style.css, app.js.
//   Data files (users.txt, etc.) are never served as static files.
// - Request bodies are capped at 1 MiB; oversized bodies are rejected.
// - No command execution, no SQL, no user input passed to a shell.

#ifdef _MSC_VER
#pragma comment(lib, "ws2_32")
#endif
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <random>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <vector>
#ifdef _WIN32
#include <process.h>
#include <winsock2.h>
#include <windows.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <csignal>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

using namespace std;

// ---------------------------------------------------------------- config
static string g_dataDir = ".";
static string g_staticDir = ".";
static mutex g_apiMutex;
static map<string, string> g_sessions;  // token -> username
static mutex g_sessionMutex;
static atomic<unsigned long long> g_tokenCounter{0};

static string joinPath(const string& dir, const string& name) {
    if (dir.empty() || dir.back() == '/') return dir + name;
    return dir + "/" + name;
}

// ---------------------------------------------------------------- helpers
static string sanitize(const string& v) {
    string out = v;
    for (char& c : out) if (c == '|' || c == '\n' || c == '\r') c = '/';
    return out;
}
static string trimStr(const string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}
static vector<string> splitPipe(const string& s) {
    vector<string> parts; string cur;
    for (char c : s) { if (c == '|') { parts.push_back(cur); cur.clear(); } else cur += c; }
    parts.push_back(cur); return parts;
}
static bool isLeap(int y) { return (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0); }
static bool validDate(const string& d) {
    if (d.size() != 10 || d[4] != '-' || d[7] != '-') return false;
    for (int i = 0; i < 10; i++) {
        if (i == 4 || i == 7) continue;
        if (d[i] < '0' || d[i] > '9') return false;
    }
    int y = stoi(d.substr(0, 4)), m = stoi(d.substr(5, 2)), day = stoi(d.substr(8, 2));
    if (m < 1 || m > 12 || day < 1) return false;
    static const int dim[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    int limit = dim[m - 1]; if (m == 2 && isLeap(y)) limit = 29;
    return day <= limit;
}
static bool validMonth(const string& m) {
    if (m.size() != 7 || m[4] != '-') return false;
    for (int i = 0; i < 7; i++) {
        if (i == 4) continue;
        if (m[i] < '0' || m[i] > '9') return false;
    }
    int mo = stoi(m.substr(5, 2)); return mo >= 1 && mo <= 12;
}
static string todayStr() {
    time_t t = time(nullptr); struct tm tmv;
#ifdef _WIN32
    localtime_s(&tmv, &t);
#else
    localtime_r(&t, &tmv);
#endif
    char buf[32]; snprintf(buf, sizeof(buf), "%04d-%02d-%02d", tmv.tm_year + 1900, tmv.tm_mon + 1, tmv.tm_mday);
    return buf;
}
static int daysFromCivilStr(const string& d) {
    int y = stoi(d.substr(0, 4)), m = stoi(d.substr(5, 2)), day = stoi(d.substr(8, 2));
    y -= m <= 2; int era = (y >= 0 ? y : y - 399) / 400;
    unsigned yoe = (unsigned)(y - era * 400), mp = (unsigned)((m + 9) % 12);
    unsigned doy = (153 * mp + 2) / 5 + day - 1, doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + (int)doe - 719468;
}
static string fmtNum(double v) {
    char buf[64]; snprintf(buf, sizeof(buf), "%.2f", v);
    // Keep integers readable: 5000.00 is fine and matches the Python server.
    return buf;
}
static string fmtNumRaw(double v) {
    // For amounts stored in files, keep the C++ default formatting simple.
    ostringstream os; os << v; return os.str();
}
static string jsonEscape(const string& s) {
    string out;
    for (unsigned char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) { char buf[8]; snprintf(buf, sizeof(buf), "\\u%04x", c); out += buf; }
                else out += (char)c;
        }
    }
    return out;
}
static string jsonStr(const string& s) { return "\"" + jsonEscape(s) + "\""; }

// Minimal JSON field extraction (frontend sends flat JSON objects).
static bool jsonStringField(const string& body, const string& key, string& out) {
    string pat = "\"" + key + "\"";
    size_t p = body.find(pat); if (p == string::npos) return false;
    p = body.find(':', p + pat.size()); if (p == string::npos) return false;
    p++; while (p < body.size() && (body[p] == ' ' || body[p] == '\t')) p++;
    if (p >= body.size() || body[p] != '"') return false;
    p++; string val;
    while (p < body.size() && body[p] != '"') {
        if (body[p] == '\\' && p + 1 < body.size()) { p++; val += body[p]; p++; }
        else { val += body[p]; p++; }
    }
    out = val; return true;
}
static bool jsonNumberField(const string& body, const string& key, double& out) {
    string pat = "\"" + key + "\"";
    size_t p = body.find(pat); if (p == string::npos) return false;
    p = body.find(':', p + pat.size()); if (p == string::npos) return false;
    p++; while (p < body.size() && (body[p] == ' ' || body[p] == '\t')) p++;
    size_t start = p;
    if (p < body.size() && (body[p] == '-' || body[p] == '+')) p++;
    while (p < body.size() && (isdigit((unsigned char)body[p]) || body[p] == '.')) p++;
    if (p == start) return false;
    try { out = stod(body.substr(start, p - start)); } catch (...) { return false; }
    return true;
}
static bool jsonIntField(const string& body, const string& key, long long& out) {
    double d; if (!jsonNumberField(body, key, d)) return false; out = (long long)d; return true;
}

// ---------------------------------------------------------------- file IO
static vector<string> readLines(const string& path) {
    vector<string> out; ifstream in(path); string line;
    while (getline(in, line)) if (!trimStr(line).empty()) out.push_back(line);
    return out;
}
static bool writeLines(const string& path, const vector<string>& lines) {
    ofstream out(path, ios::trunc); if (!out) return false;
    for (auto& l : lines) out << l << '\n';
    return (bool)out;
}
static bool appendLine(const string& path, const string& line) {
    ofstream out(path, ios::app); if (!out) return false; out << line << '\n'; return (bool)out;
}
static bool fileExists(const string& path) { struct stat st; return stat(path.c_str(), &st) == 0; }

// RAII lock on "<datafile>.lock" in the data directory.
// Same protocol as file_lock.h in the repository root: POSIX flock
// on Linux/macOS, LockFileEx on Windows.
struct FileLock {
#ifdef _WIN32
    HANDLE handle = INVALID_HANDLE_VALUE;
    explicit FileLock(const string& dataFile) {
        string lockPath = joinPath(g_dataDir, dataFile + ".lock");
        handle = CreateFileA(lockPath.c_str(), GENERIC_READ | GENERIC_WRITE,
                             0, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (handle != INVALID_HANDLE_VALUE) {
            OVERLAPPED ov = {};
            LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK, 0, MAXDWORD, MAXDWORD, &ov);
        }
    }
    ~FileLock() {
        if (handle != INVALID_HANDLE_VALUE) {
            OVERLAPPED ov = {};
            UnlockFileEx(handle, 0, MAXDWORD, MAXDWORD, &ov);
            CloseHandle(handle);
        }
    }
#else
    int fd = -1;
    explicit FileLock(const string& dataFile) {
        string lockPath = joinPath(g_dataDir, dataFile + ".lock");
        fd = open(lockPath.c_str(), O_CREAT | O_RDWR, 0644);
        if (fd >= 0) flock(fd, LOCK_EX);
    }
    ~FileLock() { if (fd >= 0) { flock(fd, LOCK_UN); close(fd); } }
#endif
    FileLock(const FileLock&) = delete; FileLock& operator=(const FileLock&) = delete;
};

// ---------------------------------------------------------------- data
struct Decision { string id, date, type, title; int priority = 0; };
struct Tx { string date, type, category, note; double amount = 0; };
struct Goal { string name; double target = 0, saved = 0; };
struct Task { string id, title, deadline, status; int urgency = 0, importance = 0; int score() const { return urgency * 2 + importance * 3; } };

static map<string, pair<string, string>> loadUsers() {  // username -> (password, role)
    map<string, pair<string, string>> users;
    for (auto& line : readLines(joinPath(g_dataDir, "users.txt"))) {
        istringstream is(line); string u, p, r;
        if (is >> u >> p >> r) users[u] = {p, r};
    }
    return users;
}
static vector<Decision> loadDecisions() {
    vector<Decision> out;
    for (auto& line : readLines(joinPath(g_dataDir, "decisions.txt"))) {
        auto parts = splitPipe(line); if (parts.size() < 5) continue;
        try { Decision d; d.id = parts[0]; d.date = parts[1]; d.type = parts[2]; d.priority = stoi(parts[3]);
              d.title = parts[4]; for (size_t i = 5; i < parts.size(); i++) d.title += "|" + parts[i]; out.push_back(d); }
        catch (...) {}
    }
    return out;
}
static Decision appendDecision(const string& type, int priority, const string& title) {
    FileLock lock("decisions.txt");
    auto ds = loadDecisions(); long long nextId = 1;
    for (auto& d : ds) { try { nextId = max(nextId, stoll(d.id) + 1); } catch (...) {} }
    Decision rec; rec.id = to_string(nextId); rec.date = todayStr(); rec.type = sanitize(type); rec.priority = priority; rec.title = sanitize(title);
    appendLine(joinPath(g_dataDir, "decisions.txt"), rec.id + "|" + rec.date + "|" + rec.type + "|" + to_string(rec.priority) + "|" + rec.title);
    return rec;
}
static string decisionJson(const Decision& d) {
    return "{\"id\":" + jsonStr(d.id) + ",\"date\":" + jsonStr(d.date) + ",\"type\":" + jsonStr(d.type) +
           ",\"priority\":" + to_string(d.priority) + ",\"title\":" + jsonStr(d.title) + "}";
}
static vector<Tx> loadTxs() {
    vector<Tx> out;
    for (auto& line : readLines(joinPath(g_dataDir, "transactions.txt"))) {
        auto parts = splitPipe(line); if (parts.size() < 5) continue;
        try { Tx t; t.date = parts[0]; t.type = parts[1]; t.category = parts[2]; t.amount = stod(parts[3]); t.note = parts[4]; out.push_back(t); } catch (...) {}
    }
    return out;
}
static vector<Goal> loadGoals() {
    vector<Goal> out;
    for (auto& line : readLines(joinPath(g_dataDir, "savings_goals.txt"))) {
        auto parts = splitPipe(line); if (parts.size() < 3) continue;
        try { Goal g; g.name = parts[0]; g.target = stod(parts[1]); g.saved = stod(parts[2]); out.push_back(g); } catch (...) {}
    }
    return out;
}
static void saveGoals(const vector<Goal>& goals) {
    vector<string> lines;
    for (auto& g : goals) lines.push_back(sanitize(g.name) + "|" + fmtNumRaw(g.target) + "|" + fmtNumRaw(g.saved));
    writeLines(joinPath(g_dataDir, "savings_goals.txt"), lines);
}
static vector<Task> loadTasks() {
    vector<Task> out;
    for (auto& line : readLines(joinPath(g_dataDir, "tasks.txt"))) {
        auto parts = splitPipe(line); if (parts.size() < 6) continue;
        try { Task t; t.id = parts[0]; t.title = parts[1]; t.urgency = stoi(parts[2]); t.importance = stoi(parts[3]); t.deadline = parts[4]; t.status = parts[5]; out.push_back(t); } catch (...) {}
    }
    sort(out.begin(), out.end(), [](const Task& a, const Task& b) {
        if (a.score() != b.score()) return a.score() > b.score();
        return a.id < b.id; });
    return out;
}
static void saveTasks(const vector<Task>& tasks) {
    vector<string> lines;
    for (auto& t : tasks) lines.push_back(sanitize(t.id) + "|" + sanitize(t.title) + "|" + to_string(t.urgency) + "|" + to_string(t.importance) + "|" + sanitize(t.deadline) + "|" + sanitize(t.status));
    writeLines(joinPath(g_dataDir, "tasks.txt"), lines);
}
static string taskJson(const Task& t) {
    return "{\"id\":" + jsonStr(t.id) + ",\"title\":" + jsonStr(t.title) + ",\"urgency\":" + to_string(t.urgency) +
           ",\"importance\":" + to_string(t.importance) + ",\"deadline\":" + jsonStr(t.deadline) +
           ",\"status\":" + jsonStr(t.status) + ",\"score\":" + to_string(t.score()) + "}";
}
static string priorityLevel(int score) {
    if (score >= 40) return "VERY HIGH";
    if (score >= 30) return "HIGH";
    if (score >= 20) return "MEDIUM";
    return "LOW";
}
static string makeToken() {
    // Cross-platform: random_device (backed by the OS CSPRNG on
    // both Windows and Linux) plus a process-wide counter, so two
    // tokens can never collide even if random_device repeats.
    unsigned char bytes[16];
    static random_device rd;
    for (auto& b : bytes) b = (unsigned char)(rd() & 0xff);
    unsigned long long ctr = ++g_tokenCounter;
    char buf[64]; snprintf(buf, sizeof(buf), "%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%llx",
        bytes[0],bytes[1],bytes[2],bytes[3],bytes[4],bytes[5],bytes[6],bytes[7],bytes[8],bytes[9],bytes[10],bytes[11],bytes[12],bytes[13],bytes[14],bytes[15], ctr);
    return buf;
}

// ---------------------------------------------------------------- HTTP
struct Request {
    string method, path, query, body, auth;
};
static string urlDecode(const string& s) {
    string out;
    for (size_t i = 0; i < s.size(); i++) {
        if (s[i] == '%' && i + 2 < s.size()) { out += (char)strtol(s.substr(i + 1, 2).c_str(), nullptr, 16); i += 2; }
        else if (s[i] == '+') out += ' ';
        else out += s[i];
    }
    return out;
}
static map<string, string> parseQuery(const string& q) {
    map<string, string> out; stringstream ss(q); string pair;
    while (getline(ss, pair, '&')) {
        size_t eq = pair.find('='); if (eq == string::npos) out[urlDecode(pair)] = "";
        else out[urlDecode(pair.substr(0, eq))] = urlDecode(pair.substr(eq + 1));
    }
    return out;
}
// Cross-platform socket type: SOCKET on Windows, int on POSIX.
#ifdef _WIN32
using SocketFd = SOCKET;
static void closeSocket(SocketFd fd) { closesocket(fd); }
#else
using SocketFd = int;
static void closeSocket(SocketFd fd) { close(fd); }
#endif

static void sendAll(SocketFd fd, const string& data) {
    size_t sent = 0; while (sent < data.size()) { auto n = send(fd, data.data() + sent, (int)(data.size() - sent), 0); if (n <= 0) break; sent += (size_t)n; }
}
static void sendResponse(SocketFd fd, int status, const string& ctype, const string& body) {
    string reason = status == 200 ? "OK" : status == 201 ? "Created" : status == 400 ? "Bad Request" : status == 401 ? "Unauthorized" : status == 404 ? "Not Found" : status == 413 ? "Payload Too Large" : "Error";
    ostringstream os; os << "HTTP/1.1 " << status << " " << reason << "\r\nContent-Type: " << ctype << "\r\nContent-Length: " << body.size() << "\r\nConnection: close\r\n\r\n" << body;
    sendAll(fd, os.str());
}
static void sendJson(SocketFd fd, int status, const string& body) { sendResponse(fd, status, "application/json", body); }
static void sendErr(SocketFd fd, int status, const string& msg) { sendJson(fd, status, "{\"error\":" + jsonStr(msg) + "}"); }

static string getSessionUser(const Request& req) {
    if (req.auth.rfind("Bearer ", 0) != 0) return "";
    lock_guard<mutex> lk(g_sessionMutex);
    auto it = g_sessions.find(req.auth.substr(7));
    return it == g_sessions.end() ? "" : it->second;
}

// Multi-task input: parse the "tasks" array from the request body.
struct MtTask { string name; int urgency = 0, energy = 0, minutes = 0; };
static vector<MtTask> parseMtTasks(const string& body, bool& ok) {
    ok = false; vector<MtTask> out;
    size_t arr = body.find("\"tasks\""); if (arr == string::npos) return out;
    size_t open = body.find('[', arr); size_t close = body.find(']', open); if (open == string::npos || close == string::npos) return out;
    string inner = body.substr(open + 1, close - open - 1);
    size_t pos = 0;
    while (true) {
        size_t o = inner.find('{', pos); if (o == string::npos) break;
        size_t c = inner.find('}', o); if (c == string::npos) break;
        string obj = inner.substr(o, c - o + 1);
        MtTask t; string name; double dv;
        if (!jsonStringField(obj, "name", name) || name.empty()) return vector<MtTask>();
        if (!jsonNumberField(obj, "deadlineUrgency", dv)) return vector<MtTask>();
        t.urgency = (int)dv;
        if (!jsonNumberField(obj, "energy", dv)) return vector<MtTask>();
        t.energy = (int)dv;
        if (!jsonNumberField(obj, "time", dv)) return vector<MtTask>();
        t.minutes = (int)dv;
        t.name = name; out.push_back(t); pos = c + 1;
    }
    ok = !out.empty(); return out;
}

static string habitStreakJson(const string& habit) {
    int total = 0; vector<string> dates;
    for (auto& line : readLines(joinPath(g_dataDir, "habit_log.txt"))) {
        auto p = splitPipe(line);
        if (p.size() >= 2 && p[0] == habit && validDate(p[1])) { total++; dates.push_back(p[1]); }
    }
    if (dates.empty()) return "{\"habit\":" + jsonStr(habit) + ",\"total\":0,\"streak\":0,\"latest\":null}";
    sort(dates.begin(), dates.end()); dates.erase(unique(dates.begin(), dates.end()), dates.end());
    int streak = 1; int current = daysFromCivilStr(dates.back());
    for (int i = (int)dates.size() - 2; i >= 0; i--) {
        int prev = daysFromCivilStr(dates[i]);
        if (current - prev == 1) { streak++; current = prev; } else break;
    }
    return "{\"habit\":" + jsonStr(habit) + ",\"total\":" + to_string(total) + ",\"streak\":" + to_string(streak) + ",\"latest\":" + jsonStr(dates.back()) + "}";
}

static void handleApi(SocketFd fd, const Request& req, const string& path, const map<string, string>& query) {
    string method = req.method;
    // ---- register / login / logout (no token needed) ----
    if (path == "/api/register" && method == "POST") {
        string username, password;
        if (!jsonStringField(req.body, "username", username) || !jsonStringField(req.body, "password", password))
            return sendErr(fd, 400, "Username and password are required.");
        if (username.empty() || username.find(' ') != string::npos)
            return sendErr(fd, 400, "Username must not be empty or contain spaces.");
        bool letter = false, digit = false;
        for (char c : password) { if (isalpha((unsigned char)c)) letter = true; if (isdigit((unsigned char)c)) digit = true; }
        if (password.size() < 8 || !letter || !digit)
            return sendErr(fd, 400, "Password must be 8+ characters with a letter and a digit.");
        auto users = loadUsers();
        if (users.count(username)) return sendErr(fd, 400, "Username already exists.");
        string role = users.empty() ? "ADMIN" : "USER";
        appendLine(joinPath(g_dataDir, "users.txt"), username + " " + password + " " + role);
        return sendJson(fd, 201, "{\"username\":" + jsonStr(username) + ",\"role\":" + jsonStr(role) + "}");
    }
    if (path == "/api/login" && method == "POST") {
        string username, password;
        jsonStringField(req.body, "username", username); jsonStringField(req.body, "password", password);
        auto users = loadUsers(); auto it = users.find(username);
        if (it == users.end() || it->second.first != password)
            return sendErr(fd, 401, "Invalid username or password.");
        string token = makeToken();
        { lock_guard<mutex> lk(g_sessionMutex); g_sessions[token] = username; }
        return sendJson(fd, 200, "{\"username\":" + jsonStr(username) + ",\"role\":" + jsonStr(it->second.second) + ",\"token\":" + jsonStr(token) + "}");
    }
    if (path == "/api/logout" && method == "POST") {
        if (req.auth.rfind("Bearer ", 0) == 0) { lock_guard<mutex> lk(g_sessionMutex); g_sessions.erase(req.auth.substr(7)); }
        return sendJson(fd, 200, "{\"ok\":true}");
    }
    // ---- everything below needs a login ----
    string user = getSessionUser(req);
    if (user.empty()) return sendErr(fd, 401, "Please log in first.");
    auto users = loadUsers(); string role = users.count(user) ? users[user].second : "USER";

    if (path == "/api/me" && method == "GET")
        return sendJson(fd, 200, "{\"username\":" + jsonStr(user) + ",\"role\":" + jsonStr(role) + "}");

    if (path == "/api/overview" && method == "GET") {
        auto ds = loadDecisions(); auto txs = loadTxs(); auto goals = loadGoals(); auto tasks = loadTasks();
        double income = 0, expense = 0; for (auto& t : txs) (t.type == "income" ? income : expense) += t.amount;
        double tg = 0, sg = 0; for (auto& g : goals) { tg += g.target; sg += g.saved; }
        int pending = 0; for (auto& t : tasks) if (t.status == "Pending") pending++;
        map<string, int> habits;
        for (auto& line : readLines(joinPath(g_dataDir, "habit_log.txt"))) { auto p = splitPipe(line); if (p.size() >= 2) habits[p[0]]++; }
        ostringstream os; os << "{\"username\":" << jsonStr(user) << ",\"role\":" << jsonStr(role)
            << ",\"decisions\":" << ds.size() << ",\"tasks\":" << tasks.size() << ",\"tasksPending\":" << pending
            << ",\"income\":" << fmtNum(income) << ",\"expense\":" << fmtNum(expense) << ",\"balance\":" << fmtNum(income - expense)
            << ",\"savingsGoals\":" << goals.size() << ",\"savingsTarget\":" << fmtNum(tg) << ",\"savingsSaved\":" << fmtNum(sg) << ",\"habits\":{";
        bool first = true; for (auto& kv : habits) { if (!first) os << ","; first = false; os << jsonStr(kv.first) << ":" << kv.second; }
        os << "}}"; return sendJson(fd, 200, os.str());
    }

    if (path == "/api/decisions" && method == "GET") {
        auto ds = loadDecisions(); string search, dtype;
        auto si = query.find("search"); if (si != query.end()) search = si->second;
        auto ti = query.find("type"); if (ti != query.end()) dtype = ti->second;
        string out = "["; bool first = true;
        for (auto& d : ds) {
            string lowTitle = d.title, lowType = d.type, lowSearch = search;
            transform(lowTitle.begin(), lowTitle.end(), lowTitle.begin(), ::tolower);
            transform(lowType.begin(), lowType.end(), lowType.begin(), ::tolower);
            transform(lowSearch.begin(), lowSearch.end(), lowSearch.begin(), ::tolower);
            if (!search.empty() && lowTitle.find(lowSearch) == string::npos && lowType.find(lowSearch) == string::npos) continue;
            if (!dtype.empty() && d.type != dtype) continue;
            if (!first) out += ",";
            first = false; out += decisionJson(d);
        }
        out += "]"; return sendJson(fd, 200, out);
    }
    if (path == "/api/decisions" && method == "POST") {
        string type, title; long long prio;
        jsonStringField(req.body, "type", type); if (type.empty()) type = "Daily";
        if (!jsonIntField(req.body, "priority", prio) || prio < 0 || prio > 1000 || !jsonStringField(req.body, "title", title) || trimStr(title).empty())
            return sendErr(fd, 400, "A decision needs a title and a numeric priority.");
        return sendJson(fd, 201, decisionJson(appendDecision(type, (int)prio, title)));
    }
    if (path.rfind("/api/decisions/", 0) == 0 && method == "DELETE") {
        string id = path.substr(string("/api/decisions/").size());
        FileLock lock("decisions.txt");
        auto lines = readLines(joinPath(g_dataDir, "decisions.txt")); vector<string> kept; bool found = false;
        for (auto& line : lines) { if (splitPipe(line)[0] == id) { found = true; continue; } kept.push_back(line); }
        if (!found) return sendErr(fd, 404, "Decision ID not found.");
        writeLines(joinPath(g_dataDir, "decisions.txt"), kept);
        return sendJson(fd, 200, "{\"deleted\":" + jsonStr(id) + "}");
    }

    if (path == "/api/daily-decision" && method == "POST") {
        double dv; long long available = -1, required = -1, urgency = -1, importance = -1, energy = -1;
        if (jsonNumberField(req.body, "availableTime", dv)) available = (long long)dv;
        if (jsonNumberField(req.body, "requiredTime", dv)) required = (long long)dv;
        if (jsonNumberField(req.body, "urgency", dv)) urgency = (long long)dv;
        if (jsonNumberField(req.body, "importance", dv)) importance = (long long)dv;
        if (jsonNumberField(req.body, "energy", dv)) energy = (long long)dv;
        if (available < 1 || available > 1440 || required < 1 || urgency < 1 || urgency > 10 || importance < 1 || importance > 10 || energy < 1 || energy > 10)
            return sendErr(fd, 400, "Check the ranges: time 1-1440, urgency/importance/energy 1-10.");
        string suggestion;
        if (required > available) suggestion = "Divide the task into smaller parts.";
        else if (urgency >= 8 && importance >= 8) suggestion = "Complete this task first.";
        else if (importance >= 8 && energy <= 4) suggestion = "Take a short break, then do this task.";
        else if (urgency >= 7) suggestion = "Complete this task soon.";
        else suggestion = "Schedule this task for later.";
        int score = (int)(urgency * 2 + importance * 3);
        Decision rec = appendDecision("Daily", score, "Daily decision: " + suggestion);
        return sendJson(fd, 200, "{\"suggestion\":" + jsonStr(suggestion) + ",\"score\":" + to_string(score) + ",\"record\":" + decisionJson(rec) + "}");
    }

    if (path == "/api/multi-task" && method == "POST") {
        double dv; long long eBudget = -1, tBudget = -1;
        if (jsonNumberField(req.body, "availableEnergy", dv)) eBudget = (long long)dv;
        if (jsonNumberField(req.body, "availableTime", dv)) tBudget = (long long)dv;
        bool ok = false; auto tasks = parseMtTasks(req.body, ok);
        if (eBudget < 1 || eBudget > 100 || tBudget < 1 || tBudget > 1440 || !ok || tasks.size() > 20)
            return sendErr(fd, 400, "Give 1-20 tasks, energy 1-100, time 1-1440.");
        for (auto& t : tasks) if (t.urgency < 1 || t.urgency > 10 || t.energy < 1 || t.energy > 10 || t.minutes < 1 || t.minutes > 1440)
            return sendErr(fd, 400, "Each task needs a name, urgency 1-10, energy 1-10, time 1-1440.");
        stable_sort(tasks.begin(), tasks.end(), [](const MtTask& a, const MtTask& b) { return a.urgency > b.urgency; });
        vector<MtTask> rec, skip; long long re = eBudget, rt = tBudget;
        for (auto& t : tasks) {
            if (t.energy <= re && t.minutes <= rt) { re -= t.energy; rt -= t.minutes; rec.push_back(t); appendDecision("MultiTask", t.urgency * 5, "Multi-task: " + t.name); }
            else skip.push_back(t);
        }
        auto arrJson = [](const vector<MtTask>& v) { string s = "["; bool f = true; for (auto& t : v) { if (!f) s += ","; f = false; s += "{\"name\":" + jsonStr(t.name) + ",\"deadlineUrgency\":" + to_string(t.urgency) + ",\"energy\":" + to_string(t.energy) + ",\"time\":" + to_string(t.minutes) + "}"; } return s + "]"; };
        return sendJson(fd, 200, "{\"recommended\":" + arrJson(rec) + ",\"skipped\":" + arrJson(skip) + ",\"remainingEnergy\":" + to_string(re) + ",\"remainingTime\":" + to_string(rt) + "}");
    }

    if (path == "/api/priority" && method == "POST") {
        double dv; long long urgency = -1, importance = -1;
        if (jsonNumberField(req.body, "urgency", dv)) urgency = (long long)dv;
        if (jsonNumberField(req.body, "importance", dv)) importance = (long long)dv;
        if (urgency < 1 || urgency > 10 || importance < 1 || importance > 10)
            return sendErr(fd, 400, "Urgency and importance must be 1-10.");
        int score = (int)(urgency * 2 + importance * 3);
        return sendJson(fd, 200, "{\"score\":" + to_string(score) + ",\"max\":50,\"level\":" + jsonStr(priorityLevel(score)) + "}");
    }

    if (path == "/api/tasks" && method == "GET") {
        auto tasks = loadTasks(); string out = "["; bool first = true;
        for (auto& t : tasks) { if (!first) out += ","; first = false; out += taskJson(t); }
        return sendJson(fd, 200, out + "]");
    }
    if (path == "/api/tasks" && method == "POST") {
        string title, deadline; double dv; long long urgency = -1, importance = -1;
        jsonStringField(req.body, "title", title); jsonStringField(req.body, "deadline", deadline);
        if (jsonNumberField(req.body, "urgency", dv)) urgency = (long long)dv;
        if (jsonNumberField(req.body, "importance", dv)) importance = (long long)dv;
        if (trimStr(title).empty() || urgency < 1 || urgency > 10 || importance < 1 || importance > 10)
            return sendErr(fd, 400, "A task needs a title, urgency 1-10, importance 1-10.");
        if (!deadline.empty() && !validDate(deadline))
            return sendErr(fd, 400, "Deadline must be a real YYYY-MM-DD date, or blank.");
        FileLock lock("tasks.txt");
        auto tasks = loadTasks(); long long nextId = 1;
        for (auto& t : tasks) { try { nextId = max(nextId, stoll(t.id) + 1); } catch (...) {} }
        Task task; task.id = to_string(nextId); task.title = title; task.urgency = (int)urgency; task.importance = (int)importance; task.deadline = deadline; task.status = "Pending";
        tasks.push_back(task); saveTasks(tasks);
        return sendJson(fd, 201, taskJson(task));
    }
    if (path.rfind("/api/tasks/", 0) == 0 && (method == "PATCH" || method == "DELETE")) {
        string id = path.substr(string("/api/tasks/").size());
        FileLock lock("tasks.txt");
        auto tasks = loadTasks(); Task* found = nullptr;
        for (auto& t : tasks) if (t.id == id) found = &t;
        if (!found) return sendErr(fd, 404, "Task not found.");
        if (method == "DELETE") {
            vector<Task> kept; for (auto& t : tasks) if (t.id != id) kept.push_back(t);
            saveTasks(kept); return sendJson(fd, 200, "{\"deleted\":" + jsonStr(id) + "}");
        }
        string status; if (!jsonStringField(req.body, "status", status) || (status != "Pending" && status != "In Progress" && status != "Completed"))
            return sendErr(fd, 400, "Status must be Pending, In Progress, or Completed.");
        found->status = status; Task copy = *found; saveTasks(tasks);
        return sendJson(fd, 200, taskJson(copy));
    }

    if (path == "/api/budget" && method == "GET") {
        auto ii = query.find("income"), ei = query.find("expenses");
        if (ii == query.end() || ei == query.end()) return sendErr(fd, 400, "Income and expenses must be numbers >= 0.");
        double income, expenses;
        try { income = stod(ii->second); expenses = stod(ei->second); } catch (...) { return sendErr(fd, 400, "Income and expenses must be numbers >= 0."); }
        if (income < 0 || expenses < 0) return sendErr(fd, 400, "Income and expenses must be numbers >= 0.");
        double rem = income - expenses;
        string decision = rem < 0 ? "Reduce expenses." : rem == 0 ? "Income equals expenses." : "Save money for the future.";
        return sendJson(fd, 200, "{\"income\":" + fmtNum(income) + ",\"expenses\":" + fmtNum(expenses) + ",\"remaining\":" + fmtNum(rem) + ",\"decision\":" + jsonStr(decision) + "}");
    }

    if (path == "/api/transactions" && method == "GET") {
        auto txs = loadTxs(); string out = "["; bool first = true;
        for (auto& t : txs) { if (!first) out += ","; first = false;
            out += "{\"date\":" + jsonStr(t.date) + ",\"type\":" + jsonStr(t.type) + ",\"category\":" + jsonStr(t.category) + ",\"amount\":" + fmtNum(t.amount) + ",\"note\":" + jsonStr(t.note) + "}"; }
        return sendJson(fd, 200, out + "]");
    }
    if (path == "/api/transactions" && method == "POST") {
        string date, type, category, note; double amount = -1;
        jsonStringField(req.body, "date", date); jsonStringField(req.body, "type", type); jsonStringField(req.body, "category", category); jsonStringField(req.body, "note", note);
        jsonNumberField(req.body, "amount", amount);
        if (!validDate(date) || (type != "income" && type != "expense") || trimStr(category).empty() || amount < 0)
            return sendErr(fd, 400, "Need a real date, type income/expense, a category, and an amount >= 0.");
        FileLock lock("transactions.txt");
        appendLine(joinPath(g_dataDir, "transactions.txt"), date + "|" + type + "|" + sanitize(category) + "|" + fmtNumRaw(amount) + "|" + sanitize(note));
        return sendJson(fd, 201, "{\"date\":" + jsonStr(date) + ",\"type\":" + jsonStr(type) + ",\"category\":" + jsonStr(category) + ",\"amount\":" + fmtNum(amount) + ",\"note\":" + jsonStr(note) + "}");
    }

    if (path == "/api/savings" && method == "GET") {
        auto goals = loadGoals(); string out = "["; bool first = true;
        for (auto& g : goals) { if (!first) out += ","; first = false;
            out += "{\"name\":" + jsonStr(g.name) + ",\"target\":" + fmtNum(g.target) + ",\"saved\":" + fmtNum(g.saved) + "}"; }
        return sendJson(fd, 200, out + "]");
    }
    if (path == "/api/savings" && method == "POST") {
        string name; double target = -1; jsonStringField(req.body, "name", name); jsonNumberField(req.body, "target", target);
        if (trimStr(name).empty() || target <= 0) return sendErr(fd, 400, "A goal needs a name and a target > 0.");
        FileLock lock("savings_goals.txt");
        auto goals = loadGoals();
        for (auto& g : goals) if (g.name == name) return sendErr(fd, 400, "A goal with that name already exists.");
        goals.push_back({name, target, 0}); saveGoals(goals);
        return sendJson(fd, 201, "{\"name\":" + jsonStr(name) + ",\"target\":" + fmtNum(target) + ",\"saved\":0}");
    }
    if (path == "/api/savings/add" && method == "POST") {
        string name; double amount = -1; jsonStringField(req.body, "name", name); jsonNumberField(req.body, "amount", amount);
        if (amount <= 0) return sendErr(fd, 400, "Amount must be > 0.");
        FileLock lock("savings_goals.txt");
        auto goals = loadGoals();
        for (auto& g : goals) if (g.name == name) { g.saved += amount; saveGoals(goals);
            return sendJson(fd, 200, "{\"name\":" + jsonStr(g.name) + ",\"target\":" + fmtNum(g.target) + ",\"saved\":" + fmtNum(g.saved) + "}"); }
        return sendErr(fd, 404, "Goal not found.");
    }

    if (path == "/api/habits" && method == "GET") {
        map<string, vector<string>> byHabit;
        for (auto& line : readLines(joinPath(g_dataDir, "habit_log.txt"))) { auto p = splitPipe(line); if (p.size() >= 2) byHabit[p[0]].push_back(p[1]); }
        string out = "["; bool first = true;
        for (auto& kv : byHabit) { sort(kv.second.begin(), kv.second.end()); if (!first) out += ","; first = false;
            out += "{\"habit\":" + jsonStr(kv.first) + ",\"dates\":["; bool f2 = true; for (auto& d : kv.second) { if (!f2) out += ","; f2 = false; out += jsonStr(d); } out += "]}"; }
        return sendJson(fd, 200, out + "]");
    }
    if (path == "/api/habits" && method == "POST") {
        string habit, date; jsonStringField(req.body, "habit", habit); jsonStringField(req.body, "date", date);
        if (date.empty()) date = todayStr();
        if (trimStr(habit).empty() || !validDate(date)) return sendErr(fd, 400, "Need a habit name and a real YYYY-MM-DD date.");
        { FileLock lock("habit_log.txt"); appendLine(joinPath(g_dataDir, "habit_log.txt"), sanitize(habit) + "|" + date); }
        return sendJson(fd, 201, habitStreakJson(habit));
    }
    if (path == "/api/habits/streak" && method == "GET") {
        auto it = query.find("habit"); if (it == query.end() || it->second.empty()) return sendErr(fd, 400, "Give a habit name, for example ?habit=Reading.");
        return sendJson(fd, 200, habitStreakJson(it->second));
    }

    if (path == "/api/reports" && method == "GET") {
        auto txs = loadTxs();
        auto mi = query.find("month"), wi = query.find("week_end");
        vector<Tx> selected; string label;
        if (mi != query.end() && !mi->second.empty()) {
            if (!validMonth(mi->second)) return sendErr(fd, 400, "Month must be YYYY-MM.");
            for (auto& t : txs) if (t.date.rfind(mi->second, 0) == 0) selected.push_back(t);
            label = "Monthly report for " + mi->second;
        } else if (wi != query.end() && !wi->second.empty()) {
            if (!validDate(wi->second)) return sendErr(fd, 400, "Week end must be a real YYYY-MM-DD date.");
            int endDays = daysFromCivilStr(wi->second);
            for (auto& t : txs) if (validDate(t.date)) { int d = endDays - daysFromCivilStr(t.date); if (d >= 0 && d <= 6) selected.push_back(t); }
            label = "Weekly report ending " + wi->second;
        } else return sendErr(fd, 400, "Give ?month=YYYY-MM or ?week_end=YYYY-MM-DD.");
        double income = 0, expense = 0; for (auto& t : selected) (t.type == "income" ? income : expense) += t.amount;
        string out = "{\"label\":" + jsonStr(label) + ",\"transactions\":["; bool first = true;
        for (auto& t : selected) { if (!first) out += ","; first = false;
            out += "{\"date\":" + jsonStr(t.date) + ",\"type\":" + jsonStr(t.type) + ",\"category\":" + jsonStr(t.category) + ",\"amount\":" + fmtNum(t.amount) + ",\"note\":" + jsonStr(t.note) + "}"; }
        out += "],\"income\":" + fmtNum(income) + ",\"expense\":" + fmtNum(expense) + ",\"balance\":" + fmtNum(income - expense) + ",\"count\":" + to_string(selected.size()) + "}";
        return sendJson(fd, 200, out);
    }

    if (path == "/api/backup" && method == "POST") {
        if (!fileExists(joinPath(g_dataDir, "decisions.txt"))) return sendErr(fd, 400, "No decision file found to back up.");
        FileLock lock("decisions.txt");
        auto lines = readLines(joinPath(g_dataDir, "decisions.txt"));
        writeLines(joinPath(g_dataDir, "decisions_backup.txt"), lines);
        return sendJson(fd, 200, "{\"backedUp\":" + to_string(lines.size()) + "}");
    }
    if (path == "/api/restore" && method == "POST") {
        if (!fileExists(joinPath(g_dataDir, "decisions_backup.txt"))) return sendErr(fd, 400, "No backup file found.");
        FileLock lock("decisions.txt");
        auto lines = readLines(joinPath(g_dataDir, "decisions_backup.txt"));
        writeLines(joinPath(g_dataDir, "decisions.txt"), lines);
        return sendJson(fd, 200, "{\"restored\":" + to_string(lines.size()) + "}");
    }

    // ---- new sections (all mirror the console modules of the same name) ----
    if (path == "/api/info" && method == "GET")
        return sendJson(fd, 200, "{\"backend\":\"C++\",\"server\":\"cpp_server.cpp\",\"dataFiles\":[\"users.txt\",\"decisions.txt\",\"tasks.txt\",\"transactions.txt\",\"savings_goals.txt\",\"habit_log.txt\"]}");
    if (path == "/api/users" && method == "GET") {
        // Mirrors admin.cpp: username and role only, never passwords.
        if (role != "ADMIN") return sendErr(fd, 403, "Only an ADMIN can list users.");
        auto users = loadUsers(); string out = "[";
        bool first = true; for (auto& kv : users) { if (!first) out += ","; first = false; out += "{\"username\":" + jsonStr(kv.first) + ",\"role\":" + jsonStr(kv.second.second) + "}"; }
        return sendJson(fd, 200, out + "]");
    }
    if (path == "/api/change-password" && method == "POST") {
        string cur, nw;
        jsonStringField(req.body, "currentPassword", cur); jsonStringField(req.body, "newPassword", nw);
        auto users = loadUsers(); auto it = users.find(user);
        if (it == users.end() || it->second.first != cur) return sendErr(fd, 400, "Wrong current password.");
        bool letter = false, digit = false;
        for (char c : nw) { if (isalpha((unsigned char)c)) letter = true; if (isdigit((unsigned char)c)) digit = true; }
        if (nw.size() < 8 || !letter || !digit) return sendErr(fd, 400, "Password must be 8+ characters with a letter and a digit.");
        FileLock lock("users.txt");
        // Re-read under the lock so a concurrent register cannot be lost.
        auto fresh = loadUsers(); if (fresh.count(user) && fresh[user].first != cur) return sendErr(fd, 400, "Wrong current password.");
        vector<string> lines;
        for (auto& kv : fresh) lines.push_back(kv.first + " " + (kv.first == user ? nw : kv.second.first) + " " + kv.second.second);
        writeLines(joinPath(g_dataDir, "users.txt"), lines);
        return sendJson(fd, 200, "{\"ok\":true}");
    }
    if (path == "/api/study-planner" && method == "POST") {
        // Mirrors study_planner.cpp: days 1-365, hours 1-24, total = days*hours.
        string subject; double dv; long long days = -1, hours = -1;
        jsonStringField(req.body, "subject", subject);
        if (jsonNumberField(req.body, "days", dv)) days = (long long)dv;
        if (jsonNumberField(req.body, "hours", dv)) hours = (long long)dv;
        if (trimStr(subject).empty() || days < 1 || days > 365 || hours < 1 || hours > 24)
            return sendErr(fd, 400, "A plan needs a subject, days 1-365, hours 1-24.");
        ostringstream os; os << "{\"subject\":" << jsonStr(subject) << ",\"days\":" << days << ",\"hoursPerDay\":" << hours << ",\"totalHours\":" << (days * hours) << ",\"plan\":[";
        for (long long d = 1; d <= days; d++) { if (d > 1) os << ","; os << "{\"day\":" << d << ",\"text\":" << jsonStr("Day " + to_string(d) + ": " + subject + " - " + to_string(hours) + " hour(s)") << "}"; }
        return sendJson(fd, 200, os.str() + "]}");
    }
    if (path == "/api/time-allocation" && method == "POST") {
        // Mirrors time_allocation.cpp: each 0-24, total, remaining or warning.
        double dv; long long sleepH = -1, studyH = -1, workH = -1, otherH = -1;
        if (jsonNumberField(req.body, "sleep", dv)) sleepH = (long long)dv;
        if (jsonNumberField(req.body, "study", dv)) studyH = (long long)dv;
        if (jsonNumberField(req.body, "work", dv)) workH = (long long)dv;
        if (jsonNumberField(req.body, "other", dv)) otherH = (long long)dv;
        if (sleepH < 0 || sleepH > 24 || studyH < 0 || studyH > 24 || workH < 0 || workH > 24 || otherH < 0 || otherH > 24)
            return sendErr(fd, 400, "Each value must be 0-24 hours.");
        long long total = sleepH + studyH + workH + otherH;
        ostringstream os; os << "{\"sleep\":" << sleepH << ",\"study\":" << studyH << ",\"work\":" << workH << ",\"other\":" << otherH << ",\"total\":" << total;
        if (total > 24) os << ",\"remaining\":null,\"warning\":\"Total exceeds 24 hours!\"";
        else os << ",\"remaining\":" << (24 - total) << ",\"warning\":null";
        return sendJson(fd, 200, os.str() + "}");
    }
    if (path == "/api/decision-explanation" && method == "POST") {
        // Mirrors decision_explanation.cpp: score = urgency*2 + importance*3.
        double dv; long long urgency = -1, importance = -1;
        if (jsonNumberField(req.body, "urgency", dv)) urgency = (long long)dv;
        if (jsonNumberField(req.body, "importance", dv)) importance = (long long)dv;
        if (urgency < 1 || urgency > 10 || importance < 1 || importance > 10)
            return sendErr(fd, 400, "Urgency and importance must be 1-10.");
        long long score = urgency * 2 + importance * 3;
        string level, rec;
        if (score >= 40) { level = "Very high priority."; rec = "Complete this task first."; }
        else if (score >= 30) { level = "High priority."; rec = "Schedule it soon."; }
        else if (score >= 20) { level = "Medium priority."; rec = "Plan it after higher-priority tasks."; }
        else { level = "Low priority based on this score."; rec = "Schedule it when time is available."; }
        ostringstream os; os << "{\"urgency\":" << urgency << ",\"importance\":" << importance << ",\"score\":" << score
            << ",\"formula\":\"Formula: (Urgency x 2) + (Importance x 3)\""
            << ",\"calculation\":\"Calculation: (" << urgency << " x 2) + (" << importance << " x 3) = " << score << "/50\""
            << ",\"explanation\":" << jsonStr(level) << ",\"recommendation\":" << jsonStr(rec) << "}";
        return sendJson(fd, 200, os.str());
    }
    if (path == "/api/deadlines" && method == "GET") {
        // Mirrors deadline_alert.cpp: string comparison on YYYY-MM-DD,
        // Completed tasks skipped, malformed deadlines flagged.
        string today; auto ti = query.find("today"); if (ti != query.end()) today = ti->second; else today = todayStr();
        if (!validDate(today)) return sendErr(fd, 400, "Today must be a real YYYY-MM-DD date.");
        auto tasks = loadTasks(); string out = "[";
        bool first = true;
        for (auto& t : tasks) {
            if (t.status == "Completed") continue;
            string alert;
            if (t.deadline.size() != 10 || t.deadline[4] != '-' || t.deadline[7] != '-') alert = "CHECK";
            else if (t.deadline < today) alert = "OVERDUE";
            else if (t.deadline == today) alert = "DUE TODAY";
            else alert = "UPCOMING";
            if (!first) out += ",";
            first = false;
            out += "{\"id\":" + jsonStr(t.id) + ",\"title\":" + jsonStr(t.title) + ",\"deadline\":" + jsonStr(t.deadline) + ",\"status\":" + jsonStr(t.status) + ",\"alert\":" + jsonStr(alert) + "}";
        }
        return sendJson(fd, 200, out + "]");
    }

    return sendErr(fd, 404, "Unknown API endpoint.");
}

// ---------------------------------------------------------------- connections
static void serveStatic(SocketFd fd, const string& path) {
    string name;
    if (path == "/" || path == "/index.html") name = "index.html";
    else if (path == "/style.css") name = "style.css";
    else if (path == "/app.js") name = "app.js";
    else { sendErr(fd, 404, "Not found."); return; }
    ifstream in(joinPath(g_staticDir, name), ios::binary);
    if (!in) { sendErr(fd, 404, "File not found."); return; }
    string body((istreambuf_iterator<char>(in)), istreambuf_iterator<char>());
    string ctype = name == "index.html" ? "text/html" : name == "style.css" ? "text/css" : "application/javascript";
    sendResponse(fd, 200, ctype, body);
}

static void handleConnection(SocketFd clientFd) {
    // Read headers (cap: 64 KiB of headers).
    string raw; char buf[4096];
    while (raw.find("\r\n\r\n") == string::npos && raw.size() < 65536) {
        auto n = recv(clientFd, buf, sizeof(buf), 0);
        if (n <= 0) { closeSocket(clientFd); return; }
        raw.append(buf, (size_t)n);
    }
    size_t headerEnd = raw.find("\r\n\r\n");
    if (headerEnd == string::npos) { closeSocket(clientFd); return; }
    string head = raw.substr(0, headerEnd);
    string body = raw.substr(headerEnd + 4);
    istringstream hs(head); string method, target, version;
    hs >> method >> target >> version;
    map<string, string> headers; string line; getline(hs, line);  // consume rest of request line
    while (getline(hs, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        size_t colon = line.find(':'); if (colon == string::npos) continue;
        string key = trimStr(line.substr(0, colon)), val = trimStr(line.substr(colon + 1));
        transform(key.begin(), key.end(), key.begin(), ::tolower);
        headers[key] = val;
    }
    long long contentLength = 0;
    auto ci = headers.find("content-length");
    if (ci != headers.end()) { try { contentLength = stoll(ci->second); } catch (...) { contentLength = 0; } }
    if (contentLength < 0 || contentLength > 1048576) { sendErr(clientFd, 413, "Request body too large (max 1 MiB)."); closeSocket(clientFd); return; }
    while ((long long)body.size() < contentLength) {
        auto n = recv(clientFd, buf, sizeof(buf), 0);
        if (n <= 0) break;
        body.append(buf, (size_t)n);
    }
    if ((long long)body.size() > contentLength) body = body.substr(0, (size_t)contentLength);

    Request req; req.method = method; req.body = body;
    auto ai = headers.find("authorization"); if (ai != headers.end()) req.auth = ai->second;
    size_t qm = target.find('?');
    req.path = qm == string::npos ? target : target.substr(0, qm);
    req.query = qm == string::npos ? "" : target.substr(qm + 1);

    if (req.path.rfind("/api/", 0) == 0) {
        lock_guard<mutex> lk(g_apiMutex);
        handleApi(clientFd, req, req.path, parseQuery(req.query));
    } else if (method == "GET") {
        serveStatic(clientFd, req.path);
    } else {
        sendErr(clientFd, 404, "Not found.");
    }
    closeSocket(clientFd);
}

int main(int argc, char** argv) {
    int port = 8000;
    for (int i = 1; i < argc; i++) {
        string arg = argv[i];
        if (arg == "--port" && i + 1 < argc) port = atoi(argv[++i]);
        else if (arg == "--data-dir" && i + 1 < argc) g_dataDir = argv[++i];
        else if (arg == "--help") {
            cout << "Usage: cpp_server [--port 8000] [--data-dir PATH]\n"
                 << "Run from the repository root so the data files are the\n"
                 << "same ones the C++ console app reads. Binds to 127.0.0.1 only.\n";
            return 0;
        }
    }
    // Static files live next to this source file's installed location:
    // when run from the repo root they are in dashboard/; otherwise
    // fall back to the current directory.
    if (fileExists("dashboard/index.html")) g_staticDir = "dashboard";
    else if (fileExists("index.html")) g_staticDir = ".";
    else g_staticDir = "dashboard";

#ifdef _WIN32
    WSADATA wsa; if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) { cerr << "WSAStartup failed.\n"; return 1; }
#endif
    SocketFd serverFd = socket(AF_INET, SOCK_STREAM, 0);
#ifdef _WIN32
    if (serverFd == INVALID_SOCKET) { cerr << "Could not create socket.\n"; WSACleanup(); return 1; }
#else
    if (serverFd < 0) { cerr << "Could not create socket.\n"; return 1; }
#endif
    int opt = 1; setsockopt(serverFd, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));
    sockaddr_in addr{}; addr.sin_family = AF_INET; addr.sin_port = htons((uint16_t)port);
    addr.sin_addr.s_addr = inet_addr("127.0.0.1");  // loopback only, never 0.0.0.0
    if (bind(serverFd, (sockaddr*)&addr, sizeof(addr)) < 0) { cerr << "Could not bind to 127.0.0.1:" << port << " (is another server running?).\n"; return 1; }
    if (listen(serverFd, 32) < 0) { cerr << "Could not listen.\n"; return 1; }
    cout << "Dashboard (C++ backend): http://127.0.0.1:" << port << "/\n";
    cout << "Data directory (same files as the C++ app): " << g_dataDir << "\n";
    cout << "Press Ctrl+C to stop. This server binds to localhost only.\n" << flush;
#ifndef _WIN32
    signal(SIGPIPE, SIG_IGN);
#endif
    while (true) {
        SocketFd clientFd = accept(serverFd, nullptr, nullptr);
#ifdef _WIN32
        if (clientFd == INVALID_SOCKET) continue;
#else
        if (clientFd < 0) continue;
#endif
        thread(handleConnection, clientFd).detach();
    }
    return 0;
}
