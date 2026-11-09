#include "filter_sort.h"
#include "console_pg.h"
#include "data_owner.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <algorithm>

using namespace std;

struct DecisionRecord
{
    string id;
    string date;
    string type;
    int priority;
    string title;
};

vector<DecisionRecord> loadDecisions()
{
    vector<DecisionRecord> records;

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
        std::string l;
        while (std::getline(file, l)) lines.push_back(l);
    }

    for (const auto& line : lines)
    {
        if (console_pg::pgMode()) {
            if (!console_pg::lineVisible(line, 5)) continue;
        } else if (!lineVisibleFor(line, 5)) continue;
        stringstream ss(line);
        DecisionRecord d;
        string priorityText;

        if (!getline(ss, d.id, '|') ||
            !getline(ss, d.date, '|') ||
            !getline(ss, d.type, '|') ||
            !getline(ss, priorityText, '|') ||
            !getline(ss, d.title))
        {
            continue;
        }

        try
        {
            d.priority = stoi(priorityText);
            // Strip owner field from title if present.
            size_t sep = d.title.find('|');
            if (sep != string::npos) d.title = d.title.substr(0, sep);
            records.push_back(d);
        }
        catch (...)
        {
            continue;
        }
    }

    return records;
}

void filterDecisions()
{
    vector<DecisionRecord> records = loadDecisions();
    string keyword;
    bool found = false;

    cout << "\nEnter type to filter: ";
    getline(cin >> ws, keyword);

    for (const auto& d : records)
    {
        if (d.type.find(keyword) != string::npos)
        {
            cout << d.id << " | "
                 << d.date << " | "
                 << d.type << " | "
                 << d.priority << " | "
                 << d.title << '\n';

            found = true;
        }
    }

    if (!found)
        cout << "No matching decisions found.\n";
}

void sortDecisions()
{
    vector<DecisionRecord> records = loadDecisions();

    if (records.empty())
    {
        cout << "No decisions available to sort.\n";
        return;
    }

    sort(records.begin(), records.end(),
         [](const DecisionRecord& a, const DecisionRecord& b)
         {
             return a.priority > b.priority;
         });

    cout << "\n--- Decisions Sorted by Priority ---\n";

    for (const auto& d : records)
    {
        cout << d.id << " | "
             << d.date << " | "
             << d.type << " | "
             << d.priority << " | "
             << d.title << '\n';
    }
}
