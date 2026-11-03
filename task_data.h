#ifndef TASK_DATA_H
#define TASK_DATA_H

#include <string>
#include <vector>

struct Task {
    // id is the tasks.txt id ("" for a task not yet saved). It is
    // kept so console Task Status / Deadline work on the same tasks
    // the dashboard created, and vice versa.
    std::string id;
    std::string title;
    int urgency;
    int importance;
    std::string deadline;
    std::string status;
};

inline std::vector<Task> taskList;

#endif
