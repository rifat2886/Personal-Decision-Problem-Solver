
#include "budget.h"
#include <iostream>
#include <iomanip>
using namespace std;

void budgetDecision() {
    double income, expenses;

    cout << "\n===== BUDGET DECISION =====\n";
    cout << "Enter monthly income: ";
    cin >> income;

    cout << "Enter monthly expenses: ";
    cin >> expenses;

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
    int n;
    double amount, income = 0, expenses = 0;
    char type;

    cout << "\n===== INCOME & EXPENSE TRACKING =====\n";
    cout << "How many transactions? ";
    cin >> n;

    if (n <= 0 || n > 100) {
        cout << "Enter a number from 1 to 100.\n";
        return;
    }

    for (int i = 1; i <= n; i++) {
        cout << "\nTransaction " << i << '\n';
        cout << "Enter I for income or E for expense: ";
        cin >> type;

        cout << "Enter amount: ";
        cin >> amount;

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
    double target, current, monthlySaving;

    cout << "\n===== SAVINGS GOAL =====\n";
    cout << "Enter savings target: ";
    cin >> target;

    cout << "Current savings: ";
    cin >> current;

    cout << "Expected monthly saving: ";
    cin >> monthlySaving;

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
