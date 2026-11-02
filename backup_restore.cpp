#include "backup_restore.h"
#include "error_handler.h"
#include "file_lock.h"
#include <iostream>
#include <fstream>
#include <string>

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

    ofstream backup("decisions_backup.txt");

    if (!backup)
    {
        cout << "Could not create backup file.\n";
        logError("backupDecisions: could not create decisions_backup.txt");
        return;
    }

    string line;

    while (getline(source, line))
        backup << line << '\n';

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

    FileLock lock("decisions.txt");
    ofstream destination("decisions.txt");

    if (!destination)
    {
        cout << "Could not open decision file.\n";
        logError("restoreDecisions: could not open decisions.txt");
        return;
    }

    string line;

    while (getline(backup, line))
        destination << line << '\n';

    cout << "Decisions restored successfully!\n";
}
