#include "export_report.h"
#include "error_handler.h"
#include <iostream>
#include <fstream>

using namespace std;

void exportReportTXT()
{
    // FIX (final audit): check the source BEFORE opening
    // the destination. The old order truncated an existing report
    // file even when transactions.txt was missing, then printed an
    // error, leaving an empty report behind.
    ifstream source("transactions.txt");

    if (!source)
    {
        cout << "Could not open report files!\n";
        logError("exportReportTXT: transactions.txt not found");
        return;
    }

    ofstream destination("financial_report.txt");

    if (!destination)
    {
        cout << "Could not open report files!\n";
        logError("exportReportTXT: could not open financial_report.txt");
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
    // Same fix as exportReportTXT: do not truncate an existing CSV
    // when the source file is missing.
    ifstream source("transactions.txt");

    if (!source)
    {
        cout << "Could not open report files!\n";
        logError("exportReportCSV: transactions.txt not found");
        return;
    }

    ofstream destination("financial_report.csv");

    if (!destination)
    {
        cout << "Could not open report files!\n";
        logError("exportReportCSV: could not open financial_report.csv");
        return;
    }

    destination << "Date,Type,Category,Amount,Note\n";

    string line;

    while (getline(source, line))
    {
        size_t first = line.find('|');
        if (first == string::npos)
            continue;
        size_t second = line.find('|', first + 1);
        if (second == string::npos)
            continue;
        size_t third = line.find('|', second + 1);
        if (third == string::npos)
            continue;
        size_t fourth = line.find('|', third + 1);
        if (fourth == string::npos)
            continue;

        destination << line.substr(0, first) << ','
                    << line.substr(first + 1, second - first - 1) << ','
                    << line.substr(second + 1, third - second - 1) << ','
                    << line.substr(third + 1, fourth - third - 1) << ','
                    << '"' << line.substr(fourth + 1) << '"' << '\n';
    }

    cout << "CSV report exported to financial_report.csv\n";
}
