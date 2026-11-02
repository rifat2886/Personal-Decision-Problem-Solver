#include "daily_decision.h"
#include "decision_store.h"
#include <iostream>
#include <string>
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

    string suggestion;
    if (requiredTime > availableTime) {
        suggestion = "Divide the task into smaller parts.";
    } else if (urgency >= 8 && importance >= 8) {
        suggestion = "Complete this task first.";
    } else if (importance >= 8 && energy <= 4) {
        suggestion = "Take a short break, then do this task.";
    } else if (urgency >= 7) {
        suggestion = "Complete this task soon.";
    } else {
        suggestion = "Schedule this task for later.";
    }
    cout << "Suggestion: " << suggestion << '\n';

    // Integration fix: previously this module printed a suggestion
    // and saved nothing, so Search/Filter/Sort/Backup/Delete
    // (which all read decisions.txt) could never find it.
    int score = urgency * 2 + importance * 3;
    appendDecisionRecord("Daily", score, "Daily decision: " + suggestion);
}
