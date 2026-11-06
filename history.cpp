#include "history.h"
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
    ifstream file(HISTORY_FILE);

    cout << "\n===== DECISION HISTORY =====\n";

    if (!file) {
        cout << "No history found.\n";
        return;
    }

    string line;
    int count = 0;

    while (getline(file, line)) {
        if (!lineVisibleFor(line, 5)) continue;
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
    ifstream file(HISTORY_FILE);
    vector<string> records;
    string line, keyword;

    if (!file) {
        cout << "No history file found.\n";
        return;
    }

    while (getline(file, line)) {
        if (lineVisibleFor(line, 5)) records.push_back(line);
    }
    file.close();

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
