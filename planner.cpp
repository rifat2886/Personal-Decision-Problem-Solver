#include "planner.h"
#include <iostream>
using namespace std;

void timeAllocation() {
    double sleep, study, work, other;

    cout << "Sleep hours: ";
    cin >> sleep;

    cout << "Study hours: ";
    cin >> study;

    cout << "Work hours: ";
    cin >> work;

    cout << "Other activities hours: ";
    cin >> other;

    if (sleep < 0 || study < 0 || work < 0 ||
        other < 0 || sleep + study + work + other > 24) {
        cout << "Invalid hours! Total must be 0-24.\n";
        return;
    }

    double freeTime = 24 - sleep - study - work - other;

    cout << "Your free time: "
         << freeTime << " hours per day\n";
}

void studyPlanner() {
    int days;
    double topics;

    cout << "Days remaining before exam: ";
    cin >> days;

    cout << "Topics remaining: ";
    cin >> topics;

    if (days <= 0 || topics < 0) {
        cout << "Invalid input!\n";
        return;
    }

    cout << "Daily study target: "
         << topics / days << " topics per day\n";

    cout << "Keep time for revision and practice.\n";
}
