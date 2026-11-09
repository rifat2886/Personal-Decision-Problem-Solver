#ifndef CONSOLE_PG_H
#define CONSOLE_PG_H

// Console Postgres adapter — Phase 4, Batch B.
//
// When the DATABASE_URL environment variable is set, the console app
// reads and writes the SAME PostgreSQL database as the C++ dashboard
// server (same tables, same owner rules, same PBKDF2 users table).
// When DATABASE_URL is unset, the console behaves exactly as before
// (local txt files). There is no silent fallback: if DATABASE_URL is
// set but the database cannot be reached (or this binary was built
// without libpq), initStorage() fails and main() exits with an
// error instead of serving a different, empty txt data set.
//
// Design — mirror the server's own pattern (dashboard/cpp_server.cpp
// pgHabitLines()/pgErrorLines()): the adapter speaks the txt line
// formats. readLines() returns rows as txt-format lines, so the menu
// modules' parsing, filtering and display code stays identical;
// insertLines()/rewriteVisible() take txt-format lines back.
// Per-user isolation matches the server exactly: a row is visible
// to the current user when owner == current user, or when it is a
// legacy row (owner NULL) and the current user is the only user in
// the users table. ADMIN gets no exception.
//
// Build: the console links -lpq only when libpq is present (opt-in,
// same as the server/Makefile: pg_config --includedir for the -I
// flag, -lpq for the link). Without libpq, pgInit() fails with a
// clear message and DATABASE_URL mode exits; txt mode still builds
// and runs. This keeps the Windows/MinGW build working.
//
// No secret is in this file: DATABASE_URL comes only from the
// environment at runtime and is never logged. Table names in SQL
// come only from this file's own fixed strings, never user input.

#include "data_owner.h"
#include "dashboard/pg_store.h"

#include <cstdlib>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace console_pg {

// True after a successful initStorage() with DATABASE_URL set.
inline bool g_pgMode = false;

inline bool pgMode() { return g_pgMode; }

// Connect (Postgres mode) or stay in txt mode. Returns false only
// when DATABASE_URL is set and Postgres cannot be used; err then
// holds the reason (including "not compiled in" when this binary
// was built without libpq). Call once from main(), before the menu.
inline bool initStorage(std::string& err) {
    const char* url = std::getenv("DATABASE_URL");
    if (url == nullptr || url[0] == '\0') {
        g_pgMode = false;
        return true;
    }
    // pgInit() connects and creates the schema if missing (same DDL
    // as the server — pg_store.h is the single source of truth).
    if (!pgstore::pgInit(url, err)) return false;
    g_pgMode = true;
    return true;
}

inline void shutdown() {
    pgstore::pgShutdown();
    g_pgMode = false;
}

// --- small helpers -------------------------------------------------

// Same field sanitiser as the server (and the console txt stores):
// a user-supplied '|' would break the txt line format.
inline std::string pgSanitize(const std::string& v) {
    std::string out = v;
    for (char& c : out)
        if (c == '|' || c == '\n' || c == '\r') c = '/';
    return out;
}

// Same number formatting as the server's fmtNumRaw / the console's
// `<< double`: 10000 stays "10000", 99.95 stays "99.95".
inline std::string fmtNum(double v) {
    std::ostringstream os;
    os << v;
    return os.str();
}

// --- users ---------------------------------------------------------

inline bool getUser(const std::string& username, std::string& hash,
                    std::string& role) {
    std::vector<pgstore::Row> rows;
    std::string err;
    if (!pgstore::pgQuery(
            "SELECT password_hash, role FROM users WHERE username = $1",
            {username}, rows, err))
        return false;
    if (rows.empty()) return false;
    hash = rows[0][0].text;
    role = rows[0][1].text;
    return true;
}

inline bool userExists(const std::string& username) {
    std::string hash, role;
    return getUser(username, hash, role);
}

inline bool insertUser(const std::string& username, const std::string& hash,
                       const std::string& role) {
    std::string err;
    return pgstore::pgExec(
        "INSERT INTO users (username, password_hash, role) VALUES ($1,$2,$3)",
        {username, hash, role}, err);
}

inline bool updateUserHash(const std::string& username,
                           const std::string& hash) {
    std::string err;
    return pgstore::pgExec(
        "UPDATE users SET password_hash = $1 WHERE username = $2",
        {hash, username}, err);
}

inline std::vector<std::pair<std::string, std::string>> listUsers() {
    std::vector<std::pair<std::string, std::string>> out;
    std::vector<pgstore::Row> rows;
    std::string err;
    if (!pgstore::pgQuery("SELECT username, role FROM users ORDER BY username",
                          {}, rows, err))
        return out;
    for (auto& r : rows) out.push_back({r[0].text, r[1].text});
    return out;
}

inline std::size_t userCount() {
    std::vector<pgstore::Row> rows;
    std::string err;
    if (!pgstore::pgQuery("SELECT COUNT(*) FROM users", {}, rows, err) ||
        rows.empty())
        return 0;
    try {
        return static_cast<std::size_t>(std::stoull(rows[0][0].text));
    } catch (...) {
        return 0;
    }
}

// True when the users table holds exactly one user and it is the
// current user — the legacy-visibility rule (see data_owner.h).
inline bool isSoleUser() {
    std::vector<pgstore::Row> rows;
    std::string err;
    if (!pgstore::pgQuery("SELECT username FROM users", {}, rows, err))
        return false;
    return rows.size() == 1 && rows[0][0].text == g_currentUser;
}

// --- visibility (Postgres side of data_owner.h's rule) -------------

inline bool ownerVisible(const std::string& owner) {
    if (owner == g_currentUser) return true;
    if (!owner.empty()) return false;
    return isSoleUser();  // legacy row (owner NULL)
}

inline bool lineVisible(const std::string& line, std::size_t expectedFields) {
    return ownerVisible(ownerOfLine(line, expectedFields));
}

// --- transactions --------------------------------------------------

inline bool beginTx() {
    std::string err;
    return pgstore::pgExec("BEGIN", {}, err);
}

inline bool commitTx() {
    std::string err;
    return pgstore::pgExec("COMMIT", {}, err);
}

inline bool rollbackTx() {
    std::string err;
    return pgstore::pgExec("ROLLBACK", {}, err);
}

// --- line-oriented table access ------------------------------------
// Tables: decisions, decisions_backup, tasks, transactions,
// savings_goals, habit_log, daily_reports, error_logs. "users" is
// NOT a line table (space-separated txt format) — use getUser() etc.

// All rows as txt-format lines, ORDER BY id, owner as the last field
// (a NULL owner serialises with no owner field, i.e. a legacy row).
inline std::vector<std::string> readLines(const std::string& table) {
    std::vector<std::string> out;
    std::vector<pgstore::Row> rows;
    std::string err;
    std::string sql;
    if (table == "decisions" || table == "decisions_backup")
        sql = "SELECT id, record_date, type, priority, title, owner FROM " +
              table + " ORDER BY id";
    else if (table == "tasks")
        sql = "SELECT id, title, urgency, importance, deadline, status, "
              "owner FROM tasks ORDER BY id";
    else if (table == "transactions")
        sql = "SELECT tx_date, type, category, amount, note, owner FROM "
              "transactions ORDER BY id";
    else if (table == "savings_goals")
        sql = "SELECT name, target, saved, owner FROM savings_goals "
              "ORDER BY id";
    else if (table == "habit_log")
        sql = "SELECT habit, log_date, owner FROM habit_log ORDER BY id";
    else if (table == "daily_reports")
        sql = "SELECT line FROM daily_reports ORDER BY id";
    else if (table == "error_logs")
        sql = "SELECT line FROM error_logs ORDER BY id";
    else
        return out;  // unknown table: no rows, never user input
    if (!pgstore::pgQuery(sql, {}, rows, err)) return out;
    for (auto& r : rows) {
        // Owner suffix: NULL owner means a legacy row (no field).
        auto suffix = [](const pgstore::Value& v) {
            return v.isNull ? std::string("") : "|" + v.text;
        };
        if (table == "decisions" || table == "decisions_backup")
            out.push_back(r[0].text + "|" + r[1].text + "|" + r[2].text +
                          "|" + r[3].text + "|" + r[4].text + suffix(r[5]));
        else if (table == "tasks")
            out.push_back(r[0].text + "|" + r[1].text + "|" + r[2].text +
                          "|" + r[3].text + "|" + r[4].text + "|" +
                          r[5].text + suffix(r[6]));
        else if (table == "transactions")
            out.push_back(r[0].text + "|" + r[1].text + "|" + r[2].text +
                          "|" + r[3].text + "|" + r[4].text + suffix(r[5]));
        else if (table == "savings_goals")
            out.push_back(r[0].text + "|" + r[1].text + "|" + r[2].text +
                          suffix(r[3]));
        else if (table == "habit_log")
            out.push_back(r[0].text + "|" + r[1].text + suffix(r[2]));
        else
            out.push_back(r[0].text);
    }
    return out;
}

// Insert txt-format lines. For decisions/tasks/decisions_backup the
// line's id is preserved when present (rewrite paths); an empty id
// means "let SERIAL assign" (new tasks). Returns false on the first
// bad line or SQL error (bad lines are never silently dropped).
inline bool insertLines(const std::string& table,
                        const std::vector<std::string>& lines) {
    std::string err;
    for (const auto& line : lines) {
        auto parts = splitPipeField(line);
        bool ok = false;
        // Strict integer check: stoi() alone would accept "1x".
        auto strictInt = [](const std::string& s) {
            if (s.empty()) return false;
            std::size_t i = (s[0] == '-') ? 1 : 0;
            if (i >= s.size()) return false;
            for (; i < s.size(); ++i)
                if (s[i] < '0' || s[i] > '9') return false;
            return true;
        };
        if (table == "decisions" || table == "decisions_backup") {
            if (parts.size() < 5) return false;
            if (!strictInt(parts[3])) return false;
            std::string owner = parts.size() >= 6 ? parts[5] : "";
            if (parts[0].empty()) {
                if (owner.empty())
                    ok = pgstore::pgExec(
                        "INSERT INTO " + table +
                            " (record_date, type, priority, title, owner) "
                            "VALUES ($1,$2,$3,$4,NULL)",
                        {parts[1], pgSanitize(parts[2]), parts[3],
                         pgSanitize(parts[4])},
                        err);
                else
                    ok = pgstore::pgExec(
                        "INSERT INTO " + table +
                            " (record_date, type, priority, title, owner) "
                            "VALUES ($1,$2,$3,$4,$5)",
                        {parts[1], pgSanitize(parts[2]), parts[3],
                         pgSanitize(parts[4]), owner},
                        err);
            } else {
                if (!strictInt(parts[0])) return false;
                if (owner.empty())
                    ok = pgstore::pgExec(
                        "INSERT INTO " + table +
                            " (id, record_date, type, priority, title, "
                            "owner) VALUES ($1,$2,$3,$4,$5,NULL)",
                        {parts[0], parts[1], pgSanitize(parts[2]), parts[3],
                         pgSanitize(parts[4])},
                        err);
                else
                    ok = pgstore::pgExec(
                        "INSERT INTO " + table +
                            " (id, record_date, type, priority, title, "
                            "owner) VALUES ($1,$2,$3,$4,$5,$6)",
                        {parts[0], parts[1], pgSanitize(parts[2]), parts[3],
                         pgSanitize(parts[4]), owner},
                        err);
            }
        } else if (table == "tasks") {
            if (parts.size() < 6) return false;
            if (!strictInt(parts[2]) || !strictInt(parts[3])) return false;
            std::string owner = parts.size() >= 7 ? parts[6] : "";
            if (parts[0].empty()) {
                if (owner.empty())
                    ok = pgstore::pgExec(
                        "INSERT INTO tasks (title, urgency, importance, "
                        "deadline, status, owner) VALUES ($1,$2,$3,$4,$5,"
                        "NULL)",
                        {pgSanitize(parts[1]), parts[2], parts[3],
                         pgSanitize(parts[4]), pgSanitize(parts[5])},
                        err);
                else
                    ok = pgstore::pgExec(
                        "INSERT INTO tasks (title, urgency, importance, "
                        "deadline, status, owner) VALUES ($1,$2,$3,$4,$5,"
                        "$6)",
                        {pgSanitize(parts[1]), parts[2], parts[3],
                         pgSanitize(parts[4]), pgSanitize(parts[5]), owner},
                        err);
            } else {
                if (!strictInt(parts[0])) return false;
                if (owner.empty())
                    ok = pgstore::pgExec(
                        "INSERT INTO tasks (id, title, urgency, "
                        "importance, deadline, status, owner) VALUES "
                        "($1,$2,$3,$4,$5,$6,NULL)",
                        {parts[0], pgSanitize(parts[1]), parts[2], parts[3],
                         pgSanitize(parts[4]), pgSanitize(parts[5])},
                        err);
                else
                    ok = pgstore::pgExec(
                        "INSERT INTO tasks (id, title, urgency, "
                        "importance, deadline, status, owner) VALUES "
                        "($1,$2,$3,$4,$5,$6,$7)",
                        {parts[0], pgSanitize(parts[1]), parts[2], parts[3],
                         pgSanitize(parts[4]), pgSanitize(parts[5]), owner},
                        err);
            }
        } else if (table == "transactions") {
            if (parts.size() < 5) return false;
            double amt;
            try {
                amt = std::stod(parts[3]);
            } catch (...) {
                return false;
            }
            std::string owner = parts.size() >= 6 ? parts[5] : "";
            if (owner.empty())
                ok = pgstore::pgExec(
                    "INSERT INTO transactions (tx_date, type, category, "
                    "amount, note, owner) VALUES ($1,$2,$3,$4,$5,NULL)",
                    {parts[0], pgSanitize(parts[1]), pgSanitize(parts[2]),
                     fmtNum(amt), pgSanitize(parts[4])},
                    err);
            else
                ok = pgstore::pgExec(
                    "INSERT INTO transactions (tx_date, type, category, "
                    "amount, note, owner) VALUES ($1,$2,$3,$4,$5,$6)",
                    {parts[0], pgSanitize(parts[1]), pgSanitize(parts[2]),
                     fmtNum(amt), pgSanitize(parts[4]), owner},
                    err);
        } else if (table == "savings_goals") {
            if (parts.size() < 3) return false;
            double tgt, svd;
            try {
                tgt = std::stod(parts[1]);
                svd = std::stod(parts[2]);
            } catch (...) {
                return false;
            }
            std::string owner = parts.size() >= 4 ? parts[3] : "";
            if (owner.empty())
                ok = pgstore::pgExec(
                    "INSERT INTO savings_goals (name, target, saved, "
                    "owner) VALUES ($1,$2,$3,NULL)",
                    {pgSanitize(parts[0]), fmtNum(tgt), fmtNum(svd)}, err);
            else
                ok = pgstore::pgExec(
                    "INSERT INTO savings_goals (name, target, saved, "
                    "owner) VALUES ($1,$2,$3,$4)",
                    {pgSanitize(parts[0]), fmtNum(tgt), fmtNum(svd), owner},
                    err);
        } else if (table == "habit_log") {
            if (parts.size() < 2) return false;
            std::string owner = parts.size() >= 3 ? parts[2] : "";
            if (owner.empty())
                ok = pgstore::pgExec(
                    "INSERT INTO habit_log (habit, log_date, owner) VALUES "
                    "($1,$2,NULL)",
                    {pgSanitize(parts[0]), parts[1]}, err);
            else
                ok = pgstore::pgExec(
                    "INSERT INTO habit_log (habit, log_date, owner) VALUES "
                    "($1,$2,$3)",
                    {pgSanitize(parts[0]), parts[1], owner}, err);
        } else if (table == "daily_reports") {
            ok = pgstore::pgExec(
                "INSERT INTO daily_reports (line) VALUES ($1)", {line}, err);
        } else if (table == "error_logs") {
            ok = pgstore::pgExec("INSERT INTO error_logs (line) VALUES ($1)",
                                 {line}, err);
        } else {
            return false;
        }
        if (!ok) return false;
    }
    return true;
}

// Delete every row visible to the current user (own rows, plus
// legacy NULL-owner rows when the current user is the sole user).
// Other users' rows and hidden legacy rows are untouched. Only for
// tables with an owner column.
inline bool deleteVisible(const std::string& table) {
    if (table != "decisions" && table != "decisions_backup" &&
        table != "tasks" && table != "transactions" &&
        table != "savings_goals" && table != "habit_log")
        return false;
    std::string err;
    if (!pgstore::pgExec("DELETE FROM " + table + " WHERE owner = $1",
                         {g_currentUser}, err))
        return false;
    if (isSoleUser()) {
        if (!pgstore::pgExec("DELETE FROM " + table + " WHERE owner IS NULL",
                             {}, err))
            return false;
    }
    return true;
}

// Delete one visible row by id. `deleted` reports whether a row was
// actually removed (false = no such visible id, same as the txt
// "not found" path). Returns false only on a SQL error.
inline bool deleteById(const std::string& table, const std::string& id,
                       bool& deleted) {
    deleted = false;
    if (table != "decisions" && table != "decisions_backup" &&
        table != "tasks")
        return false;
    // Strict integer check: a non-numeric id simply matches nothing.
    if (id.empty()) return true;
    for (char c : id)
        if (c < '0' || c > '9') return true;
    std::vector<pgstore::Row> rows;
    std::string err;
    std::string sql;
    if (isSoleUser())
        sql = "DELETE FROM " + table +
              " WHERE id = $1 AND (owner = $2 OR owner IS NULL) "
              "RETURNING id";
    else
        sql = "DELETE FROM " + table +
              " WHERE id = $1 AND owner = $2 RETURNING id";
    if (!pgstore::pgQuery(sql, {id, g_currentUser}, rows, err)) return false;
    deleted = !rows.empty();
    return true;
}

// Replace the current user's visible rows with the given lines, in
// one transaction (like the server's saveTasks). The SERIAL sequence
// is moved ahead of preserved ids afterwards, like the server.
inline bool rewriteVisible(const std::string& table,
                           const std::vector<std::string>& lines) {
    std::string err;
    if (!beginTx()) return false;
    if (!deleteVisible(table)) {
        rollbackTx();
        return false;
    }
    if (!insertLines(table, lines)) {
        rollbackTx();
        return false;
    }
    if (table == "decisions" || table == "tasks") {
        std::string seq = table + "_id_seq";
        if (!pgstore::pgExec(
                "SELECT setval('" + seq + "', COALESCE((SELECT MAX(id) FROM " +
                    table + "), 1))",
                {}, err)) {
            rollbackTx();
            return false;
        }
    }
    if (!commitTx()) return false;
    return true;
}

// --- structured appends (no id in the line; SERIAL assigns) -------

// Console decisions carry record_date "-" (the console's own
// convention, same as txt mode) — not the server's todayStr().
inline bool appendDecision(const std::string& type, int priority,
                           const std::string& title) {
    std::string err;
    return pgstore::pgExec(
        "INSERT INTO decisions (record_date, type, priority, title, owner) "
        "VALUES ('-', $1, $2, $3, $4)",
        {pgSanitize(type), std::to_string(priority), pgSanitize(title),
         g_currentUser},
        err);
}

inline bool appendTask(const std::string& title, int urgency, int importance,
                       const std::string& deadline,
                       const std::string& status) {
    std::string err;
    return pgstore::pgExec(
        "INSERT INTO tasks (title, urgency, importance, deadline, status, "
        "owner) VALUES ($1,$2,$3,$4,$5,$6)",
        {pgSanitize(title), std::to_string(urgency),
         std::to_string(importance), pgSanitize(deadline),
         pgSanitize(status), g_currentUser},
        err);
}

inline bool appendTransaction(const std::string& date, const std::string& type,
                              const std::string& category, double amount,
                              const std::string& note) {
    std::string err;
    return pgstore::pgExec(
        "INSERT INTO transactions (tx_date, type, category, amount, note, "
        "owner) VALUES ($1,$2,$3,$4,$5,$6)",
        {date, pgSanitize(type), pgSanitize(category), fmtNum(amount),
         pgSanitize(note), g_currentUser},
        err);
}

// False when a goal with this name already exists for this user
// (the UNIQUE index on (name, owner)) or on any other SQL error.
inline bool appendSavingsGoal(const std::string& name, double target) {
    std::string err;
    return pgstore::pgExec(
        "INSERT INTO savings_goals (name, target, saved, owner) VALUES "
        "($1,$2,0,$3)",
        {pgSanitize(name), fmtNum(target), g_currentUser}, err);
}

inline bool appendHabit(const std::string& habit, const std::string& date) {
    std::string err;
    return pgstore::pgExec(
        "INSERT INTO habit_log (habit, log_date, owner) VALUES ($1,$2,$3)",
        {pgSanitize(habit), date, g_currentUser}, err);
}

// Free-text single-line tables (daily_reports, error_logs).
inline bool appendFreeLine(const std::string& table, const std::string& line) {
    if (table != "daily_reports" && table != "error_logs") return false;
    std::string err;
    return pgstore::pgExec("INSERT INTO " + table + " (line) VALUES ($1)",
                           {line}, err);
}

}  // namespace console_pg

#endif
