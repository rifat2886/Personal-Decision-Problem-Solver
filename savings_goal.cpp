#include "savings_goal.h"
#include <iostream>
#include <fstream>
#include <iomanip>
#include <limits>

using namespace std;

const string SAVINGS_FILE = "savings_goals.txt";

void addSavingsGoal()
{
    string name;
    double target;

    cin.ignore(numeric_limits<streamsize>::max(), '\n');

    cout << "\nEnter savings goal name: ";
    getline(cin, name);

    cout << "Enter target amount: ";

    if (!(cin >> target) || target <= 0)
    {
        cout << "Invalid target amount!\n";
        cin.clear();
        cin.ignore(numeric_limits<streamsize>::max(), '\n');
        return;
    }

    ofstream file(SAVINGS_FILE, ios::app);

    if (!file)
    {
        cout << "Could not open savings file!\n";
        return;
    }

    file << name << "|" << target << "|0\n";
    cout << "Savings goal added successfully!\n";
}

void addSavingsAmount()
{
    string name, line, goalName;
    double target, saved, amount;
    bool found = false;

    cout << "\nEnter goal name: ";
    cin.ignore(numeric_limits<streamsize>::max(), '\n');
    getline(cin, name);

    cout << "Enter amount to save: ";

    if (!(cin >> amount) || amount <= 0)
    {
        cout << "Invalid amount!\n";
        cin.clear();
        cin.ignore(numeric_limits<streamsize>::max(), '\n');
        return;
    }

    ifstream inFile(SAVINGS_FILE);
    ofstream outFile("savings_temp.txt");

    if (!inFile || !outFile)
    {
        cout << "Could not open savings files!\n";
        return;
    }

    while (getline(inFile, line))
    {
        size_t first = line.find('|');
        size_t second = line.find('|', first + 1);

        if (first == string::npos || second == string::npos)
        {
            outFile << line << '\n';
            continue;
        }

        goalName = line.substr(0, first);
        target = stod(line.substr(first + 1, second - first - 1));
        saved = stod(line.substr(second + 1));

        if (goalName == name)
        {
            saved += amount;
            found = true;
        }

        outFile << goalName << "|" << target << "|" << saved << '\n';
    }

    inFile.close();
    outFile.close();

    if (found)
    {
        remove(SAVINGS_FILE.c_str());
        rename("savings_temp.txt", SAVINGS_FILE.c_str());
        cout << "Savings amount updated!\n";
    }
    else
    {
        remove("savings_temp.txt");
        cout << "Goal not found!\n";
    }
}

void showSavingsGoals()
{
    ifstream file(SAVINGS_FILE);
    string name;
    double target, saved;

    cout << "\n--- Savings Goals ---\n";

    if (!file)
    {
        cout << "No savings goals found.\n";
        return;
    }

    cout << fixed << setprecision(2);

    while (getline(file, name, '|'))
    {
        if (!(file >> target))
            break;

        file.ignore(numeric_limits<streamsize>::max(), '|');

        if (!(file >> saved))
            break;

        file.ignore(numeric_limits<streamsize>::max(), '\n');

        cout << "Goal: " << name
             << " | Target: " << target
             << " | Saved: " << saved
             << " | Remaining: " << target - saved << '\n';
    }
}
