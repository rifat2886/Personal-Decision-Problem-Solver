#ifndef AUTH_H
#define AUTH_H

#include <string>
using namespace std;

bool registerOrLogin(string& currentUser, bool& isAdmin);
void changePassword(const string& currentUser);

#endif
