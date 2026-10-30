#include "search_history.h"
#include <iostream>
#include <fstream>
#include <string>

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

    ifstream file("decisions.txt");

    if (!file)
    {
        cout << "No decision history found.\n";
        return;
    }

    while (getline(file, line))
    {
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
