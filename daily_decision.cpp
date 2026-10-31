#include "daily_decision.h"
#include <iostream>
using namespace std;

void dailyDecisionMaker() {
    int availableTime, requiredTime, urgency, importance, energy;

    cout << "\n===== DAILY DECISION MAKER =====\n";

    cout << "Available time (minutes): ";
    if (!(cin >> availableTime) ||
        availableTime < 1 || availableTime > 1440) {
        cout << "Invalid time!\n";
        cin.clear();
        cin.ignore(10000, '\n');
        return;
    }

    cout << "Required time (minutes): ";
    if (!(cin >> requiredTime) || requiredTime < 1) {
        cout << "Invalid time!\n";
        cin.clear();
        cin.ignore(10000, '\n');
        return;
    }

    cout << "Urgency (1-10): ";
    if (!(cin >> urgency) || urgency < 1 || urgency > 10) {
        cout << "Invalid urgency!\n";
        cin.clear();
        cin.ignore(10000, '\n');
        return;
    }

    cout << "Importance (1-10): ";
    if (!(cin >> importance) ||
        importance < 1 || importance > 10) {
        cout << "Invalid importance!\n";
        cin.clear();
        cin.ignore(10000, '\n');
        return;
    }

    cout << "Energy level (1-10): ";
    if (!(cin >> energy) || energy < 1 || energy > 10) {
        cout << "Invalid energy level!\n";
        cin.clear();
        cin.ignore(10000, '\n');
        return;
    }

    cin.ignore(10000, '\n');

    if (requiredTime > availableTime) {
        cout << "Suggestion: Divide the task into smaller parts.\n";
    } else if (urgency >= 8 && importance >= 8) {
        cout << "Suggestion: Complete this task first.\n";
    } else if (importance >= 8 && energy <= 4) {
        cout << "Suggestion: Take a short break, then do this task.\n";
    } else if (urgency >= 7) {
        cout << "Suggestion: Complete this task soon.\n";
    } else {
        cout << "Suggestion: Schedule this task for later.\n";
    }
}
