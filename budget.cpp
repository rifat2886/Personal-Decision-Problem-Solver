#include "budget.h"
#include <iostream>
#include <iomanip>
#include <limits>
using namespace std;

// Reads a double safely: on non-numeric input the stream is cleared
// and the bad input discarded, instead of leaving the variable
// uninitialised (the old code read with plain cin >> and then used
// the value unconditionally).
static bool readDouble(double& value)
{
    if (cin >> value)
        return true;
    cout << "Invalid amount!\n";
    cin.clear();
    cin.ignore(numeric_limits<streamsize>::max(), '\n');
    return false;
}

void budgetDecision() {
    double income = 0, expenses = 0;

    cout << "\n===== BUDGET DECISION =====\n";
    cout << "Enter monthly income: ";
    if (!readDouble(income))
        return;

    cout << "Enter monthly expenses: ";
    if (!readDouble(expenses))
        return;

    if (income < 0 || expenses < 0) {
        cout << "Invalid amount!\n";
        return;
    }

    double savings = income - expenses;

    cout << fixed << setprecision(2);
    cout << "Remaining balance: " << savings << " Tk\n";

    if (savings < 0)
        cout << "Decision: Reduce expenses.\n";
    else if (savings == 0)
        cout << "Decision: Income equals expenses.\n";
    else
        cout << "Decision: Save money for the future.\n";
}


void incomeExpenseTracking() {
    int n = 0;
    double amount = 0, income = 0, expenses = 0;
    char type = 0;

    cout << "\n===== INCOME & EXPENSE TRACKING =====\n";
    cout << "How many transactions? ";
    if (!(cin >> n)) {
        cout << "Invalid number!\n";
        cin.clear();
        cin.ignore(numeric_limits<streamsize>::max(), '\n');
        return;
    }

    if (n <= 0 || n > 100) {
        cout << "Enter a number from 1 to 100.\n";
        return;
    }

    for (int i = 1; i <= n; i++) {
        cout << "\nTransaction " << i << '\n';
        cout << "Enter I for income or E for expense: ";
        cin >> type;

        cout << "Enter amount: ";
        if (!(cin >> amount)) {
            // FIX (final audit): on end-of-file, abort
            // instead of retrying forever, as the old code did.
            if (cin.eof()) {
                cout << "Input closed. Aborting tracking.\n";
                return;
            }
            cout << "Invalid amount. Try again.\n";
            cin.clear();
            cin.ignore(numeric_limits<streamsize>::max(), '\n');
            i--;
            continue;
        }

        if (amount < 0 ||
            (type != 'I' && type != 'i' &&
             type != 'E' && type != 'e')) {
            cout << "Invalid input. Try again.\n";
            i--;
            continue;
        }

        if (type == 'I' || type == 'i')
            income += amount;
        else
            expenses += amount;
    }

    cout << fixed << setprecision(2);
    cout << "Total Income: " << income << " Tk\n";
    cout << "Total Expense: " << expenses << " Tk\n";
    cout << "Balance: " << income - expenses << " Tk\n";
}


void savingsGoal() {
    double target = 0, current = 0, monthlySaving = 0;

    cout << "\n===== SAVINGS GOAL =====\n";
    cout << "Enter savings target: ";
    if (!readDouble(target))
        return;

    cout << "Current savings: ";
    if (!readDouble(current))
        return;

    cout << "Expected monthly saving: ";
    if (!readDouble(monthlySaving))
        return;

    if (target <= 0 || current < 0 || monthlySaving <= 0) {
        cout << "Invalid input!\n";
        return;
    }

    if (current >= target) {
        cout << "Congratulations! Your goal is complete.\n";
        return;
    }

    double remaining = target - current;
    int months = static_cast<int>(
        (remaining + monthlySaving - 0.01) / monthlySaving
    );

    cout << fixed << setprecision(2);
    cout << "Amount remaining: " << remaining << " Tk\n";
    cout << "Estimated time: " << months << " month(s)\n";
}
