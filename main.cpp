#include <iostream>
#include <limits>
#include "auth.h"
#include "admin.h"
#include "planner.h"
#include "decision.h"
#include "budget.h"
#include "habit.h"
#include "report.h"
#include "problem.h"
using namespace std;

int main() {
    string currentUser;
    bool isAdmin = false;
    bool exitProgram = false;

    cout << "========================================\n";
    cout << "  PERSONAL DECISION & PROBLEM SOLVER\n";
    cout << "========================================\n";

    while (!exitProgram) {
        currentUser = "";
        isAdmin = false;

        // Login or registration
        bool loggedIn = registerOrLogin(currentUser, isAdmin);

        if (!loggedIn) {
            char choice;

            cout << "\n1. Try again\n";
            cout << "0. Exit program\n";
            cout << "Enter choice: ";

            cin >> choice;

            if (choice == '0') {
                exitProgram = true;
            }

            continue;
        }

        cout << "\nWelcome, " << currentUser << "!\n";

        bool loggedOut = false;

        while (!loggedOut && !exitProgram) {
            cout << "\n========== MAIN MENU ==========\n";
            cout << "1. Daily Decision Maker\n";
            cout << "2. Priority Calculator\n";
            cout << "3. Time Allocation\n";
            cout << "4. Budget Decision\n";
            cout << "5. Task Prioritization\n";
            cout << "6. Study Planner\n";
            cout << "7. Habit Decision\n";
            cout << "8. Compare Options\n";
            cout << "9. Problem Solver\n";
            cout << "10. Decision History\n";
            cout << "11. Generate Report\n";
            cout << "12. Control Panel\n";
            cout << "13. Logout\n";
            cout << "0. Exit Program\n";

            if (isAdmin) {
                cout << "14. Admin Panel\n";
            }

            cout << "Select an option: ";

            int choice;

            if (!(cin >> choice)) {
                cin.clear();
                cin.ignore(
                    numeric_limits<streamsize>::max(), '\n'
                );

                cout << "Invalid input! Enter a number.\n";
                continue;
            }

            switch (choice) {
                case 1:
                    dailyDecision();
                    break;

                case 2:
                    priorityCalculator();
                    break;

                case 3:
                    timeAllocation();
                    break;

                case 4:
                    budgetDecision();
                    break;

                case 5:
                    taskPrioritization();
                    break;

                case 6:
                    studyPlanner();
                    break;

                case 7:
                    habitDecision();
                    break;

                case 8:
                    compareOptions();
                    break;

                case 9:
                    problemSolver();
                    break;

                case 10:
                    decisionHistory();
                    break;

                case 11:
                    generateReport();
                    break;

                case 12:
                    controlPanel();
                    break;

                case 13:
                    loggedOut = true;
                    cout << "Logged out successfully.\n";
                    break;

                case 14:
                    if (isAdmin) {
                        adminPanel();
                    } else {
                        cout << "Access denied!\n";
                    }
                    break;

                case 0: {
                    char confirm;

                    cout << "Exit the program? (y/n): ";
                    cin >> confirm;

                    if (confirm == 'y' || confirm == 'Y') {
                        exitProgram = true;
                        cout << "Thank you for using the program!\n";
                    }

                    break;
                }

                default:
                    cout << "Invalid menu option!\n";
            }
        }
    }

    return 0;
}
