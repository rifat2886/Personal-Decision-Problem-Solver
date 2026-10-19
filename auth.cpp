#include "auth.h"
#include <iostream>
#include <fstream>
#include <string>
using namespace std;

bool registerOrLogin(string& currentUser, bool& isAdmin) {
    int choice;
    string username, password, u, p, role;

    cout << "\n1. Register\n2. Login\nChoose: ";
    cin >> choice;

    cout << "Username: ";
    cin >> username;

    cout << "Password: ";
    cin >> password;

    if (choice == 1) {
        ifstream check("users.txt");

        while (check >> u >> p >> role) {
            if (u == username) {
                cout << "Username already exists!\n";
                return false;
            }
        }
        check.close();

        string newRole = "USER";
        ifstream existing("users.txt");
        bool hasUser = static_cast<bool>(existing >> u >> p >> role);
        existing.close();

        if (!hasUser)
            newRole = "ADMIN";

        ofstream out("users.txt", ios::app);
        out << username << ' ' << password << ' '
            << newRole << '\n';
        out.close();

        cout << "Registration successful!\n";
        cout << "Please login to continue.\n";
        return false;
    }

    if (choice == 2) {
        ifstream in("users.txt");

        while (in >> u >> p >> role) {
            if (u == username && p == password) {
                currentUser = username;
                isAdmin = (role == "ADMIN");

                cout << "Login successful!\n";
                return true;
            }
        }

        cout << "Invalid username or password.\n";
        return false;
    }

    cout << "Invalid choice.\n";
    return false;
}

void changePassword(const string& currentUser) {
    cout << "Password change will be implemented "
         << "after secure password storage is added.\n";
}
