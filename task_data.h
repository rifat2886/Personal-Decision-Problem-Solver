#ifndef TASK_DATA_H
#define TASK_DATA_H

#include <string>
#include <vector>

struct Task {
    std::string title;
    int urgency;
    int importance;
    std::string deadline;
    std::string status;
};

inline std::vector<Task> taskList;

#endif
