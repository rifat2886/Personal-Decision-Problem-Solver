#include "income_expense.h"
#include "console_pg.h"
#include "file_lock.h"
#include "data_owner.h"
#include <iostream>
#include <string>
#include <fstream>
#include <iomanip>
#include <limits>

using namespace std;

const string TRANSACTION_FILE = "transactions.txt";

void addTransaction()
{
    string date, type, category, note;
    double amount;

    cout << "\n--- Add Income or Expense ---\n";

    cout << "Enter date (YYYY-MM-DD): ";
    cin >> date;

    if (date.size() != 10 || date[4] != '-' || date[7] != '-')
    {
        cout << "Invalid date format! Use YYYY-MM-DD.\n";
        return;
    }

    cout << "Type (income/expense): ";
    cin >> type;

    if (type != "income" && type != "expense")
    {
        cout << "Invalid type!\n";
        return;
    }

    cin.ignore(numeric_limits<streamsize>::max(), '\n');

    cout << "Enter category: ";
    getline(cin, category);

    cout << "Enter amount: ";

    if (!(cin >> amount) || amount <= 0)
    {
        cout << "Invalid amount!\n";
        cin.clear();
        cin.ignore(numeric_limits<streamsize>::max(), '\n');
        return;
    }

    cin.ignore(numeric_limits<streamsize>::max(), '\n');

    cout << "Enter note: ";
    getline(cin, note);

    // Phase 4, Batch B: Postgres mode inserts into the shared
    // transactions table.
    if (console_pg::pgMode())
    {
        console_pg::appendTransaction(date, type, category, amount, note);
        cout << "Transaction saved successfully!\n";
        return;
    }

    FileLock lock(TRANSACTION_FILE);
    ofstream file(TRANSACTION_FILE, ios::app);

    if (!file)
    {
        cout << "Could not open transaction file!\n";
        return;
    }

    file << date << "|" << type << "|" << category
         << "|" << amount << "|" << note << "|" << g_currentUser << "\n";

    file.close();

    cout << "Transaction saved successfully!\n";
}

void showTransactions()
{
    cout << "\n--- Transaction History ---\n";

    // Phase 4, Batch B: Postgres mode reads the shared table.
    if (console_pg::pgMode())
    {
        for (const auto& line : console_pg::readLines("transactions"))
        {
            if (!console_pg::lineVisible(line, 5)) continue;
            cout << line << '\n';
        }
        return;
    }

    ifstream file(TRANSACTION_FILE);
    string line;

    if (!file)
    {
        cout << "No transaction records found.\n";
        return;
    }

    while (getline(file, line))
    {
        if (!lineVisibleFor(line, 5)) continue;
        cout << line << '\n';
    }

    file.close();
}

void showBalance()
{
    // Phase 4, Batch B: load the lines from the shared table in
    // Postgres mode, or from transactions.txt as before. The
    // summing body below is identical for both.
    std::vector<std::string> lines;
    if (console_pg::pgMode())
    {
        lines = console_pg::readLines("transactions");
    }
    else
    {
        std::ifstream file(TRANSACTION_FILE);
        std::string l;
        while (std::getline(file, l)) lines.push_back(l);
    }

    double income = 0, expense = 0;

    for (const auto& line : lines)
    {
        if (console_pg::pgMode()) {
            if (!console_pg::lineVisible(line, 5)) continue;
        } else if (!lineVisibleFor(line, 5)) continue;
        // date|type|category|amount|note
        size_t p1 = line.find('|');
        if (p1 == string::npos) continue;
        size_t p2 = line.find('|', p1 + 1);
        if (p2 == string::npos) continue;
        size_t p3 = line.find('|', p2 + 1);
        if (p3 == string::npos) continue;
        size_t p4 = line.find('|', p3 + 1);
        if (p4 == string::npos) continue;
        string type = line.substr(p1 + 1, p2 - p1 - 1);
        try {
            double amount = stod(line.substr(p3 + 1, p4 - p3 - 1));
            if (type == "income") income += amount;
            else if (type == "expense") expense += amount;
        } catch (...) {
            continue;
        }
    }

    cout << fixed << setprecision(2);
    cout << "\nTotal Income: " << income << '\n';
    cout << "Total Expense: " << expense << '\n';
    cout << "Current Balance: " << income - expense << '\n';
}
