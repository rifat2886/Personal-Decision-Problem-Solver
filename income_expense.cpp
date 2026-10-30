#include "income_expense.h"
#include <iostream>
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

    ofstream file(TRANSACTION_FILE, ios::app);

    if (!file)
    {
        cout << "Could not open transaction file!\n";
        return;
    }

    file << date << "|" << type << "|" << category
         << "|" << amount << "|" << note << "\n";

    file.close();

    cout << "Transaction saved successfully!\n";
}

void showTransactions()
{
    ifstream file(TRANSACTION_FILE);
    string line;

    cout << "\n--- Transaction History ---\n";

    if (!file)
    {
        cout << "No transaction records found.\n";
        return;
    }

    while (getline(file, line))
    {
        cout << line << '\n';
    }

    file.close();
}

void showBalance()
{
    ifstream file(TRANSACTION_FILE);

    string date, type, category, note;
    double amount;
    double income = 0, expense = 0;

    while (file >> date)
    {
        if (!getline(file, type, '|'))
            break;

        if (!getline(file, category, '|'))
            break;

        if (!(file >> amount))
            break;

        file.ignore(numeric_limits<streamsize>::max(), '|');

        if (!getline(file, note))
            note = "";

        // Remove the first '|' remaining before type.
        if (!type.empty() && type[0] == '|')
            type.erase(0, 1);

        if (type == "income")
            income += amount;
        else if (type == "expense")
            expense += amount;
    }

    cout << fixed << setprecision(2);
    cout << "\nTotal Income: " << income << '\n';
    cout << "Total Expense: " << expense << '\n';
    cout << "Current Balance: " << income - expense << '\n';
}
