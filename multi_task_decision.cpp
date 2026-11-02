#include "multi_task_decision.h"
#include "decision_store.h"
#include <algorithm>
#include <iostream>
#include <limits>
#include <string>

using namespace std;

vector<MultiTaskItem> selectMultiTasks(
    vector<MultiTaskItem> tasks,
    int availableEnergy,
    int availableTime)
{
    stable_sort(tasks.begin(), tasks.end(),
                [](const MultiTaskItem& a, const MultiTaskItem& b) {
                    return a.deadlineUrgency > b.deadlineUrgency;
                });

    vector<MultiTaskItem> recommended;
    for (const MultiTaskItem& task : tasks)
    {
        if (task.energy <= availableEnergy &&
            task.time <= availableTime)
        {
            recommended.push_back(task);
            availableEnergy -= task.energy;
            availableTime -= task.time;
        }
    }
    return recommended;
}

// Read one integer with the project's usual invalid-input behaviour:
// on a non-numeric or out-of-range value, print a message, clear the
// stream and return false (the feature aborts, like daily_decision,
// problem, and compare_options do). On end-of-file, return false
// without looping, consistent with the final-audit EOF fixes.
static bool readInt(const char* prompt, int minimum, int maximum,
                    int& value)
{
    cout << prompt;
    if (!(cin >> value))
    {
        if (cin.eof())
            cout << "Input closed. Aborting multi-task decision.\n";
        else
            cout << "Invalid input!\n";
        cin.clear();
        cin.ignore(numeric_limits<streamsize>::max(), '\n');
        return false;
    }
    if (value < minimum || value > maximum)
    {
        cout << "Invalid input! Expected " << minimum << "-"
             << maximum << ".\n";
        cin.clear();
        cin.ignore(numeric_limits<streamsize>::max(), '\n');
        return false;
    }
    return true;
}

void multiTaskDecision()
{
    cout << "\n===== MULTI-TASK DAILY DECISION =====\n";
    cout << "Restored from Sweety's logic_priority daily decision:\n"
         << "tasks are sorted by deadline urgency, then accepted\n"
         << "in that order only while their energy and time both\n"
         << "fit in your remaining budgets.\n";

    int count = 0;
    if (!readInt("How many tasks? (1-20): ", 1, 20, count))
        return;

    int availableEnergy = 0;
    if (!readInt("Available energy (1-100): ", 1, 100,
                 availableEnergy))
        return;

    int availableTime = 0;
    if (!readInt("Available time in minutes (1-1440): ", 1, 1440,
                 availableTime))
        return;

    // Consume the newline left by the last numeric read so the
    // first task name can be read with getline, including an
    // intentionally empty name (which is rejected, not skipped).
    cin.ignore(numeric_limits<streamsize>::max(), '\n');

    vector<MultiTaskItem> tasks;
    for (int i = 1; i <= count; ++i)
    {
        MultiTaskItem task;
        // Empty name: reject and retry this same task, so an empty
        // line cannot silently become a task or shift later inputs.
        while (true)
        {
            cout << "Task " << i << " name: ";
            if (!getline(cin, task.name))
            {
                cout << "Input closed. Aborting multi-task decision.\n";
                return;
            }
            if (!task.name.empty())
                break;
            cout << "Task name cannot be empty.\n";
        }

        if (!readInt("  Deadline urgency (1-10): ", 1, 10,
                     task.deadlineUrgency))
            return;
        if (!readInt("  Energy cost (1-10): ", 1, 10, task.energy))
            return;
        if (!readInt("  Time in minutes (1-1440): ", 1, 1440,
                     task.time))
            return;
        // Consume the newline left by the time read so the next
        // task name is read with getline, not as an empty line.
        cin.ignore(numeric_limits<streamsize>::max(), '\n');

        tasks.push_back(task);
    }

    vector<MultiTaskItem> recommended =
        selectMultiTasks(tasks, availableEnergy, availableTime);

    int remainingEnergy = availableEnergy;
    int remainingTime = availableTime;
    for (const MultiTaskItem& task : recommended)
    {
        remainingEnergy -= task.energy;
        remainingTime -= task.time;
    }

    if (recommended.empty())
    {
        cout << "\nNo tasks fit your energy/time budgets.\n";
    }
    else
    {
        cout << "\nRecommended tasks (in deadline-urgency order):\n";
        for (const MultiTaskItem& task : recommended)
        {
            cout << "- " << task.name << " (urgency "
                 << task.deadlineUrgency << ", energy "
                 << task.energy << ", time " << task.time
                 << " min)\n";
            // Saved through the shared decision store, like Nuriya's
            // dailyDecisionMaker and taskPrioritization, so Sweety's
            // search/filter/sort and Rifat's delete can find them.
            // Priority is urgency scaled to the 0-50 range used by
            // the other decision modules, so sorting respects it.
            appendDecisionRecord(
                "MultiTask", task.deadlineUrgency * 5,
                "Multi-task: " + task.name);
        }
    }

    if (recommended.size() < tasks.size())
    {
        // Match by value with a remaining-count, so duplicate tasks
        // (same name/urgency/energy/time) are counted correctly:
        // the first occurrences up to the recommended count are
        // treated as recommended, any further identical task is not.
        cout << "\nNot recommended (did not fit the remaining budgets):\n";
        for (size_t i = 0; i < tasks.size(); ++i)
        {
            const MultiTaskItem& task = tasks[i];
            int recommendedCount = 0;
            for (const MultiTaskItem& chosen : recommended)
            {
                if (chosen.name == task.name &&
                    chosen.deadlineUrgency == task.deadlineUrgency &&
                    chosen.energy == task.energy &&
                    chosen.time == task.time)
                    ++recommendedCount;
            }
            int seenBefore = 0;
            for (size_t j = 0; j < i; ++j)
            {
                if (tasks[j].name == task.name &&
                    tasks[j].deadlineUrgency == task.deadlineUrgency &&
                    tasks[j].energy == task.energy &&
                    tasks[j].time == task.time)
                    ++seenBefore;
            }
            if (seenBefore >= recommendedCount)
                cout << "- " << task.name << '\n';
        }
    }

    cout << "Remaining energy: " << remainingEnergy << '\n';
    cout << "Remaining time: " << remainingTime << " min\n";
}
