
#ifndef LOGIC_PRIORITY_H
#define LOGIC_PRIORITY_H

#include <string>
#include <vector>

struct Task {
    std::string name;
    int deadline_urgency;
    int urgency;
    int importance;
    int energy;
    int time;
};

struct Option {
    std::string name;
    int benefit;
    int feasibility;
    int cost;
};

class LogicPriorityDeveloper {
public:
    std::vector<Task> daily_decision_maker(
        std::vector<Task> tasks,
        int available_energy,
        int available_time
    );

    int priority_calculator(
        const std::string& task_name,
        int urgency,
        int importance
    );

    std::string task_prioritization(
        const Task& task_a,
        const Task& task_b
    );

    std::string compare_options(
        const Option& option_a,
        const Option& option_b
    );
};

#endif
