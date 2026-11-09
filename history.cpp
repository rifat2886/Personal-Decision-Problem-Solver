#include "history.h"
#include "console_pg.h"
#include "data_owner.h"
#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <algorithm>
using namespace std;

// Unified with the rest of the menu (search/filter/sort/backup/
// restore/delete in main.cpp options 28-32), which all use
// decisions.txt / decisions_backup.txt. Previously this module used
// decision_history.txt, a file no menu module wrote to.
const string HISTORY_FILE = "decisions.txt";
const string BACKUP_FILE = "decisions_backup.txt";

// Extra: System Log
void writeLog(const string& message) {
    ofstream log("system_log.txt", ios::app);

    if (log) {
        log << message << '\n';
    }
}

// Feature 10: Decision History
void decisionHistory() {
    cout << "\n===== DECISION HISTORY =====\n";

    // Phase 4, Batch B: load the lines from the shared table in
    // Postgres mode, or from decisions.txt as before.
    std::vector<std::string> lines;
    if (console_pg::pgMode())
    {
        lines = console_pg::readLines("decisions");
    }
    else
    {
        std::ifstream file(HISTORY_FILE);
        if (!file) {
            cout << "No history found.\n";
            return;
        }
        std::string l;
        while (std::getline(file, l)) lines.push_back(l);
    }

    string line;
    int count = 0;

    for (const auto& l : lines) {
        line = l;
        if (console_pg::pgMode()) {
            if (!console_pg::lineVisible(line, 5)) continue;
        } else if (!lineVisibleFor(line, 5)) continue;
        cout << ++count << ". " << line << '\n';
    }

    if (count == 0) {
        cout << "History is empty.\n";
    }

    writeLog("Decision history viewed.");
}

// NOTE: searchHistory() is intentionally NOT defined here.
// It is defined once, in search_history.cpp, and declared in both
// search_history.h and history.h. Defining it here as well was the
// multiple-definition link error that broke the whole build.
// The control panel (control.cpp) calls the search_history.cpp
// version, which searches the same decisions.txt file.
// Extra: Filter and Sort
void filterSortHistory() {
    // Phase 4, Batch B: load the lines from the shared table in
    // Postgres mode, or from decisions.txt as before.
    std::vector<std::string> lines;
    if (console_pg::pgMode())
    {
        lines = console_pg::readLines("decisions");
    }
    else
    {
        std::ifstream file(HISTORY_FILE);
        if (!file) {
            cout << "No history file found.\n";
            return;
        }
        std::string l;
        while (std::getline(file, l)) lines.push_back(l);
    }

    vector<string> records;
    string line, keyword;

    for (const auto& l : lines) {
        line = l;
        if (console_pg::pgMode()) {
            if (console_pg::lineVisible(line, 5)) records.push_back(line);
        } else if (lineVisibleFor(line, 5)) records.push_back(line);
    }

    cout << "Enter keyword or * for all records: ";
    cin >> keyword;

    vector<string> filtered;

    for (const string& record : records) {
        if (keyword == "*" ||
            record.find(keyword) != string::npos) {
            filtered.push_back(record);
        }
    }

    if (filtered.empty()) {
        cout << "No matching records.\n";
        return;
    }

    sort(filtered.begin(), filtered.end());

    cout << "\n===== FILTERED & SORTED HISTORY =====\n";

    for (size_t i = 0; i < filtered.size(); i++) {
        cout << i + 1 << ". " << filtered[i] << '\n';
    }

    writeLog("History filtered and sorted.");
}

// Extra: Backup
void backupHistory() {
    // Phase 4, Batch B: Postgres mode replaces only the caller's
    // backup rows in the shared decisions_backup table, keeping
    // other users' backup rows (same per-user rule as txt mode).
    if (console_pg::pgMode()) {
        std::vector<std::string> myLines;
        for (const auto& line : console_pg::readLines("decisions"))
            if (console_pg::lineVisible(line, 5)) myLines.push_back(line);
        if (!console_pg::beginTx() ||
            !console_pg::deleteVisible("decisions_backup") ||
            !console_pg::insertLines("decisions_backup", myLines) ||
            !console_pg::commitTx()) {
            console_pg::rollbackTx();
            cout << "Could not create backup.\n";
            return;
        }
        cout << "Backup created successfully.\n";
        writeLog("History backup created.");
        return;
    }

    ifstream source(HISTORY_FILE);

    if (!source) {
        cout << "No history available for backup.\n";
        return;
    }

    ofstream backup(BACKUP_FILE);

    if (!backup) {
        cout << "Could not create backup.\n";
        return;
    }

    string line;
    while (getline(source, line)) {
        if (lineVisibleFor(line, 5)) backup << line << '\n';
    }

    cout << "Backup created successfully.\n";
    writeLog("History backup created.");
}

// Extra: Restore
void restoreHistory() {
    // Phase 4, Batch B: Postgres mode restores only the current
    // user's backup rows into the shared decisions table.
    if (console_pg::pgMode()) {
        char confirm;

        cout << "Replace current history with backup? (y/n): ";
        cin >> confirm;

        if (confirm != 'y' && confirm != 'Y') {
            cout << "Restore cancelled.\n";
            return;
        }

        std::vector<std::string> myBackup;
        for (const auto& line : console_pg::readLines("decisions_backup"))
            if (console_pg::lineVisible(line, 5)) myBackup.push_back(line);
        if (myBackup.empty())
        {
            cout << "No backup found for this user. Nothing was changed.\n";
            return;
        }
        if (!console_pg::rewriteVisible("decisions", myBackup))
        {
            cout << "Could not restore history.\n";
            return;
        }
        cout << "History restored successfully.\n";
        writeLog("History restored.");
        return;
    }

    ifstream backup(BACKUP_FILE);

    if (!backup) {
        cout << "No backup file found.\n";
        return;
    }

    char confirm;

    cout << "Replace current history with backup? (y/n): ";
    cin >> confirm;

    if (confirm != 'y' && confirm != 'Y') {
        cout << "Restore cancelled.\n";
        return;
    }

    // Restore only the current user's records; preserve other
    // users' and legacy records already in the history file.
    vector<string> kept;
    {
        ifstream current(HISTORY_FILE);
        string cur;
        while (getline(current, cur)) {
            if (!lineVisibleFor(cur, 5)) kept.push_back(cur);
        }
    }
    ofstream destination(HISTORY_FILE);

    if (!destination) {
        cout << "Could not restore history.\n";
        return;
    }

    for (auto& ln : kept) destination << ln << '\n';
    string line;
    while (getline(backup, line)) {
        if (lineVisibleFor(line, 5)) destination << line << '\n';
    }

    cout << "History restored successfully.\n";
    writeLog("History restored.");
}

// Extra: Delete Confirmation
void deleteHistory() {
    char confirm;

    cout << "Delete all history? (y/n): ";
    cin >> confirm;

    if (confirm != 'y' && confirm != 'Y') {
        cout << "Deletion cancelled.\n";
        return;
    }

    // Phase 4, Batch B: Postgres mode deletes only the current
    // user's rows from the shared decisions table.
    if (console_pg::pgMode()) {
        if (!console_pg::deleteVisible("decisions")) {
            cout << "Could not delete history.\n";
            writeLog("Error deleting history.");
            return;
        }
        cout << "History deleted successfully.\n";
        writeLog("History deleted.");
        return;
    }

    // Delete only the current user's records; preserve others.
    vector<string> kept;
    {
        ifstream current(HISTORY_FILE);
        string cur;
        while (getline(current, cur)) {
            if (!lineVisibleFor(cur, 5)) kept.push_back(cur);
        }
    }
    ofstream file(HISTORY_FILE, ios::trunc);

    if (file) {
        for (auto& ln : kept) file << ln << '\n';
        cout << "History deleted successfully.\n";
        writeLog("History deleted.");
    }
    else {
        cout << "Could not delete history.\n";
        writeLog("Error deleting history.");
    }
}
