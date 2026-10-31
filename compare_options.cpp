#include "compare_options.h"
#include <iostream>
#include <string>
using namespace std;

void compareOptions() {
    string name[2];
    int benefit[2], cost[2], risk[2], score[2];

    cout << "\n===== COMPARE OPTIONS =====\n";

    for (int i = 0; i < 2; i++) {
        cout << "\nOption " << i + 1 << " name: ";
        getline(cin >> ws, name[i]);

        cout << "Benefit (1-10): ";
        if (!(cin >> benefit[i]) ||
            benefit[i] < 1 || benefit[i] > 10) {
            cout << "Invalid benefit!\n";
            cin.clear();
            cin.ignore(10000, '\n');
            return;
        }

        cout << "Cost (1-10): ";
        if (!(cin >> cost[i]) || cost[i] < 1 || cost[i] > 10) {
            cout << "Invalid cost!\n";
            cin.clear();
            cin.ignore(10000, '\n');
            return;
        }

        cout << "Risk (1-10): ";
        if (!(cin >> risk[i]) || risk[i] < 1 || risk[i] > 10) {
            cout << "Invalid risk!\n";
            cin.clear();
            cin.ignore(10000, '\n');
            return;
        }

        score[i] = benefit[i] * 3 - cost[i] - risk[i];
    }

    cin.ignore(10000, '\n');

    cout << "\n" << name[0] << " Score: " << score[0] << '\n';
    cout << name[1] << " Score: " << score[1] << '\n';

    if (score[0] > score[1])
        cout << "Suggested option: " << name[0] << '\n';
    else if (score[1] > score[0])
        cout << "Suggested option: " << name[1] << '\n';
    else
        cout << "Both options have equal scores.\n";
}
