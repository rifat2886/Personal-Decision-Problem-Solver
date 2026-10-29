```cpp
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

    cout << "\n0. Exit Program\n";
    cout << "============================================\n";
}

int main()
{
    int choice;
    bool running = true;
    string username;
    bool loggedIn = false;

    while (running)
    {
        showMenu();

        cout << "Enter your choice: ";
        choice = getValidatedInteger(0, 34);

        switch (choice)
        {
            // Authentication & Core System
            case 1:
                registerUser();
                break;

            case 2:
                if (loginUser())
                {
                    cout << "Login successful.\n";
                    cout << "Enter your username for this session: ";
                    cin >> username;
                    loggedIn = true;
                }
                else
                {
                    cout << "Login failed.\n";
                }
                break;

            case 3:
                if (loggedIn)
                    showProfile(username);
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
                adminPanel();
                break;

            case 6:
                timeAllocation();
                break;

            case 7:
                studyPlanner();
                break;

            case 8:
                logoutUser();
                loggedIn = false;
                username.clear();
                break;

            // Decision & Task Management
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

            // Budget, Savings & Habits
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

            // History & File Management
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
                string id;

                cout << "Enter decision ID to delete: ";
                cin >> id;

                confirmDelete(id);
                break;
            }

            case 0:
                cout << "Thank you for using the system!\n";
                running = false;
                break;

            default:
                cout << "Invalid choice. Please try again.\n";
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
``` 
