#include "admin.h"
#include <iostream>
#include <fstream>
#include <string>
using namespace std;

void adminPanel() {
    ifstream in("users.txt");

    if (!in) {
        cout << "No user data found.\n";
        return;
    }

    string username, password, role;

    cout << "\n===== ADMIN PANEL =====\n";
    cout << "Registered Users:\n";

    while (in >> username >> password >> role) {
        cout << "Username: " << username
             << " | Role: " << role << '\n';
    }

    in.close();
}
