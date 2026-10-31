#include "deadline_alert.h"
#include "task_data.h"

#include <iostream>
#include <string>
using namespace std;

void deadlineAlert() {
    cout << "\n===== DEADLINE ALERT =====\n";

    if (taskList.empty()) {
        cout << "No tasks found. Use Task Prioritization first.\n";
        return;
    }

    string today;

    cout << "Today's date (YYYY-MM-DD): ";
    getline(cin >> ws, today);

    if (today.size() != 10 ||
        today[4] != '-' || today[7] != '-') {
        cout << "Invalid date format!\n";
        return;
    }

    for (char c : today) {
        if (c != '-' && (c < '0' || c > '9')) {
            cout << "Invalid date format!\n";
            return;
        }
    }

    for (const Task& task : taskList) {
        if (task.deadline.empty() ||
            task.status == "Completed")
            continue;

        if (task.deadline.size() != 10 ||
            task.deadline[4] != '-' ||
            task.deadline[7] != '-') {
            cout << "Check deadline for: "
                 << task.title << '\n';
            continue;
        }

        if (task.deadline < today) {
            cout << "OVERDUE: " << task.title
                 << " | Deadline: " << task.deadline << '\n';
        } else if (task.deadline == today) {
            cout << "DUE TODAY: " << task.title << '\n';
        } else {
            cout << "UPCOMING: " << task.title
                 << " | Deadline: " << task.deadline << '\n';
        }
    }
}
