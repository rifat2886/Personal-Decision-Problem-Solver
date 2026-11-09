#include "error_handler.h"
#include "console_pg.h"
#include <iostream>
#include <fstream>
#include <string>
#include <vector>

using namespace std;

void logError(const string& message)
{
    // Phase 4, Batch B: Postgres mode appends to the shared
    // error_logs table.
    if (console_pg::pgMode())
    {
        if (!console_pg::appendFreeLine("error_logs", message))
            cout << "Could not write to error log.\n";
        return;
    }

    ofstream file("error_log.txt", ios::app);

    if (!file)
    {
        cout << "Could not write to error log.\n";
        return;
    }

    file << message << '\n';
}

void showErrorLog()
{
    cout << "\n--- Error Log ---\n";

    // Phase 4, Batch B: Postgres mode reads the shared table.
    if (console_pg::pgMode())
    {
        for (const auto& line : console_pg::readLines("error_logs"))
            cout << line << '\n';
        return;
    }

    ifstream file("error_log.txt");
    string line;

    if (!file)
    {
        cout << "No error log found.\n";
        return;
    }

    while (getline(file, line))
        cout << line << '\n';
}
