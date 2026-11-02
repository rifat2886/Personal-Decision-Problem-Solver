#include "habit_streak.h"
#include "error_handler.h"
#include "file_lock.h"
#include <algorithm>
#include <iostream>
#include <fstream>
#include <limits>
#include <vector>

using namespace std;

const string HABIT_FILE = "habit_log.txt";

// FIX (backend final testing): the old showHabitStreak() only
// counted total completions, even though it was presented as a
// streak. The helpers below validate a real calendar date and
// convert it to a day number (Howard Hinnant's days-from-civil
// algorithm), so a true consecutive-day streak can be computed.
static bool isLeapYear(int year)
{
    return (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
}

static bool validCalendarDate(const string& date)
{
    if (date.size() != 10 || date[4] != '-' || date[7] != '-')
        return false;
    for (int i = 0; i < 10; i++)
    {
        if (i == 4 || i == 7)
            continue;
        if (date[i] < '0' || date[i] > '9')
            return false;
    }
    int year = stoi(date.substr(0, 4));
    int month = stoi(date.substr(5, 2));
    int day = stoi(date.substr(8, 2));
    if (month < 1 || month > 12 || day < 1)
        return false;
    static const int daysInMonth[] =
        {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    int limit = daysInMonth[month - 1];
    if (month == 2 && isLeapYear(year))
        limit = 29;
    return day <= limit;
}

static int daysFromCivil(const string& date)
{
    int y = stoi(date.substr(0, 4));
    int m = stoi(date.substr(5, 2));
    int d = stoi(date.substr(8, 2));
    y -= m <= 2;
    int era = (y >= 0 ? y : y - 399) / 400;
    unsigned yoe = static_cast<unsigned>(y - era * 400);
    unsigned mp = static_cast<unsigned>((m + 9) % 12);
    unsigned doy = (153 * mp + 2) / 5 + d - 1;
    unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + static_cast<int>(doe) - 719468;
}

void markHabitDone()
{
    string habit, date;

    cin.ignore(numeric_limits<streamsize>::max(), '\n');

    cout << "\nEnter habit name: ";
    getline(cin, habit);

    if (habit.empty())
    {
        cout << "Habit name cannot be empty.\n";
        return;
    }

    cout << "Enter date (YYYY-MM-DD): ";
    cin >> date;

    if (!validCalendarDate(date))
    {
        cout << "Invalid date! Use a real date in YYYY-MM-DD format.\n";
        return;
    }

    FileLock lock(HABIT_FILE);
    ofstream file(HABIT_FILE, ios::app);

    if (!file)
    {
        cout << "Could not open habit log!\n";
        logError("markHabitDone: could not open habit_log.txt");
        return;
    }

    file << habit << "|" << date << '\n';

    cout << "Habit completion recorded!\n";
}

void showHabitStreak()
{
    string habit, line;
    int count = 0;
    vector<int> days;

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
        string savedDate = line.substr(separator + 1);

        if (savedHabit == habit && validCalendarDate(savedDate))
        {
            count++;
            days.push_back(daysFromCivil(savedDate));
        }
    }

    // Keep the old total-count line (existing tests and users rely
    // on it), and add the true consecutive-day streak: unique
    // dates, sorted, counted backwards from the latest date.
    cout << "Recorded completions for " << habit
         << ": " << count << '\n';

    if (days.empty())
    {
        cout << "Consecutive-day streak: 0 day(s)\n";
        return;
    }

    sort(days.begin(), days.end());
    days.erase(unique(days.begin(), days.end()), days.end());

    int streak = 1;
    for (int i = static_cast<int>(days.size()) - 1; i > 0; i--)
    {
        if (days[i] - days[i - 1] == 1)
            streak++;
        else
            break;
    }

    cout << "Consecutive-day streak: " << streak << " day(s)\n";
}
