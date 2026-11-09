#include "password_change.h"
#include "console_pg.h"
#include "password_validation.h"
#include "file_lock.h"
#include "password_hash.h"

#include <iostream>
#include <fstream>
#include <string>
#include <vector>

bool changePassword(const std::string& currentUser)
{
    // Phase 4, Batch B: Postgres mode updates the shared users table.
    if (console_pg::pgMode())
    {
        std::string oldPassword, newPassword;

        std::cout << "Enter current password: ";
        std::cin >> oldPassword;

        std::string storedHash, role;
        if (!console_pg::getUser(currentUser, storedHash, role))
        {
            std::cout << "User not found!\n";
            return false;
        }

        if (!pdps_hash::verifyPassword(oldPassword, storedHash))
        {
            std::cout << "Wrong current password!\n";
            return false;
        }

        std::cout << "Enter new password: ";
        std::cin >> newPassword;

        if (!validPassword(newPassword))
        {
            std::cout << "Password needs 8+ characters, "
                      << "a letter and a digit.\n";
            return false;
        }

        if (!console_pg::updateUserHash(currentUser,
                                        pdps_hash::hashPassword(newPassword)))
        {
            std::cout << "Could not update password!\n";
            return false;
        }

        std::cout << "Password changed successfully!\n";
        return true;
    }

    // Hold the users lock for the whole change flow, so a
    // dashboard register/change-password cannot interleave.
    FileLock lock("users.txt");
    std::ifstream input("users.txt");

    if (!input)
    {
        std::cout << "User database not found!\n";
        return false;
    }

    std::vector<std::string> records;
    std::string username, password, role;
    std::string oldPassword, newPassword;
    bool found = false;

    std::cout << "Enter current password: ";
    std::cin >> oldPassword;

    while (input >> username >> password >> role)
    {
        if (username == currentUser)
        {
            found = true;

            if (!pdps_hash::verifyPassword(oldPassword, password))
            {
                std::cout << "Wrong current password!\n";
                return false;
            }

            std::cout << "Enter new password: ";
            std::cin >> newPassword;

            if (!validPassword(newPassword))
            {
                std::cout << "Password needs 8+ characters, "
                          << "a letter and a digit.\n";
                return false;
            }

            password = pdps_hash::hashPassword(newPassword);
        }

        records.push_back(username + " " + password + " " + role);
    }

    input.close();

    if (!found)
    {
        std::cout << "User not found!\n";
        return false;
    }

    std::ofstream output("users.txt");

    if (!output)
    {
        std::cout << "Could not update password!\n";
        return false;
    }

    for (const std::string& record : records)
        output << record << '\n';

    std::cout << "Password changed successfully!\n";
    return true;
}