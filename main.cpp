#include <iostream>
#include <string>

#include "registration.h"
#include "login.h"
#include "profile.h"
#include "password_change.h"
#include "admin.h"
#include "time_allocation.h"
#include "study_planner.h"
#include "logout.h"

int main()
{
    std::string currentUser;
    bool isAdmin = false;
    bool loggedIn = false;
    int choice;

    while (true)
    {
        // LOGIN ER AGE SUDHU EI MENU DEKHABE
        if (!loggedIn)
        {
            std::cout << "\n===== WELCOME =====\n";
            std::cout << "1. Register\n";
            std::cout << "2. Login\n";
            std::cout << "0. Exit\n";
            std::cout << "Choice: ";
        }
        else
        {
            // LOGIN ER POR USER DASHBOARD
            std::cout << "\n===== USER DASHBOARD =====\n";
            std::cout << "Welcome, " << currentUser << "!\n";
            std::cout << "1. Profile\n";
            std::cout << "2. Change Password\n";
            std::cout << "3. Time Allocation\n";
            std::cout << "4. Study Planner\n";

            if (isAdmin)
                std::cout << "5. Admin Panel\n";

            std::cout << "8. Logout\n";
            std::cout << "0. Exit\n";
            std::cout << "Choice: ";
        }

        if (!(std::cin >> choice))
        {
            std::cin.clear();
            std::cin.ignore(10000, '\n');
            std::cout << "Invalid input!\n";
            continue;
        }

        if (choice == 0)
        {
            std::cout << "Program closed.\n";
            return 0;
        }

        // LOGIN ER AGE
        if (!loggedIn)
        {
            switch (choice)
            {
                case 1:
                    registerUser();
                    break;

                case 2:
                    if (loginUser(currentUser, isAdmin))
                        loggedIn = true;
                    break;

                default:
                    std::cout << "Invalid choice!\n";
            }

            continue;
        }

        // LOGIN ER POR
        switch (choice)
        {
            case 1:
                showProfile(currentUser, isAdmin);
                break;

            case 2:
                changePassword(currentUser);
                break;

            case 3:
                timeAllocation();
                break;

            case 4:
                studyPlanner();
                break;

            case 5:
                if (isAdmin)
                    adminPanel();
                else
                    std::cout << "Admin access denied!\n";
                break;

            case 8:
                logoutUser(currentUser, isAdmin, loggedIn);
                break;

            default:
                std::cout << "Invalid choice!\n";
        }
    }
}