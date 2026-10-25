#include "password_validation.h"

bool validPassword(const std::string& password)
{
    if (password.length() < 8)
        return false;

    bool letter = false;
    bool digit = false;

    for (char ch : password)
    {
        if ((ch >= 'A' && ch <= 'Z') ||
            (ch >= 'a' && ch <= 'z'))
            letter = true;

        if (ch >= '0' && ch <= '9')
            digit = true;
    }

    return letter && digit;
}