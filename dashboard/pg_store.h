// pg_store.h — PostgreSQL connection helpers for the C++ server.
//
// Route 2, Phase 1. This header is intentionally generic: it knows
// nothing about decisions, tasks, or any PDPS record type. The
// server (cpp_server.cpp) maps query rows onto its own structs.
//
// Compilation:
//  - If <libpq-fe.h> is available (Linux, and the Render Dockerfile
//    which installs libpq-dev), Postgres mode is compiled in.
//  - If it is not available (for example a Windows/MinGW build
//    without libpq), Postgres mode is compiled OUT: pgIsEnabled()
//    is false, pgInit() fails with a clear message, and the server
//    still builds and runs in its original txt mode. This keeps the
//    Windows build working without a new dependency.
//  - PDPS_NO_LIBPQ (set by the Makefile / .bat launchers when
//    pg_config is missing) forces Postgres support OUT even when
//    the headers exist: otherwise the headers compile the real code
//    in but -lpq is never linked and the build fails with
//    "undefined reference to PQconnectdb" (same mismatch as
//    libcurl, fixed the same way 2026-11-09).
//  - No connection string, password, or secret is in this file.
//    The connection string comes only from the DATABASE_URL
//    environment variable at runtime, and is never logged.
//
// Threading: the server creates one thread per HTTP connection and
// serialises all API handling with g_apiMutex, so a single PGconn
// shared by pgQuery() is safe in this server. Do NOT use this header
// from a multi-threaded caller without the same serialisation.

#ifndef PDPS_PG_STORE_H
#define PDPS_PG_STORE_H

#include <string>
#include <vector>

namespace pgstore {

struct Value {
    bool isNull = true;
    std::string text;
};
using Row = std::vector<Value>;

// True only when libpq was available at compile time AND pgInit()
// succeeded. All server code must check this before any pg call.
bool pgIsEnabled();

// Connect with conninfo (a libpq connection string, normally the
// DATABASE_URL value) and create the schema if it does not exist.
// On failure returns false and sets err; the caller must NOT fall
// back to txt mode when DATABASE_URL was set, because that would
// silently serve a different, empty data set. Fail fast instead.
bool pgInit(const std::string& conninfo, std::string& err);

// Run a query with $1, $2, ... parameters (never interpolate user
// data into SQL text). On success returns true; rows holds the
// result rows for SELECT / INSERT ... RETURNING, and is empty for
// plain INSERT / UPDATE / DELETE / DDL. On failure returns false
// and sets err to the server's error message.
bool pgQuery(const std::string& sql, const std::vector<std::string>& params,
             std::vector<Row>& rows, std::string& err);

// Convenience for statements that return no rows.
bool pgExec(const std::string& sql, const std::vector<std::string>& params,
            std::string& err);

void pgShutdown();

}  // namespace pgstore

// ------------------------------------------------------------------
// Implementation. Keep it in this header so cpp_server.cpp needs no
// new .cpp file in the Makefile's 35-file console list and no new
// build step beyond -lpq (see Dockerfile; txt builds link without
// libpq because the libpq calls below are compiled out).
// ------------------------------------------------------------------
#if !defined(PDPS_NO_LIBPQ) && defined(__has_include)
#if __has_include(<libpq-fe.h>)
#define PDPS_HAS_LIBPQ 1
#include <libpq-fe.h>
#endif
#endif

namespace pgstore {

#ifdef PDPS_HAS_LIBPQ
namespace detail {
inline PGconn* g_conn = nullptr;
inline bool g_enabled = false;

inline const char* schemaSql() {
    return
        "CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT, role TEXT NOT NULL CHECK (role IN ('ADMIN','USER')), email TEXT, google_sub TEXT, auth_provider TEXT NOT NULL DEFAULT 'password' CHECK (auth_provider IN ('password','google','both')), display_name TEXT);"
        "CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (email) WHERE email IS NOT NULL;"
        "CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_unique ON users (google_sub) WHERE google_sub IS NOT NULL;"
        "CREATE TABLE IF NOT EXISTS decisions (id SERIAL PRIMARY KEY, record_date TEXT NOT NULL, type TEXT NOT NULL, priority INTEGER NOT NULL, title TEXT NOT NULL, owner TEXT);"
        "CREATE TABLE IF NOT EXISTS decisions_backup (id INTEGER PRIMARY KEY, record_date TEXT NOT NULL, type TEXT NOT NULL, priority INTEGER NOT NULL, title TEXT NOT NULL, owner TEXT);"
        "CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, title TEXT NOT NULL, urgency INTEGER NOT NULL, importance INTEGER NOT NULL, deadline TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, owner TEXT);"
        "CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, tx_date TEXT NOT NULL, type TEXT NOT NULL, category TEXT NOT NULL, amount NUMERIC NOT NULL, note TEXT NOT NULL DEFAULT '', owner TEXT);"
        "CREATE TABLE IF NOT EXISTS savings_goals (id SERIAL PRIMARY KEY, name TEXT NOT NULL, target NUMERIC NOT NULL, saved NUMERIC NOT NULL DEFAULT 0, owner TEXT);"
        "CREATE UNIQUE INDEX IF NOT EXISTS savings_goals_name_owner_idx ON savings_goals (name, (COALESCE(owner, '')));"
        "CREATE TABLE IF NOT EXISTS habit_log (id SERIAL PRIMARY KEY, habit TEXT NOT NULL, log_date TEXT NOT NULL, owner TEXT);"
        "CREATE TABLE IF NOT EXISTS daily_reports (id SERIAL PRIMARY KEY, line TEXT NOT NULL);"
        "CREATE TABLE IF NOT EXISTS error_logs (id SERIAL PRIMARY KEY, line TEXT NOT NULL);"
        "CREATE TABLE IF NOT EXISTS ai_history (id SERIAL PRIMARY KEY, owner TEXT NOT NULL, feature TEXT NOT NULL, prompt TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL);";
}
}  // namespace detail

inline bool pgIsEnabled() { return detail::g_enabled; }

inline bool pgInit(const std::string& conninfo, std::string& err) {
    detail::g_conn = PQconnectdb(conninfo.c_str());
    if (PQstatus(detail::g_conn) != CONNECTION_OK) {
        err = PQerrorMessage(detail::g_conn);
        PQfinish(detail::g_conn);
        detail::g_conn = nullptr;
        return false;
    }
    PGresult* res = PQexec(detail::g_conn, detail::schemaSql());
    if (PQresultStatus(res) != PGRES_COMMAND_OK) {
        err = PQerrorMessage(detail::g_conn);
        PQclear(res);
        PQfinish(detail::g_conn);
        detail::g_conn = nullptr;
        return false;
    }
    PQclear(res);
    detail::g_enabled = true;
    return true;
}

inline bool pgQuery(const std::string& sql, const std::vector<std::string>& params,
                    std::vector<Row>& rows, std::string& err) {
    rows.clear();
    if (!detail::g_conn) { err = "Postgres connection is not initialised."; return false; }
    std::vector<const char*> values;
    values.reserve(params.size());
    for (const auto& p : params) values.push_back(p.c_str());
    PGresult* res = PQexecParams(detail::g_conn, sql.c_str(), (int)params.size(),
                                 nullptr, values.empty() ? nullptr : values.data(),
                                 nullptr, nullptr, 0);
    ExecStatusType st = PQresultStatus(res);
    if (st != PGRES_TUPLES_OK && st != PGRES_COMMAND_OK) {
        err = PQerrorMessage(detail::g_conn);
        PQclear(res);
        return false;
    }
    int nrows = PQntuples(res);
    int ncols = PQnfields(res);
    for (int r = 0; r < nrows; r++) {
        Row row;
        for (int c = 0; c < ncols; c++) {
            Value v;
            v.isNull = PQgetisnull(res, r, c) != 0;
            v.text = v.isNull ? "" : PQgetvalue(res, r, c);
            row.push_back(v);
        }
        rows.push_back(row);
    }
    PQclear(res);
    return true;
}

inline bool pgExec(const std::string& sql, const std::vector<std::string>& params,
                   std::string& err) {
    std::vector<Row> rows;
    return pgQuery(sql, params, rows, err);
}

inline void pgShutdown() {
    if (detail::g_conn) { PQfinish(detail::g_conn); detail::g_conn = nullptr; }
    detail::g_enabled = false;
}

#else  // no libpq at compile time

inline bool pgIsEnabled() { return false; }
inline bool pgInit(const std::string&, std::string& err) {
    err = "Postgres support was not compiled in: libpq-fe.h was not available at build time. Build with libpq-dev (see Dockerfile) or run without DATABASE_URL for txt mode.";
    return false;
}
inline bool pgQuery(const std::string&, const std::vector<std::string>&,
                    std::vector<Row>&, std::string& err) {
    err = "Postgres support was not compiled in.";
    return false;
}
inline bool pgExec(const std::string&, const std::vector<std::string>&,
                   std::string& err) {
    err = "Postgres support was not compiled in.";
    return false;
}
inline void pgShutdown() {}

#endif  // PDPS_HAS_LIBPQ

}  // namespace pgstore

#endif  // PDPS_PG_STORE_H
