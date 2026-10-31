#include "backup_restore.h"
#include <iostream>
#include <fstream>
#include <string>

using namespace std;

void backupDecisions()
{
    ifstream source("decisions.txt");
    ofstream backup("decisions_backup.txt");

    if (!source)
    {
        cout << "No decision file found to back up.\n";
        return;
    }

    if (!backup)
    {
        cout << "Could not create backup file.\n";
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
        return;
    }

    cout << "Restoring will replace decisions.txt.\n";
    cout << "Continue? (y/n): ";

    char choice;
    cin >> choice;

    if (choice != 'y' && choice != 'Y')
    {
        cout << "Restore cancelled.\n";
        return;
    }

    ofstream destination("decisions.txt");

    if (!destination)
    {
        cout << "Could not open decision file.\n";
        return;
    }

    string line;

    while (getline(backup, line))
        destination << line << '\n';

    cout << "Decisions restored successfully!\n";
}
