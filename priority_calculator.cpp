#include "priority_calculator.h"
#include <iostream>
using namespace std;

void priorityCalculator() {
    int urgency, importance;

    cout << "\n===== PRIORITY CALCULATOR =====\n";

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

    cin.ignore(10000, '\n');

    int score = urgency * 2 + importance * 3;

    cout << "Priority Score: " << score << "/50\n";

    if (score >= 40)
        cout << "Priority: VERY HIGH\n";
    else if (score >= 30)
        cout << "Priority: HIGH\n";
    else if (score >= 20)
        cout << "Priority: MEDIUM\n";
    else
        cout << "Priority: LOW\n";
}
