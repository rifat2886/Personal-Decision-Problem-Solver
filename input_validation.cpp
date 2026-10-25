#include "input_validation.h"
#include <iostream>
#include <limits>

bool validUsername(const std::string& username)
{
    if (username.empty())
        return false;

    for (char ch : username)
    {
        if (ch == ' ')
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

        std::cout << "Invalid input! Try again.\n";

        std::cin.clear();
        std::cin.ignore(
            std::numeric_limits<std::streamsize>::max(), '\n'
        );
    }
}