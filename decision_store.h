#ifndef DECISION_STORE_H
#define DECISION_STORE_H

#include "file_lock.h"
#include <fstream>
#include <string>

// Shared decision store used by the menu modules.
// Format (one record per line, as expected by filter_sort.cpp and
// delete_confirmation.cpp):
//   id|date|type|priority|title
// The date field is "-" when the caller has no date. Titles and types
// are sanitised so a user-supplied '|' cannot break the format.
inline void appendDecisionRecord(const std::string& type,
                                 int priority,
                                 const std::string& title)
{
    // Hold the decisions lock for the whole count-then-append, so
    // a dashboard write cannot interleave and duplicate an id.
    // The dashboard C++ server uses the same lock file.
    FileLock lock("decisions.txt");
    std::string safeType = type;
    std::string safeTitle = title;
    for (char& ch : safeType)
        if (ch == '|' || ch == '\n')
            ch = '/';
    for (char& ch : safeTitle)
        if (ch == '|' || ch == '\n')
            ch = '/';

    std::ifstream input("decisions.txt");
    int count = 0;
    std::string line;
    while (std::getline(input, line))
        ++count;
    input.close();

    std::ofstream file("decisions.txt", std::ios::app);
    if (file)
        file << (count + 1) << "|-" << '|' << safeType << '|'
             << priority << '|' << safeTitle << '\n';
}

#endif
