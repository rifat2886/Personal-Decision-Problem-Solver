#include "savings_goal.h"
#include "console_pg.h"
#include "file_lock.h"
#include "data_owner.h"
#include <iostream>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <vector>

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

    // Phase 4, Batch B: Postgres mode inserts into the shared
    // savings_goals table. A goal with this name already exists for
    // this user when the UNIQUE index rejects the insert (txt mode
    // allowed duplicate names; the shared table does not).
    if (console_pg::pgMode())
    {
        if (!console_pg::appendSavingsGoal(name, target))
        {
            cout << "Could not save the savings goal. A goal with "
                    "this name may already exist.\n";
            return;
        }
        cout << "Savings goal added successfully!\n";
        return;
    }

    FileLock lock(SAVINGS_FILE);
    ofstream file(SAVINGS_FILE, ios::app);

    if (!file)
    {
        cout << "Could not open savings file!\n";
        return;
    }

    file << name << "|" << target << "|0|" << g_currentUser << "\n";
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

    // Phase 4, Batch B: Postgres mode loads the caller's visible
    // goals, adds the amount to every matching one (same as the txt
    // temp-file rewrite), and writes them back in one transaction.
    if (console_pg::pgMode())
    {
        std::vector<std::string> updated;
        bool found = false;
        for (const auto& line : console_pg::readLines("savings_goals"))
        {
            if (!console_pg::lineVisible(line, 3)) continue;
            size_t first = line.find('|');
            size_t second = line.find('|', first + 1);
            size_t third = (second == string::npos)
                               ? string::npos
                               : line.find('|', second + 1);
            if (first == string::npos || second == string::npos) continue;
            std::string goalName = line.substr(0, first);
            std::string owner =
                (third == string::npos) ? "" : line.substr(third + 1);
            double goalTarget, goalSaved;
            try {
                goalTarget = stod(line.substr(first + 1, second - first - 1));
                goalSaved = stod(line.substr(
                    second + 1, (third == string::npos
                                     ? string::npos
                                     : third - second - 1)));
            } catch (...) {
                continue;
            }
            if (goalName == name)
            {
                goalSaved += amount;
                found = true;
            }
            std::ostringstream rebuilt;
            rebuilt << goalName << "|" << goalTarget << "|" << goalSaved
                    << "|" << (owner.empty() ? g_currentUser : owner);
            updated.push_back(rebuilt.str());
        }
        if (!found)
        {
            cout << "Goal not found!\n";
            return;
        }
        if (!console_pg::rewriteVisible("savings_goals", updated))
        {
            cout << "Could not update savings.\n";
            return;
        }
        cout << "Savings amount updated!\n";
        return;
    }

    // Hold the savings lock for the whole read-modify-write, so a
    // dashboard savings-add cannot read the same old value and
    // overwrite this update (the classic lost-update race).
    FileLock lock(SAVINGS_FILE);
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
        size_t third = (second == string::npos) ? string::npos : line.find('|', second + 1);

        if (first == string::npos || second == string::npos)
        {
            outFile << line << '\n';
            continue;
        }

        goalName = line.substr(0, first);
        string owner = (third == string::npos) ? "" : line.substr(third + 1);
        // Other users' and legacy (multi-user) records are preserved
        // verbatim and never modified here.
        if (!ownerVisibleFor(owner))
        {
            outFile << line << '\n';
            continue;
        }
        try {
            target = stod(line.substr(first + 1, second - first - 1));
            saved = stod(line.substr(second + 1, (third == string::npos ? string::npos : third - second - 1)));
        } catch (...) {
            // Preserve a malformed line instead of crashing.
            outFile << line << '\n';
            continue;
        }

        if (goalName == name)
        {
            saved += amount;
            found = true;
        }

        outFile << goalName << "|" << target << "|" << saved << "|" << (owner.empty() ? g_currentUser : owner) << '\n';
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
    cout << "\n--- Savings Goals ---\n";

    // Phase 4, Batch B: load the lines from the shared table in
    // Postgres mode, or from savings_goals.txt as before.
    std::vector<std::string> lines;
    if (console_pg::pgMode())
    {
        lines = console_pg::readLines("savings_goals");
    }
    else
    {
        std::ifstream file(SAVINGS_FILE);
        if (!file)
        {
            cout << "No savings goals found.\n";
            return;
        }
        std::string l;
        while (std::getline(file, l)) lines.push_back(l);
    }

    cout << fixed << setprecision(2);

    string name;
    double target, saved;

    // Parse line by line. The old getline(name, '|') version treated
    // a malformed line with no '|' as the start of the next line
    // (getline with a non-newline delimiter does not stop at '\n'),
    // so one bad line hid every goal after it.
    string line;
    for (const auto& l : lines)
    {
        line = l;
        if (console_pg::pgMode()) {
            if (!console_pg::lineVisible(line, 3)) continue;
        } else if (!lineVisibleFor(line, 3)) continue;
        size_t first = line.find('|');
        if (first == string::npos)
            continue;
        size_t second = line.find('|', first + 1);
        if (second == string::npos)
            continue;
        try
        {
            name = line.substr(0, first);
            target = stod(line.substr(first + 1, second - first - 1));
            saved = stod(line.substr(second + 1));
        }
        catch (...)
        {
            continue;
        }

        cout << "Goal: " << name
             << " | Target: " << target
             << " | Saved: " << saved
             << " | Remaining: " << target - saved << '\n';
    }
}
