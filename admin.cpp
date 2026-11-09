#include "admin.h"
#include "console_pg.h"

#include <fstream>
#include <iostream>
#include <string>

// Admin access is gated in main.cpp: only a logged-in user whose
// users.txt role is ADMIN can reach this function. This function
// therefore never needs (and must never contain) a hard-coded
// admin username/password, and it never prints stored passwords.
void adminPanel()
{
    std::cout << "\n===== ADMIN PANEL =====\n";

    // Phase 4, Batch B: Postgres mode lists the shared users table.
    if (console_pg::pgMode())
    {
        auto users = console_pg::listUsers();
        if (users.empty())
        {
            std::cout << "No registered users found.\n";
            return;
        }
        std::cout << "Registered Users:\n";
        for (auto& u : users)
            std::cout << "Username: " << u.first
                      << " | Role: " << u.second << '\n';
        return;
    }

    std::ifstream in("users.txt");

    if (!in)
    {
        std::cout << "No user data found.\n";
        return;
    }

    std::string username, password, role;
    bool found = false;

    std::cout << "Registered Users:\n";

    while (in >> username >> password >> role)
    {
        // Deliberately print only username and role, never password.
        std::cout << "Username: " << username
                  << " | Role: " << role << '\n';
        found = true;
    }

    if (!found)
        std::cout << "No registered users found.\n";
}
