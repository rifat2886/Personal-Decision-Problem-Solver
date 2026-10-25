#include "password_change.h"
#include "password_validation.h"

#include <iostream>
#include <fstream>
#include <string>
#include <vector>

bool changePassword(const std::string& currentUser)
{
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

            if (password != oldPassword)
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

            password = newPassword;
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