
#include "report.h"
#include <iostream>
#include <fstream>
#include <iomanip>
using namespace std;


void generateReport() {
    double income, expenses;
    int habitsCompleted, habitsPlanned;

    cout << "\n===== DAILY SUMMARY REPORT =====\n";

    cout << "Enter total income: ";
    cin >> income;

    cout << "Enter total expenses: ";
    cin >> expenses;

    cout << "Habits completed today: ";
    cin >> habitsCompleted;

    cout << "Habits planned today: ";
    cin >> habitsPlanned;

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

    ofstream file("daily_report.txt", ios::app);

    if (!file) {
        cout << "Could not save the report.\n";
        return;
    }

    file << fixed << setprecision(2);
    file << "Income: " << income
         << ", Expenses: " << expenses
         << ", Balance: " << balance
         << ", Habit completion: " << habitRate << "%\n";

    file.close();

    cout << "Report saved to daily_report.txt\n";
}
