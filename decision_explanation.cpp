#include "decision_explanation.h"
#include <iostream>
using namespace std;

void decisionExplanation() {
    int urgency, importance;

    cout << "\n===== DECISION EXPLANATION =====\n";

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

    cout << "\nFormula: (Urgency x 2) + (Importance x 3)\n";
    cout << "Calculation: (" << urgency << " x 2) + ("
         << importance << " x 3) = " << score << "/50\n";

    if (score >= 40) {
        cout << "Explanation: Very high priority.\n";
        cout << "Recommendation: Complete this task first.\n";
    } else if (score >= 30) {
        cout << "Explanation: High priority.\n";
        cout << "Recommendation: Schedule it soon.\n";
    } else if (score >= 20) {
        cout << "Explanation: Medium priority.\n";
        cout << "Recommendation: Plan it after higher-priority tasks.\n";
    } else {
        cout << "Explanation: Low priority based on this score.\n";
        cout << "Recommendation: Schedule it when time is available.\n";
    }
}
