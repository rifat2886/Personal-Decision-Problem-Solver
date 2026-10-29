#include "history.h"
#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <algorithm>
using namespace std;

const string HISTORY_FILE = "decision_history.txt";
const string BACKUP_FILE = "decision_backup.txt";

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
        cout << ++count << ". " << line << '\n';
    }

    if (count == 0) {
        cout << "History is empty.\n";
    }

    writeLog("Decision history viewed.");
}

// Extra: Search History
void searchHistory() {
    string keyword, line;
    bool found = false;

    cout << "Enter keyword (one word): ";
    cin >> keyword;

    ifstream file(HISTORY_FILE);

    if (!file) {
        cout << "No history file found.\n";
        writeLog("History search failed.");
        return;
    }

    while (getline(file, line)) {
        if (line.find(keyword) != string::npos) {
            cout << line << '\n';
            found = true;
        }
    }

    if (!found) {
        cout << "No matching record found.\n";
    }

    writeLog("History search completed.");
}

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
        records.push_back(line);
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

    backup << source.rdbuf();

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

    ofstream destination(HISTORY_FILE);

    if (!destination) {
        cout << "Could not restore history.\n";
        return;
    }

    destination << backup.rdbuf();

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

    ofstream file(HISTORY_FILE, ios::trunc);

    if (file) {
        cout << "History deleted successfully.\n";
        writeLog("History deleted.");
    }
    else {
        cout << "Could not delete history.\n";
        writeLog("Error deleting history.");
    }
}
