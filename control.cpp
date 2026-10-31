#include "control.h"
#include "history.h"
#include <iostream>
#include <limits>
using namespace std;

// Feature 12: Control Panel
void controlPanel() {
    int choice = -1;

    do {
        cout << "\n===== CONTROL PANEL =====\n";
        cout << "1. View Decision History\n";
        cout << "2. Search History\n";
        cout << "3. Filter and Sort History\n";
        cout << "4. Backup History\n";
        cout << "5. Restore History\n";
        cout << "6. Delete History\n";
        cout << "0. Back to Main Menu\n";
        cout << "Enter choice: ";

        if (!(cin >> choice)) {
            cin.clear();
            cin.ignore(
                numeric_limits<streamsize>::max(), '\n'
            );

            cout << "Invalid input! Enter a number.\n";
            continue;
        }

        switch (choice) {
            case 1:
                decisionHistory();
                break;

            case 2:
                searchHistory();
                break;

            case 3:
                filterSortHistory();
                break;

            case 4:
                backupHistory();
                break;

            case 5:
                restoreHistory();
                break;

            case 6:
                deleteHistory();
                break;

            case 0:
                cout << "Returning to Main Menu.\n";
                break;

            default:
                cout << "Invalid choice!\n";
        }

    } while (choice != 0);
}
