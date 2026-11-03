#include "task_prioritization.h"
#include "task_data.h"
#include "task_store.h"
#include "decision_store.h"

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

        // FIX (backend final testing): retry a single invalid field
        // instead of discarding every task entered so far and
        // forcing the user to restart this feature.
        while (true) {
            cout << "Urgency (1-10): ";
            if (cin >> task.urgency &&
                task.urgency >= 1 && task.urgency <= 10)
                break;
            if (cin.eof()) {
                cout << "Input closed. Aborting task prioritization.\n";
                taskList.clear();
                return;
            }
            cout << "Invalid urgency. Please enter a number from 1 to 10.\n";
            cin.clear();
            cin.ignore(10000, '\n');
        }

        while (true) {
            cout << "Importance (1-10): ";
            if (cin >> task.importance &&
                task.importance >= 1 && task.importance <= 10)
                break;
            if (cin.eof()) {
                cout << "Input closed. Aborting task prioritization.\n";
                taskList.clear();
                return;
            }
            cout << "Invalid importance. Please enter a number from 1 to 10.\n";
            cin.clear();
            cin.ignore(10000, '\n');
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

        // Save each prioritised task as a decision record so
        // Search/Filter/Sort can find prioritised tasks. The
        // deadline is carried in the title for visibility.
        appendDecisionRecord("Task", score,
                             taskList[i].title +
                                 (taskList[i].deadline.empty()
                                      ? ""
                                      : " (deadline " +
                                            taskList[i].deadline + ")"));
    }

    // Persist the tasks so Task Status, Deadline Alert and the
    // dashboard all see them (previously they were in-memory only
    // and lost when the console app exited).
    pdps_tasks::appendTasks(taskList);
    cout << "Tasks saved to tasks.txt.\n";
}
