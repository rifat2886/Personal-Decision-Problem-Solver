#ifndef TASK_STORE_H
#define TASK_STORE_H

// Persistent task storage, shared by the console app and the dashboard.
//
// Format (exactly the dashboard's tasks.txt format, plus owner):
//   id|title|urgency|importance|deadline|status|owner
// Records without an owner are legacy records (see data_owner.h).
// Titles, deadlines and statuses are sanitised so a user-supplied '|'
// cannot break the format. Corrupted lines (fewer than 6 fields, or a
// non-numeric urgency/importance) are skipped, not fatal.
//
// Why this file exists: the console task modules used to keep tasks
// only in the in-memory taskList, so Task Status (13) and Deadline
// Alert (14) only worked if Task Prioritization (11) had run in the
// same session, and dashboard tasks were invisible to the console.
// Now Task Prioritization appends to tasks.txt, and Task Status and
// Deadline Alert load tasks.txt first, so both interfaces see the
// same tasks. No existing user data is lost: tasks.txt already
// created by the dashboard is read as-is, and in-memory-only tasks
// from old sessions were already lost on exit, so there is nothing
// to migrate.

#include "file_lock.h"
#include "data_owner.h"
#include "task_data.h"

#include <fstream>
#include <string>
#include <vector>

namespace pdps_tasks {

inline std::string sanitizeField(const std::string& s) {
    std::string out = s;
    for (char& c : out)
        if (c == '|' || c == '\n' || c == '\r') c = '/';
    return out;
}

inline std::vector<std::string> splitPipe(const std::string& line) {
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

// Load only the current user's tasks from tasks.txt (empty if the
// file does not exist). Also fills the shared in-memory taskList.
// Other users' and legacy records are NOT returned here, so callers
// cannot see them; saveTasks() preserves them on disk (see below).
inline std::vector<Task> loadTasks() {
    FileLock lock("tasks.txt");
    std::vector<Task> tasks;
    std::ifstream input("tasks.txt");
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        auto parts = splitPipe(line);
        if (parts.size() < 6) continue;
        Task t;
        t.id = parts[0];
        t.title = parts[1];
        try {
            t.urgency = std::stoi(parts[2]);
            t.importance = std::stoi(parts[3]);
        } catch (...) {
            continue;
        }
        if (t.urgency < 1 || t.urgency > 10 || t.importance < 1 ||
            t.importance > 10)
            continue;
        t.deadline = parts[4];
        t.status = parts[5];
        t.owner = parts.size() >= 7 ? parts[6] : "";
        if (!ownerVisibleFor(t.owner)) continue;
        tasks.push_back(t);
    }
    taskList = tasks;
    return tasks;
}

// Rewrite tasks.txt with the given (current user's) tasks, preserving
// ids where set and assigning new sequential ids where empty, AND
// preserving every other user's and legacy line verbatim on disk.
// Held under the lock.
inline void saveTasks(const std::vector<Task>& tasks) {
    FileLock lock("tasks.txt");
    std::vector<std::string> kept;
    {
        std::ifstream input("tasks.txt");
        std::string line;
        while (std::getline(input, line)) {
            if (line.empty()) continue;
            auto parts = splitPipe(line);
            if (parts.size() < 6) { kept.push_back(line); continue; }
            std::string owner = parts.size() >= 7 ? parts[6] : "";
            if (!ownerVisibleFor(owner)) kept.push_back(line);
        }
    }
    std::ofstream output("tasks.txt");
    if (!output) return;
    for (auto& ln : kept) output << ln << '\n';
    int nextId = 1;
    for (auto& ln : kept) {
        auto parts = splitPipe(ln);
        if (!parts.empty()) { try { int v = std::stoi(parts[0]); if (v >= nextId) nextId = v + 1; } catch (...) {} }
    }
    for (const auto& t : tasks) {
        std::string id = t.id;
        if (id.empty()) {
            id = std::to_string(nextId);
        } else {
            try {
                int v = std::stoi(id);
                if (v >= nextId) nextId = v + 1;
            } catch (...) {
                id = std::to_string(nextId);
            }
        }
        std::string owner = t.owner.empty() ? g_currentUser : t.owner;
        output << id << '|' << sanitizeField(t.title) << '|'
               << t.urgency << '|' << t.importance << '|'
               << sanitizeField(t.deadline) << '|'
               << sanitizeField(t.status) << '|' << owner << '\n';
        try {
            int v = std::stoi(id);
            if (v >= nextId) nextId = v + 1;
        } catch (...) {
        }
    }
}

// Append new tasks to tasks.txt, allocating fresh ids after the
// highest existing id. Used by Task Prioritization.
inline void appendTasks(const std::vector<Task>& newTasks) {
    FileLock lock("tasks.txt");
    std::vector<Task> existing;
    {
        std::ifstream input("tasks.txt");
        std::string line;
        while (std::getline(input, line)) {
            if (line.empty()) continue;
            auto parts = splitPipe(line);
            if (parts.size() < 6) continue;
            Task t;
            t.id = parts[0];
            t.title = parts[1];
            try {
                t.urgency = std::stoi(parts[2]);
                t.importance = std::stoi(parts[3]);
            } catch (...) {
                continue;
            }
            t.deadline = parts[4];
            t.status = parts[5];
            existing.push_back(t);
        }
    }
    int nextId = 1;
    for (const auto& t : existing) {
        try {
            int v = std::stoi(t.id);
            if (v >= nextId) nextId = v + 1;
        } catch (...) {
        }
    }
    std::ofstream output("tasks.txt", std::ios::app);
    if (!output) return;
    for (const auto& t : newTasks) {
        output << nextId++ << '|' << sanitizeField(t.title) << '|'
               << t.urgency << '|' << t.importance << '|'
               << sanitizeField(t.deadline) << '|'
               << sanitizeField(t.status) << '|' << g_currentUser << '\n';
    }
}

}  // namespace pdps_tasks

#endif
