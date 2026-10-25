
#include "habit.h"
#include <iostream>
#include <iomanip>
using namespace std;

// Feature 7: Habit Decision
void habitDecision() {
    int completed, planned;

    cout << "\n===== HABIT DECISION =====\n";
    cout << "How many habits did you complete today? ";
    cin >> completed;

    cout << "How many habits did you plan? ";
    cin >> planned;

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
    int previousDays, completedToday;

    cout << "\n===== HABIT STREAK =====\n";
    cout << "Previous consecutive days completed: ";
    cin >> previousDays;

    cout << "Did you complete today's habit? (1 = Yes, 0 = No): ";
    cin >> completedToday;

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
