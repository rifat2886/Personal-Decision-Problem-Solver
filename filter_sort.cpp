#include "filter_sort.h"
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
    ifstream file("decisions.txt");
    string line;

    while (getline(file, line))
    {
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
