#include "registration.h"
#include "password_validation.h"
#include "input_validation.h"

#include <iostream>
#include <fstream>
#include <string>

bool registerUser()
{
    std::string username, password;

    std::cout << "Enter username: ";
    std::cin >> username;

    if (!validUsername(username))
    {
        std::cout << "Invalid username!\n";
        return false;
    }

    std::ifstream input("users.txt");
    std::string u, p, role;

    while (input >> u >> p >> role)
    {
        if (u == username)
        {
            std::cout << "Username already exists!\n";
            return false;
        }
    }
    input.close();

    std::cout << "Enter password: ";
    std::cin >> password;

    if (!validPassword(password))
    {
        std::cout << "Password must be 8+ characters "
                  << "with a letter and a digit.\n";
        return false;
    }

    std::ifstream check("users.txt");
    bool firstUser = !(check >> u);
    check.close();

    std::ofstream output("users.txt", std::ios::app);

    if (!output)
    {
        std::cout << "Cannot save user!\n";
        return false;
    }

    output << username << ' ' << password << ' '
           << (firstUser ? "ADMIN" : "USER") << '\n';

    std::cout << "Registration successful!\n";
    return true;
};