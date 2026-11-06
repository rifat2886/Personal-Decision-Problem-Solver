#include "input_validation.h"
#include <cstdlib>
#include <iostream>
#include <limits>

bool validUsername(const std::string& username)
{
    if (username.empty())
        return false;

    for (unsigned char ch : username)
    {
        // Security (public launch review, 2026-11-05): same rule as the
        // dashboard servers — a username must be a single safe token, so
        // it can never split a users.txt line or a pipe-delimited record.
        if (ch <= ' ' || ch == '|')
            return false;
    }

    return true;
}

int getValidNumber(int minimum, int maximum)
{
    int number;

    while (true)
    {
        std::cout << "Enter number (" << minimum
                  << "-" << maximum << "): ";

        if (std::cin >> number &&
            number >= minimum && number <= maximum)
            return number;

        // FIX (final audit): on end-of-file, the old
        // loop cleared the stream and retried forever, flooding
        // output. Exiting is the only sane response to closed stdin.
        if (std::cin.eof())
        {
            std::cout << "\nInput closed. Exiting.\n";
            std::exit(0);
        }

        std::cout << "Invalid input! Try again.\n";

        std::cin.clear();
        std::cin.ignore(
            std::numeric_limits<std::streamsize>::max(), '\n'
        );
    }
}