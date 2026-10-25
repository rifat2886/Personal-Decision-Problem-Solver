#include "study_planner.h"
#include "input_validation.h"

#include <iostream>
#include <string>

void studyPlanner()
{
    std::string subject;
    int days, hours;

    std::cout << "\n===== STUDY PLANNER =====\n";

    std::cout << "Enter subject name (one word): ";
    std::cin >> subject;

    std::cout << "Enter number of days:\n";
    days = getValidNumber(1, 365);

    std::cout << "Study hours per day:\n";
    hours = getValidNumber(1, 24);

    std::cout << "\n===== YOUR PLAN =====\n";

    for (int day = 1; day <= days; day++)
    {
        std::cout << "Day " << day << ": "
                  << subject << " - "
                  << hours << " hour(s)\n";
    }

    std::cout << "Total planned hours: "
              << days * hours << '\n';
}