#include "habit.h"
#include <iostream>
#include <iomanip>
#include <limits>
using namespace std;

static bool readInt(int& value)
{
    if (cin >> value)
        return true;
    cout << "Invalid input!\n";
    cin.clear();
    cin.ignore(numeric_limits<streamsize>::max(), '\n');
    return false;
}

// Feature 7: Habit Decision
void habitDecision() {
    int completed = 0, planned = 0;

    cout << "\n===== HABIT DECISION =====\n";
    cout << "How many habits did you complete today? ";
    if (!readInt(completed))
        return;

    cout << "How many habits did you plan? ";
    if (!readInt(planned))
        return;

    if (planned <= 0 || completed < 0 || completed > planned) {
        cout << "Invalid input!\n";
        return;
    }

    double percentage = completed * 100.0 / planned;

    cout << fixed << setprecision(2);
    cout << "Today's completion: " << percentage << "%\n";

    if (completed == planned)
        cout << "Excellent! You completed all planned habits.\n";
    else if (percentage >= 50)
        cout << "Good progress! Keep going.\n";
    else
        cout << "Try making a simpler plan tomorrow.\n";
}

// Feature: Habit Streak
void habitStreak() {
    int previousDays = 0, completedToday = 0;

    cout << "\n===== HABIT STREAK =====\n";
    cout << "Previous consecutive days completed: ";
    if (!readInt(previousDays))
        return;

    cout << "Did you complete today's habit? (1 = Yes, 0 = No): ";
    if (!readInt(completedToday))
        return;

    if (previousDays < 0 ||
        (completedToday != 0 && completedToday != 1)) {
        cout << "Invalid input!\n";
        return;
    }

    if (completedToday == 1)
        cout << "Current streak: " << previousDays + 1 << " day(s)\n";
    else {
        cout << "Current streak: 0 day(s)\n";
        cout << "Start a new streak tomorrow!\n";
    }
}
