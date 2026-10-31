#include "task_prioritization.h"
#include "task_data.h"

#include <iostream>
#include <algorithm>
#include <limits>
using namespace std;

void taskPrioritization() {
    int count;

    cout << "\n===== TASK PRIORITIZATION =====\n";
    cout << "Number of tasks (1-20): ";

    if (!(cin >> count) || count < 1 || count > 20) {
        cout << "Invalid number of tasks!\n";
        cin.clear();
        cin.ignore(10000, '\n');
        return;
    }

    cin.ignore(numeric_limits<streamsize>::max(), '\n');
    taskList.clear();

    for (int i = 0; i < count; i++) {
        Task task;

        cout << "\nTask " << i + 1 << " title: ";
        getline(cin, task.title);

        if (task.title.empty()) {
            cout << "Title cannot be empty.\n";
            i--;
            continue;
        }

        cout << "Urgency (1-10): ";
        if (!(cin >> task.urgency) ||
            task.urgency < 1 || task.urgency > 10) {
            cout << "Invalid urgency. Please restart this feature.\n";
            cin.clear();
            cin.ignore(10000, '\n');
            taskList.clear();
            return;
        }

        cout << "Importance (1-10): ";
        if (!(cin >> task.importance) ||
            task.importance < 1 || task.importance > 10) {
            cout << "Invalid importance. Please restart this feature.\n";
            cin.clear();
            cin.ignore(10000, '\n');
            taskList.clear();
            return;
        }

        cin.ignore(numeric_limits<streamsize>::max(), '\n');

        cout << "Deadline (YYYY-MM-DD, or blank): ";
        getline(cin, task.deadline);

        task.status = "Pending";
        taskList.push_back(task);
    }

    sort(taskList.begin(), taskList.end(),
         [](const Task& a, const Task& b) {
             int scoreA = a.urgency * 2 + a.importance * 3;
             int scoreB = b.urgency * 2 + b.importance * 3;
             return scoreA > scoreB;
         });

    cout << "\n===== PRIORITIZED TASKS =====\n";

    for (size_t i = 0; i < taskList.size(); i++) {
        int score = taskList[i].urgency * 2
                  + taskList[i].importance * 3;

        cout << i + 1 << ". " << taskList[i].title
             << " | Score: " << score
             << " | Deadline: "
             << (taskList[i].deadline.empty()
                 ? "Not set" : taskList[i].deadline)
             << " | Status: " << taskList[i].status << '\n';
    }
}
