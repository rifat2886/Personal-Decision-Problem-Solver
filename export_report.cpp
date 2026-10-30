#include "export_report.h"
#include <iostream>
#include <fstream>

using namespace std;

void exportReportTXT()
{
    ifstream source("transactions.txt");
    ofstream destination("financial_report.txt");

    if (!source || !destination)
    {
        cout << "Could not open report files!\n";
        return;
    }

    destination << "PERSONAL FINANCIAL REPORT\n";
    destination << "========================\n\n";

    string line;

    while (getline(source, line))
        destination << line << '\n';

    cout << "TXT report exported to financial_report.txt\n";
}

void exportReportCSV()
{
    ifstream source("transactions.txt");
    ofstream destination("financial_report.csv");

    if (!source || !destination)
    {
        cout << "Could not open report files!\n";
        return;
    }

    destination << "Date,Type,Category,Amount,Note\n";

    string line;

    while (getline(source, line))
    {
        size_t first = line.find('|');
        size_t second = line.find('|', first + 1);
        size_t third = line.find('|', second + 1);
        size_t fourth = line.find('|', third + 1);

        if (first == string::npos ||
            second == string::npos ||
            third == string::npos ||
            fourth == string::npos)
            continue;

        destination << line.substr(0, first) << ','
                    << line.substr(first + 1, second - first - 1) << ','
                    << line.substr(second + 1, third - second - 1) << ','
                    << line.substr(third + 1, fourth - third - 1) << ','
                    << '"' << line.substr(fourth + 1) << '"' << '\n';
    }

    cout << "CSV report exported to financial_report.csv\n";
}
