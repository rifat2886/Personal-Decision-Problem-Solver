#include "period_report.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <iomanip>

using namespace std;

void showReportByPeriod(bool monthly)
{
    ifstream file("transactions.txt");

    string line, date, type, category, amountText, note;
    double income = 0, expense = 0;

    if (!file)
    {
        cout << "No transaction records found.\n";
        return;
    }

    while (getline(file, line))
    {
        stringstream ss(line);

        if (!getline(ss, date, '|') ||
            !getline(ss, type, '|') ||
            !getline(ss, category, '|') ||
            !getline(ss, amountText, '|'))
            continue;

        try
        {
            double amount = stod(amountText);

            // Monthly report groups by YYYY-MM.
            // Weekly report here is a simple recent-record approximation
            // only if the date is stored correctly; it does not calculate
            // the exact last seven days.
            if (monthly)
            {
                if (date.size() < 7)
                    continue;

                // Report the month entered in the latest matching record.
                // This can be improved by asking the user for a month.
            }

            if (type == "income")
                income += amount;
            else if (type == "expense")
                expense += amount;
        }
        catch (...)
        {
            continue;
        }
    }

    cout << fixed << setprecision(2);
    cout << (monthly ? "\n--- Monthly Report ---\n"
                     : "\n--- Weekly Report ---\n");
    cout << "Total Income: " << income << '\n';
    cout << "Total Expense: " << expense << '\n';
    cout << "Balance: " << income - expense << '\n';
    cout << "Note: This version totals all saved transactions; "
            "it does not yet filter dates.\n";
}

void showWeeklyReport()
{
    showReportByPeriod(false);
}

void showMonthlyReport()
{
    showReportByPeriod(true);
}
