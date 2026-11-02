
#include <iostream>
#include <string>

#include "registration.h"
#include "login.h"
#include "password_validation.h"
#include "profile.h"
#include "password_change.h"
#include "admin.h"
#include "input_validation.h"
#include "time_allocation.h"
#include "study_planner.h"
#include "logout.h"

#include "daily_decision.h"
#include "priority_calculator.h"
#include "task_prioritization.h"
#include "compare_options.h"
#include "task_status.h"
#include "deadline_alert.h"
#include "decision_explanation.h"

#include "income_expense.h"
#include "savings_goal.h"
#include "habit_streak.h"
#include "period_report.h"
#include "export_report.h"

#include "search_history.h"
#include "filter_sort.h"
#include "backup_restore.h"
#include "error_handler.h"
#include "delete_confirmation.h"

// Previously orphaned modules: their .cpp files were compiled but
// never reachable from the menu, so users could not use them.
#include "problem.h"
#include "report.h"
#include "budget.h"
#include "habit.h"
#include "control.h"

// Restored multi-task decision (Sweety's logic_priority daily
// decision, without that class's priority/compare/task methods).
#include "multi_task_decision.h"

using namespace std;

void showMenu()
{
    cout << "\n============================================\n";
    cout << "   PERSONAL DECISION & PROBLEM SOLVER\n";
    cout << "============================================\n";

    cout << "\n--- Authentication & Core System ---\n";
    cout << "1. Register\n";
    cout << "2. Login\n";
    cout << "3. Show Profile\n";
    cout << "4. Change Password\n";
    cout << "5. Admin Panel\n";
    cout << "6. Time Allocation\n";
    cout << "7. Study Planner\n";
    cout << "8. Logout\n";

    cout << "\n--- Decision & Task Management ---\n";
    cout << "9. Daily Decision Maker\n";
    cout << "10. Priority Calculator\n";
    cout << "11. Task Prioritization\n";
    cout << "12. Compare Options\n";
    cout << "13. Task Status Manager\n";
    cout << "14. Deadline Alert\n";
    cout << "15. Decision Explanation\n";

    cout << "\n--- Budget, Savings & Habits ---\n";
    cout << "16. Add Income/Expense\n";
    cout << "17. Show Transactions\n";
    cout << "18. Show Balance\n";
    cout << "19. Add Savings Goal\n";
    cout << "20. Add Savings Amount\n";
    cout << "21. Show Savings Goals\n";
    cout << "22. Mark Habit Done\n";
    cout << "23. Show Habit Completion Count\n";
    cout << "24. Weekly Report\n";
    cout << "25. Monthly Report\n";
    cout << "26. Export TXT Report\n";
    cout << "27. Export CSV Report\n";

    cout << "\n--- History & File Management ---\n";
    cout << "28. Search Decision History\n";
    cout << "29. Filter Decisions\n";
    cout << "30. Sort Decisions by Priority\n";
    cout << "31. Backup Decisions\n";
    cout << "32. Restore Decisions\n";
    cout << "33. Show Error Log\n";
    cout << "34. Delete Decision\n";

    cout << "\n--- Additional Integrated Modules ---\n";
    cout << "35. Problem Solver\n";
    cout << "36. Daily Summary Report\n";
    cout << "37. Budget Decision (calculator)\n";
    cout << "38. Income & Expense Tracking (summary)\n";
    cout << "39. Savings Goal Calculator\n";
    cout << "40. Habit Decision\n";
    cout << "41. Habit Streak (calculator)\n";
    cout << "42. Control Panel (History Management)\n";
    cout << "43. Multi-Task Daily Decision (energy/time budget)\n";

    cout << "\n0. Exit Program\n";
    cout << "============================================\n";
}

int main()
{
    int choice;
    bool running = true;
    string username;
    bool loggedIn = false;
    bool isAdmin = false;

    while (running)
    {
        showMenu();

        choice = getValidNumber(0, 43);

        switch (choice)
        {
            case 1:
                registerUser();
                break;

            case 2:
                if (loggedIn)
                {
                    cout << "You are already logged in.\n";
                }
                else if (loginUser(username, isAdmin))
                {
                    loggedIn = true;
                }
                else
                {
                    cout << "Login failed.\n";
                }
                break;

            case 3:
                if (loggedIn)
                    showProfile(username, isAdmin);
                else
                    cout << "Please login first.\n";
                break;

            case 4:
                if (loggedIn)
                    changePassword(username);
                else
                    cout << "Please login first.\n";
                break;

            case 5:
                if (loggedIn && isAdmin)
                    adminPanel();
                else
                    cout << "Admin access required. Please login as ADMIN.\n";
                break;

            case 6:
                if (loggedIn)
                    timeAllocation();
                else
                    cout << "Please login first.\n";
                break;

            case 7:
                if (loggedIn)
                    studyPlanner();
                else
                    cout << "Please login first.\n";
                break;

            case 8:
                if (loggedIn)
                    logoutUser(username, isAdmin, loggedIn);
                else
                    cout << "You are not logged in.\n";
                break;

            case 9:
                dailyDecisionMaker();
                break;

            case 10:
                priorityCalculator();
                break;

            case 11:
                taskPrioritization();
                break;

            case 12:
                compareOptions();
                break;

            case 13:
                taskStatusManager();
                break;

            case 14:
                deadlineAlert();
                break;

            case 15:
                decisionExplanation();
                break;

            case 16:
                addTransaction();
                break;

            case 17:
                showTransactions();
                break;

            case 18:
                showBalance();
                break;

            case 19:
                addSavingsGoal();
                break;

            case 20:
                addSavingsAmount();
                break;

            case 21:
                showSavingsGoals();
                break;

            case 22:
                markHabitDone();
                break;

            case 23:
                showHabitStreak();
                break;

            case 24:
                showWeeklyReport();
                break;

            case 25:
                showMonthlyReport();
                break;

            case 26:
                exportReportTXT();
                break;

            case 27:
                exportReportCSV();
                break;

            case 28:
                searchHistory();
                break;

            case 29:
                filterDecisions();
                break;

            case 30:
                sortDecisions();
                break;

            case 31:
                backupDecisions();
                break;

            case 32:
                restoreDecisions();
                break;

            case 33:
                showErrorLog();
                break;

            case 34:
            {
                if (!loggedIn)
                {
                    cout << "Please login first.\n";
                    break;
                }

                string id;

                cout << "Enter decision ID to delete: ";
                cin >> id;

                confirmDelete(id);
                break;
            }

            case 35:
                problemSolver();
                break;

            case 36:
                generateReport();
                break;

            case 37:
                budgetDecision();
                break;

            case 38:
                incomeExpenseTracking();
                break;

            case 39:
                savingsGoal();
                break;

            case 40:
                habitDecision();
                break;

            case 41:
                habitStreak();
                break;

            case 42:
                controlPanel();
                break;

            case 43:
                multiTaskDecision();
                break;

            case 0:
                if (loggedIn)
                    logoutUser(username, isAdmin, loggedIn);

                cout << "Thank you for using the system!\n";
                running = false;
                break;
        }

        if (running)
        {
            cout << "\nPress Enter to return to the menu...";
            cin.ignore(10000, '\n');
            cin.get();
        }
    }

    return 0;
}
