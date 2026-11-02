#ifndef MULTI_TASK_DECISION_H
#define MULTI_TASK_DECISION_H

#include <string>
#include <vector>

// Restored capability from Sweety's old logic_priority branch
// (origin/logic-priority, merged PR #13 2026-10-25, files deleted
// 2026-10-30), integrated locally only, not pushed.
//
// Restored ONLY: the multi-task energy/time-budget daily decision
// algorithm, LogicPriorityDeveloper::daily_decision_maker.
// NOT restored: that class's priority_calculator,
// task_prioritization, and compare_options methods, because those
// duplicate Nuriya's existing priorityCalculator, taskPrioritization,
// and compareOptions modules, which must not be broken or duplicated.
//
// The old class's Task struct is also NOT restored: Nuriya's
// task_data.h already defines a different Task struct, so this module
// uses its own MultiTaskItem struct to avoid any name clash.
struct MultiTaskItem
{
    std::string name;
    int deadlineUrgency; // 1-10, higher = more urgent (sort key)
    int energy;          // 1-10, cost against the energy budget
    int time;            // 1-1440 minutes, cost against the time budget
};

// Pure algorithm, identical in effect to the original:
// sort by deadline urgency descending, then recommend each task in
// that order only while its energy and time both still fit in the
// remaining budgets, subtracting both on acceptance.
// The only intentional change from the original is stable_sort
// instead of sort, so tasks with equal urgency keep their input
// order deterministically; for distinct urgencies the result is
// exactly the original result.
std::vector<MultiTaskItem> selectMultiTasks(
    std::vector<MultiTaskItem> tasks,
    int availableEnergy,
    int availableTime);

// Interactive menu function (no main() in this file).
void multiTaskDecision();

#endif
