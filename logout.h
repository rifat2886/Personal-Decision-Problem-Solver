#ifndef LOGOUT_H
#define LOGOUT_H

#include <string>

void logoutUser(
    std::string& currentUser,
    bool& isAdmin,
    bool& loggedIn
);

bool exitProgram(int choice);

#endif