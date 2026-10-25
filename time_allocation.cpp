#include "time_allocation.h"
#include "input_validation.h"

#include <iostream>

void timeAllocation()
{
    int sleep, study, work, other;

    std::cout << "\n===== TIME ALLOCATION =====\n";

    std::cout << "Sleep hours:\n";
    sleep = getValidNumber(0, 24);

    std::cout << "Study hours:\n";
    study = getValidNumber(0, 24);

    std::cout << "Work hours:\n";
    work = getValidNumber(0, 24);

    std::cout << "Other activity hours:\n";
    other = getValidNumber(0, 24);

    int total = sleep + study + work + other;

    std::cout << "Total allocated: " << total << " hours\n";

    if (total > 24)
        std::cout << "Warning: Total exceeds 24 hours!\n";
    else
        std::cout << "Remaining: " << 24 - total << " hours\n";
}