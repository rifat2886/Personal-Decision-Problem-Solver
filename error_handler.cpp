#include "error_handler.h"
#include <iostream>
#include <fstream>
#include <string>

using namespace std;

void logError(const string& message)
{
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
    ifstream file("error_log.txt");
    string line;

    cout << "\n--- Error Log ---\n";

    if (!file)
    {
        cout << "No error log found.\n";
        return;
    }

    while (getline(file, line))
        cout << line << '\n';
}
