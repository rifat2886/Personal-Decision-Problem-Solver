
#include "logic_priority.h"
#include <algorithm>
#include <iostream>

std::vector<Task> LogicPriorityDeveloper::daily_decision_maker(
    std::vector<Task> tasks,
    int available_energy,
    int available_time
) {
    std::sort(tasks.begin(), tasks.end(),
        [](const Task& a, const Task& b) {
            return a.deadline_urgency > b.deadline_urgency;
        });

    std::vector<Task> recommended_tasks;

    for (const Task& task : tasks) {
        if (task.energy <= available_energy &&
            task.time <= available_time) {
            recommended_tasks.push_back(task);
            available_energy -= task.energy;
            available_time -= task.time;
        }
    }

    return recommended_tasks;
}

int LogicPriorityDeveloper::priority_calculator(
    const std::string& task_name,
    int urgency,
    int importance
) {
    int score = urgency * importance;

    std::cout << task_name << " priority score: "
              << score << '\n';

    if (score >= 16)
        std::cout << "Priority: Critical\n";
    else if (score >= 9)
        std::cout << "Priority: High\n";
    else if (score >= 4)
        std::cout << "Priority: Medium\n";
    else
        std::cout << "Priority: Low\n";

    return score;
}

std::string LogicPriorityDeveloper::task_prioritization(
    const Task& task_a,
    const Task& task_b
) {
    int score_a = task_a.urgency * task_a.importance;
    int score_b = task_b.urgency * task_b.importance;

    if (score_a > score_b)
        return task_a.name + " should be prioritized.";

    if (score_b > score_a)
        return task_b.name + " should be prioritized.";

    return "Both tasks have equal priority.";
}

std::string LogicPriorityDeveloper::compare_options(
    const Option& option_a,
    const Option& option_b
) {
    int score_a =
        option_a.benefit + option_a.feasibility - option_a.cost;

    int score_b =
        option_b.benefit + option_b.feasibility - option_b.cost;

    if (score_a > score_b)
        return option_a.name + " is the better option.";

    if (score_b > score_a)
        return option_b.name + " is the better option.";

    return "Both options have equal scores.";
}
