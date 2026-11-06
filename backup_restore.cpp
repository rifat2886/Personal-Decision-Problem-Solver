#include "backup_restore.h"
#include "data_owner.h"
#include "error_handler.h"
#include "file_lock.h"
#include <iostream>
#include <fstream>
#include <string>
#include <vector>

using namespace std;

void backupDecisions()
{
    // FIX (final audit): check the source
    // BEFORE opening the backup. The old order created/truncated
    // decisions_backup.txt even when the source was missing, so a
    // later restore could wipe decisions.txt with an empty backup.
    FileLock lock("decisions.txt");
    ifstream source("decisions.txt");

    if (!source)
    {
        cout << "No decision file found to back up.\n";
        // FIX (backend final testing): logError() was defined but
        // never called anywhere, so Show Error Log (option 33)
        // could never show a real failure. Log file-open failures.
        logError("backupDecisions: decisions.txt not found");
        return;
    }

    // Per-user backup (public-launch redesign, 2026-11-05): the old
    // code truncated decisions_backup.txt and wrote only the
    // caller's rows, destroying other users' backups. Now the
    // existing backup rows that are NOT visible to the current user
    // are kept verbatim, and only the caller's visible rows are
    // replaced with their current decisions. Format unchanged.
    vector<string> keptBackup;
    {
        ifstream oldBackup("decisions_backup.txt");
        string oldLine;
        while (getline(oldBackup, oldLine))
            if (!lineVisibleFor(oldLine, 5)) keptBackup.push_back(oldLine);
    }
    vector<string> myLines;
    string line;
    while (getline(source, line))
        if (lineVisibleFor(line, 5)) myLines.push_back(line);

    ofstream backup("decisions_backup.txt");

    if (!backup)
    {
        cout << "Could not create backup file.\n";
        logError("backupDecisions: could not create decisions_backup.txt");
        return;
    }

    for (auto& kept : keptBackup) backup << kept << '\n';
    for (auto& mine : myLines) backup << mine << '\n';

    cout << "Backup created successfully!\n";
}

void restoreDecisions()
{
    ifstream backup("decisions_backup.txt");

    if (!backup)
    {
        cout << "No backup file found.\n";
        logError("restoreDecisions: decisions_backup.txt not found");
        return;
    }

    cout << "Restoring will replace decisions.txt.\n";
    cout << "Continue? (y/n): ";

    char choice = 'n';
    if (!(cin >> choice)) {
        cin.clear();
        cin.ignore(10000, '\n');
        cout << "Restore cancelled.\n";
        return;
    }

    if (choice != 'y' && choice != 'Y')
    {
        cout << "Restore cancelled.\n";
        return;
    }

    // Restore only the current user's records; preserve others.
    // Read BOTH files BEFORE opening the destination: the old code
    // opened decisions.txt for writing first, which truncated it,
    // so the "kept" read always found an empty file and a restore
    // wiped every other user's decisions. Also refuse a restore
    // when the current user has no backup rows at all, instead of
    // deleting their current decisions with an empty restore.
    vector<string> kept;
    {
        ifstream current("decisions.txt");
        string cur;
        while (getline(current, cur)) {
            if (!lineVisibleFor(cur, 5)) kept.push_back(cur);
        }
    }
    vector<string> myBackup;
    {
        string line;
        while (getline(backup, line))
            if (lineVisibleFor(line, 5)) myBackup.push_back(line);
    }
    if (myBackup.empty())
    {
        cout << "No backup found for this user. Nothing was changed.\n";
        return;
    }

    FileLock lock("decisions.txt");
    ofstream destination("decisions.txt");

    if (!destination)
    {
        cout << "Could not open decision file.\n";
        logError("restoreDecisions: could not open decisions.txt");
        return;
    }

    for (auto& ln : kept) destination << ln << '\n';
    for (auto& ln : myBackup) destination << ln << '\n';

    cout << "Decisions restored successfully!\n";
}
