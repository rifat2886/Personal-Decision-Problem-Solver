#include "login.h"
#include "file_lock.h"
#include "password_hash.h"

#include <iostream>
#include <fstream>
#include <string>
#include <vector>

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
        if (u == username && pdps_hash::verifyPassword(password, p))
        {
            currentUser = u;
            isAdmin = (role == "ADMIN");

            // Backward-compatible migration: a plaintext credential
            // that just matched is rewritten as a hash, under lock.
            // After this login, no plaintext remains for this user.
            if (!pdps_hash::isHashed(p))
            {
                FileLock lock("users.txt");
                std::ifstream in("users.txt");
                std::vector<std::string> records;
                std::string ru, rp, rr;
                while (in >> ru >> rp >> rr)
                {
                    if (ru == username)
                        rp = pdps_hash::hashPassword(password);
                    records.push_back(ru + " " + rp + " " + rr);
                }
                in.close();
                std::ofstream out("users.txt");
                for (const auto& r : records) out << r << '\n';
            }

            std::cout << "Login successful!\n";
            return true;
        }
    }

    std::cout << "Invalid username or password!\n";
    return false;
}