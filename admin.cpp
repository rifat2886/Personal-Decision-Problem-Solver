#include "admin.h"

#include <iostream>
#include <string>

bool adminLogin()
{
    const std::string ADMIN_USERNAME = "admin";
    const std::string ADMIN_PASSWORD = "Admin@123";

    std::string username, password;

    std::cout << "\n===== ADMIN LOGIN =====\n";

    std::cout << "Enter Admin Username: ";
    std::cin >> username;

    std::cout << "Enter Admin Password: ";
    std::cin >> password;

    if (username == ADMIN_USERNAME &&
        password == ADMIN_PASSWORD)
    {
        std::cout << "Admin login successful!\n";
        return true;
    }

    std::cout << "Invalid Admin Username or Password!\n";
    return false;
}

void adminPanel()
{
    int choice;

    std::cout << "\n===== ADMIN PANEL =====\n";
    std::cout << "1. View Admin Information\n";
    std::cout << "0. Logout from Admin Panel\n";
    std::cout << "Enter choice: ";

    std::cin >> choice;

    switch (choice)
    {
        case 1:
            std::cout << "Logged in as Administrator.\n";
            break;

        case 0:
            std::cout << "Leaving Admin Panel.\n";
            break;

        default:
            std::cout << "Invalid choice!\n";
    }
}