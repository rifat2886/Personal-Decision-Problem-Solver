#include "delete_confirmation.h"
#include <iostream>
#include <fstream>
#include <string>

using namespace std;

void confirmDelete(const string& id)
{
    cout << "Are you sure you want to delete decision "
         << id << "? (y/n): ";

    char choice;
    cin >> choice;

    if (choice != 'y' && choice != 'Y')
    {
        cout << "Delete cancelled.\n";
        return;
    }

    ifstream source("decisions.txt");

    if (!source)
    {
        cout << "Decision file not found.\n";
        return;
    }

    ofstream temp("decisions_temp.txt");

    if (!temp)
    {
        cout << "Could not create temporary file.\n";
        return;
    }

    string line;
    bool found = false;

    while (getline(source, line))
    {
        size_t separator = line.find('|');

        if (separator != string::npos &&
            line.substr(0, separator) == id)
        {
            found = true;
            continue;
        }

        temp << line << '\n';
    }

    source.close();
    temp.close();

    if (!found)
    {
        remove("decisions_temp.txt");
        cout << "Decision ID not found.\n";
        return;
    }

    // Rename the original first so it can be restored if needed.
    if (rename("decisions.txt", "decisions_old.txt") != 0)
    {
        remove("decisions_temp.txt");
        cout << "Could not prepare decision file for update.\n";
        return;
    }

    if (rename("decisions_temp.txt", "decisions.txt") != 0)
    {
        rename("decisions_old.txt", "decisions.txt");
        cout << "Could not update decision file.\n";
        return;
    }

    remove("decisions_old.txt");

    cout << "Decision deleted successfully.\n";
}
