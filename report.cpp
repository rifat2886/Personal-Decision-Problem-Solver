#include "report.h"
#include "console_pg.h"
#include "data_owner.h"
#include "file_lock.h"
#include <iostream>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <limits>
using namespace std;

static bool readDouble(double& value)
{
    if (cin >> value)
        return true;
    cout << "Invalid input!\n";
    cin.clear();
    cin.ignore(numeric_limits<streamsize>::max(), '\n');
    return false;
}

static bool readInt(int& value)
{
    if (cin >> value)
        return true;
    cout << "Invalid input!\n";
    cin.clear();
    cin.ignore(numeric_limits<streamsize>::max(), '\n');
    return false;
}

void generateReport() {
    double income = 0, expenses = 0;
    int habitsCompleted = 0, habitsPlanned = 0;

    cout << "\n===== DAILY SUMMARY REPORT =====\n";

    cout << "Enter total income: ";
    if (!readDouble(income))
        return;

    cout << "Enter total expenses: ";
    if (!readDouble(expenses))
        return;

    cout << "Habits completed today: ";
    if (!readInt(habitsCompleted))
        return;

    cout << "Habits planned today: ";
    if (!readInt(habitsPlanned))
        return;

    if (income < 0 || expenses < 0 ||
        habitsCompleted < 0 || habitsPlanned <= 0 ||
        habitsCompleted > habitsPlanned) {
        cout << "Invalid input!\n";
        return;
    }

    double balance = income - expenses;
    double habitRate = habitsCompleted * 100.0 / habitsPlanned;

    cout << fixed << setprecision(2);
    cout << "\n----- DAILY REPORT -----\n";
    cout << "Income: " << income << " Tk\n";
    cout << "Expenses: " << expenses << " Tk\n";
    cout << "Balance: " << balance << " Tk\n";
    cout << "Habit completion: " << habitRate << "%\n";

    // Phase 4, Batch B: Postgres mode appends the report line to
    // the shared daily_reports table.
    if (console_pg::pgMode())
    {
        std::ostringstream line;
        line << std::fixed << std::setprecision(2);
        line << "User: " << g_currentUser
             << ", Income: " << income
             << ", Expenses: " << expenses
             << ", Balance: " << balance
             << ", Habit completion: " << habitRate << "%";
        if (!console_pg::appendFreeLine("daily_reports", line.str()))
        {
            cout << "Could not save the report.\n";
            return;
        }
        cout << "Report saved to the database.\n";
        return;
    }

    FileLock lock("daily_report.txt");
    ofstream file("daily_report.txt", ios::app);

    if (!file) {
        cout << "Could not save the report.\n";
        return;
    }

    file << fixed << setprecision(2);
    file << "User: " << g_currentUser
         << ", Income: " << income
         << ", Expenses: " << expenses
         << ", Balance: " << balance
         << ", Habit completion: " << habitRate << "%\n";

    file.close();

    cout << "Report saved to daily_report.txt\n";
}
