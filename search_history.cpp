#include "search_history.h"
#include "console_pg.h"
#include "data_owner.h"
#include <iostream>
#include <fstream>
#include <string>
#include <vector>

using namespace std;

void saveSearchHistory(const string& query)
{
    ofstream file("search_history.txt", ios::app);

    if (file)
        file << query << '\n';
}

void searchHistory()
{
    string query, line;
    bool found = false;

    cout << "\nEnter keyword to search: ";
    getline(cin >> ws, query);

    // Phase 4, Batch B: load the lines from the shared table in
    // Postgres mode, or from decisions.txt as before.
    std::vector<std::string> lines;
    if (console_pg::pgMode())
    {
        lines = console_pg::readLines("decisions");
    }
    else
    {
        std::ifstream file("decisions.txt");
        if (!file)
        {
            cout << "No decision history found.\n";
            return;
        }
        std::string l;
        while (std::getline(file, l)) lines.push_back(l);
    }

    for (const auto& l : lines)
    {
        line = l;
        if (console_pg::pgMode()) {
            if (!console_pg::lineVisible(line, 5)) continue;
        } else if (!lineVisibleFor(line, 5)) continue;
        if (line.find(query) != string::npos)
        {
            cout << line << '\n';
            found = true;
        }
    }

    if (!found)
        cout << "No matching records found.\n";

    saveSearchHistory(query);
}
