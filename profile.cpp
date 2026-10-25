#include "profile.h"
#include <iostream>

void showProfile(const std::string& username, bool isAdmin)
{
    std::cout << "\n===== MY PROFILE =====\n";
    std::cout << "Username: " << username << '\n';
    std::cout << "Role: "
              << (isAdmin ? "ADMIN" : "USER") << '\n';
}