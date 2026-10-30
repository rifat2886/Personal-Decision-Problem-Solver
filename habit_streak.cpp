#include "habit_streak.h"
#include <iostream>
#include <fstream>
#include <limits>

using namespace std;

const string HABIT_FILE = "habit_log.txt";

void markHabitDone()
{
    string habit, date;

    cin.ignore(numeric_limits<streamsize>::max(), '\n');

    cout << "\nEnter habit name: ";
    getline(cin, habit);

    cout << "Enter date (YYYY-MM-DD): ";
    cin >> date;

    ofstream file(HABIT_FILE, ios::app);

    if (!file)
    {
        cout << "Could not open habit log!\n";
        return;
    }

    file << habit << "|" << date << '\n';

    cout << "Habit completion recorded!\n";
}

void showHabitStreak()
{
    string habit, line;
    int count = 0;

    cin.ignore(numeric_limits<streamsize>::max(), '\n');

    cout << "\nEnter habit name to search: ";
    getline(cin, habit);

    ifstream file(HABIT_FILE);

    if (!file)
    {
        cout << "No habit records found.\n";
        return;
    }

    while (getline(file, line))
    {
        size_t separator = line.find('|');

        if (separator == string::npos)
            continue;

        string savedHabit = line.substr(0, separator);

        if (savedHabit == habit)
            count++;
    }

    cout << "Recorded completions for " << habit
         << ": " << count << '\n';

    cout << "(This is the total recorded count, not necessarily "
            "a consecutive-day streak.)\n";
}
