#ifndef DATA_OWNER_H
#define DATA_OWNER_H

// Per-user data isolation for the console app (Issue 2).
// Every personal record carries an owner as the LAST pipe field.
// Records written before this change have no owner field; they are
// "legacy" records and are NEVER deleted or silently assigned.
// A legacy record is visible only when users.txt contains exactly
// one user and that user is the current user (the only possible
// owner); with two or more users, legacy records are hidden from
// every regular user and preserved verbatim on disk. ADMIN does
// NOT get access to other users' records.
//
// The current user is set by main.cpp at login and cleared at
// logout. Personal menus are login-guarded (Issue 3), so data
// modules only run with a current user set.

#include <fstream>
#include <sstream>
#include <string>
#include <vector>

inline std::string g_currentUser;

inline void setCurrentUser(const std::string& user) { g_currentUser = user; }
inline void clearCurrentUser() { g_currentUser.clear(); }
inline std::string currentUser() { return g_currentUser; }

inline std::vector<std::string> splitPipeField(const std::string& line) {
    std::vector<std::string> parts;
    std::size_t start = 0;
    while (true) {
        std::size_t pos = line.find('|', start);
        if (pos == std::string::npos) {
            parts.push_back(line.substr(start));
            break;
        }
        parts.push_back(line.substr(start, pos - start));
        start = pos + 1;
    }
    return parts;
}

// Owner of a record line: last field when the line has more than
// expectedFields fields, otherwise "" (legacy).
inline std::string ownerOfLine(const std::string& line, std::size_t expectedFields) {
    auto parts = splitPipeField(line);
    if (parts.size() > expectedFields) return parts.back();
    return "";
}

inline bool ownerVisibleFor(const std::string& owner) {
    if (owner == g_currentUser) return true;
    if (!owner.empty()) return false;
    // Legacy: visible only to the sole user in users.txt.
    std::ifstream input("users.txt");
    std::string line, sole;
    std::size_t count = 0;
    while (std::getline(input, line)) {
        std::istringstream is(line);
        std::string u;
        if (is >> u) { sole = u; ++count; }
    }
    return count == 1 && sole == g_currentUser;
}

inline bool lineVisibleFor(const std::string& line, std::size_t expectedFields) {
    return ownerVisibleFor(ownerOfLine(line, expectedFields));
}

#endif
