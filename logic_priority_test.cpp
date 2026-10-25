
#include "logic_priority.h"
#include <iostream>
#include <vector>

int main() {
    LogicPriorityDeveloper developer;

    std::cout << "=== Priority Calculator ===\n";
    developer.priority_calculator("Complete project", 4, 5);

    Task task_a{"Study C++", 4, 5, 4, 3, 2};
    Task task_b{"Clean room", 2, 2, 2, 1, 1};

    std::cout << "\n=== Compare Tasks ===\n";
    std::cout << developer.task_prioritization(task_a, task_b)
              << '\n';

    std::cout << "\n=== Compare Options ===\n";
    Option option_a{"Option A", 8, 7, 3};
    Option option_b{"Option B", 6, 8, 2};

    std::cout << developer.compare_options(option_a, option_b)
              << '\n';

    std::cout << "\n=== Daily Decision Maker ===\n";

    std::vector<Task> tasks = {
        {"Assignment", 5, 5, 5, 3, 2},
        {"Exercise",   3, 3, 4, 2, 1},
        {"Watch TV",   1, 1, 1, 2, 2}
    };

    auto recommendations =
        developer.daily_decision_maker(tasks, 5, 3);

    std::cout << "Recommended tasks:\n";
    for (const Task& task : recommendations) {
        std::cout << "- " << task.name << '\n';
    }

    return 0;
}
