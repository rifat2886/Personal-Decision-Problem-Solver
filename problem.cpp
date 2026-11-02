#include "problem.h"
#include "decision_store.h"
#include <iostream>
#include <string>
using namespace std;

void problemSolver() {
    string problem;
    int difficulty, time;

    cout << "\n===== PROBLEM SOLVER =====\n";

    cout << "Enter problem name (one word): ";
    cin >> problem;

    cout << "Difficulty (1-5): ";
    if (!(cin >> difficulty)) {
        cin.clear();
        cin.ignore(10000, '\n');
        cout << "Invalid difficulty input!\n";
        return;
    }

    cout << "Available time in minutes: ";
    if (!(cin >> time)) {
        cin.clear();
        cin.ignore(10000, '\n');
        cout << "Invalid time input!\n";
        return;
    }

    if (difficulty < 1 || difficulty > 5 || time <= 0) {
        cout << "Invalid input!\n";
        return;
    }

    string suggestion;

    if (difficulty <= 2 && time >= 15) {
        suggestion = "Solve the problem step by step.";
    }
    else if (difficulty >= 4) {
        suggestion = "Divide the problem into smaller tasks.";
    }
    else if (time < 15) {
        suggestion = "Make a short and simple plan.";
    }
    else {
        suggestion = "Plan your work and start solving.";
    }

    cout << "Suggestion: " << suggestion << '\n';

    // Was decision_history.txt, a file no other menu module reads.
    // Now uses the shared decisions.txt format (id|date|type|
    // priority|title) so Search/Filter/Sort/Delete can find it.
    appendDecisionRecord("Problem", difficulty,
                         "Problem: " + problem + " - " + suggestion);
    cout << "History saved successfully.\n";
}
