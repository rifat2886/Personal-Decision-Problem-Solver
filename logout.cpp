#include "logout.h"
#include <iostream>

void logoutUser(
    std::string& currentUser,
    bool& isAdmin,
    bool& loggedIn
)
{
    currentUser.clear();
    isAdmin = false;
    loggedIn = false;

    std::cout << "Logout successful!\n";
}

bool exitProgram(int choice)
{
    return choice == 0;
}