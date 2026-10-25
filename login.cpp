#include "login.h"

#include <iostream>
#include <fstream>
#include <string>

bool loginUser(std::string& currentUser, bool& isAdmin)
{
    std::string username, password;

    std::cout << "Enter username: ";
    std::cin >> username;

    std::cout << "Enter password: ";
    std::cin >> password;

    std::ifstream file("users.txt");

    std::string u, p, role;

    while (file >> u >> p >> role)
    {
        if (u == username && p == password)
        {
            currentUser = u;
            isAdmin = (role == "ADMIN");

            std::cout << "Login successful!\n";
            return true;
        }
    }

    std::cout << "Invalid username or password!\n";
    return false;
}