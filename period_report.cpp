#include "period_report.h"
#include "data_owner.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <string>

using namespace std;

// Days since 1970-01-01 for a civil date (Howard Hinnant's algorithm).
// Used only to test whether a transaction falls in a 7-day window.
static bool daysFromCivil(int y, int m, int d, long long& out)
{
    if (m < 1 || m > 12 || d < 1 || d > 31)
        return false;
    y -= (m <= 2);
    long long era = (y >= 0 ? y : y - 399) / 400;
    unsigned yoe = static_cast<unsigned>(y - era * 400);
    unsigned mp = static_cast<unsigned>((m + 9) % 12);
    unsigned doy = (153 * mp + 2) / 5 + static_cast<unsigned>(d - 1);
    unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    out = era * 146097 + static_cast<long long>(doe) - 719468;
    return true;
}

static bool parseDate(const string& date, long long& days)
{
    if (date.size() != 10 || date[4] != '-' || date[7] != '-')
        return false;
    try
    {
        int y = stoi(date.substr(0, 4));
        int m = stoi(date.substr(5, 2));
        int d = stoi(date.substr(8, 2));
        return daysFromCivil(y, m, d, days);
    }
    catch (...)
    {
        return false;
    }
}

void showReportByPeriod(bool monthly)
{
    ifstream file("transactions.txt");

    if (!file)
    {
        cout << "No transaction records found.\n";
        return;
    }

    // Previously this function totalled ALL transactions for both
    // weekly and monthly reports. Now it actually filters by date.
    string month;
    long long weekEnd = 0;
    if (monthly)
    {
        cout << "Enter month (YYYY-MM): ";
        cin >> month;
        if (month.size() != 7 || month[4] != '-')
        {
            cout << "Invalid month format! Use YYYY-MM.\n";
            return;
        }
    }
    else
    {
        string endDate;
        cout << "Enter week end date (YYYY-MM-DD): ";
        cin >> endDate;
        if (!parseDate(endDate, weekEnd))
        {
            cout << "Invalid date format! Use YYYY-MM-DD.\n";
            return;
        }
    }

    string line, date, type, category, amountText;
    double income = 0, expense = 0;
    int matched = 0;

    while (getline(file, line))
    {
        if (!lineVisibleFor(line, 5)) continue;
        stringstream ss(line);

        if (!getline(ss, date, '|') ||
            !getline(ss, type, '|') ||
            !getline(ss, category, '|') ||
            !getline(ss, amountText, '|'))
            continue;

        if (monthly)
        {
            if (date.size() < 7 || date.substr(0, 7) != month)
                continue;
        }
        else
        {
            long long days = 0;
            if (!parseDate(date, days))
                continue;
            if (days < weekEnd - 6 || days > weekEnd)
                continue;
        }

        try
        {
            double amount = stod(amountText);
            if (type == "income")
                income += amount;
            else if (type == "expense")
                expense += amount;
            else
                continue;
            ++matched;
        }
        catch (...)
        {
            continue;
        }
    }

    cout << fixed << setprecision(2);
    cout << (monthly ? "\n--- Monthly Report ---\n"
                     : "\n--- Weekly Report ---\n");
    if (monthly)
        cout << "Month: " << month << '\n';
    cout << "Matching transactions: " << matched << '\n';
    cout << "Total Income: " << income << '\n';
    cout << "Total Expense: " << expense << '\n';
    cout << "Balance: " << income - expense << '\n';
}

void showWeeklyReport()
{
    showReportByPeriod(false);
}

void showMonthlyReport()
{
    showReportByPeriod(true);
}
