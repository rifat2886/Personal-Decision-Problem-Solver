#include "task_status.h"
#include "task_data.h"

#include <iostream>
#include <limits>
using namespace std;

void taskStatusManager() {
    cout << "\n===== TASK STATUS MANAGER =====\n";

    if (taskList.empty()) {
        cout << "No tasks found. Use Task Prioritization first.\n";
        return;
    }

    for (size_t i = 0; i < taskList.size(); i++) {
        cout << i + 1 << ". " << taskList[i].title
             << " [" << taskList[i].status << "]\n";
    }

    int number;

    cout << "Select task number: ";
    if (!(cin >> number) ||
        number < 1 || number > static_cast<int>(taskList.size())) {
        cout << "Invalid task number!\n";
        cin.clear();
        cin.ignore(numeric_limits<streamsize>::max(), '\n');
        return;
    }

    cout << "1. Pending\n";
    cout << "2. In Progress\n";
    cout << "3. Completed\n";
    cout << "Choose status: ";

    int choice;

    if (!(cin >> choice) || choice < 1 || choice > 3) {
        cout << "Invalid status!\n";
        cin.clear();
        cin.ignore(numeric_limits<streamsize>::max(), '\n');
        return;
    }

    cin.ignore(numeric_limits<streamsize>::max(), '\n');

    if (choice == 1)
        taskList[number - 1].status = "Pending";
    else if (choice == 2)
        taskList[number - 1].status = "In Progress";
    else
        taskList[number - 1].status = "Completed";

    cout << "Status updated successfully.\n";
}
