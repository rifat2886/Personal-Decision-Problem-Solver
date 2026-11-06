# Windows 11 build, run এবং runtime test নির্দেশনা

এই নির্দেশনাটি beginner-দের জন্য, কোনো coding জানা লাগবে না।
এটি শুধু আপনার নিজের কম্পিউটারে (localhost) চালানোর জন্য।
Dashboard-কে কখনোই আপনার কম্পিউটার থেকে সরাসরি public internet-এ
খুলবেন না — public site-এর জন্য Vercel + Render + Neon পথটি আলাদা।

## ১. MSYS2 ইনস্টল করুন

1. https://www.msys2.org/ থেকে MSYS2 ইনস্টলার ডাউনলোড করে ইনস্টল করুন।
2. MSYS2 terminal খুলে এই command-টি চালান (একবারই লাগবে):
   ```
   pacman -S mingw-w64-x86_64-gcc
   ```
3. Windows-এর PATH-এ এই folder-টি যোগ করুন:
   ```
   C:\msys64\mingw64\bin
   ```
   PATH যোগ করার পর নতুন একটি Command Prompt / PowerShell খুলে
   যাচাই করুন:
   ```
   g++ --version
   ```
   Version দেখালে ঠিক আছে। না দেখালে PATH ঠিকমতো যোগ হয়নি —
   পুরনো terminal বন্ধ করে নতুন terminal খুলে আবার চেষ্টা করুন।

## ২. Project-টি নামান এবং build করুন

Project folder-এ (যেখানে `start-dashboard.bat` আছে) Command Prompt
খুলে, অথবা folder-এ double-click করে:

- Dashboard-এর জন্য: `start-dashboard.bat`-এ double-click করুন।
  প্রথমবার এটি নিজে থেকে এই command-টি চালিয়ে `cpp_server.exe`
  বানাবে:
  ```
  g++ -std=c++17 -Wall -Wextra -pthread -o cpp_server.exe dashboard\cpp_server.cpp -lws2_32
  ```
- Console app-এর জন্য: `start-console.bat`-এ double-click করুন।
  প্রথমবার এটি এই command-টি চালিয়ে `project.exe` বানাবে:
  ```
  g++ -std=c++17 -Wall -Wextra -o project.exe admin.cpp backup_restore.cpp budget.cpp compare_options.cpp control.cpp daily_decision.cpp deadline_alert.cpp decision_explanation.cpp delete_confirmation.cpp error_handler.cpp export_report.cpp filter_sort.cpp habit.cpp habit_streak.cpp history.cpp income_expense.cpp input_validation.cpp login.cpp logout.cpp main.cpp multi_task_decision.cpp password_change.cpp password_validation.cpp period_report.cpp priority_calculator.cpp problem.cpp profile.cpp registration.cpp report.cpp savings_goal.cpp search_history.cpp study_planner.cpp task_prioritization.cpp task_status.cpp time_allocation.cpp
  ```

Build command যাচাই (2026-11-05, এই round-এ): উপরের দুটি command-ই
MinGW-w64 GCC 13 (MSYS2-তে যে toolchain `pacman -S
mingw-w64-x86_64-gcc` দেয়, তারই cross-compile সংস্করণ) দিয়ে
পরীক্ষা করা হয়েছে। দুটি `PE32+ executable (console) x86-64, for
MS Windows` ফাইল তৈরি হয়েছে, 0 warning-সহ। **এটি build-এর
যাচাই, Windows runtime-এর যাচাই নয় — নিচে দেখুন।**

দ্রষ্টব্য:
- Data folder-এর path-এ বাংলা / non-ASCII অক্ষর থাকলে সমস্যা হতে
  পারে (Windows file-lock code ANSI path ব্যবহার করে)। সহজ path
  ব্যবহার করুন, যেমন `C:\pdps\`।
- Windows Firewall জিজ্ঞেস করলে শুধু **Private** network-এ allow
  করুন, কখনো Public-এ নয়।
- Postgres mode Windows-এ build করলে libpq ছাড়া Postgres support
  compile-out হয়ে txt-only build হবে। এটি স্বাভাবিক; production
  backend Linux Docker-এ চলবে, তাই Windows-এ Postgres দরকার নেই।

## ৩. চালান

1. `start-dashboard.bat` চালু থাকা অবস্থায় browser-এ খুলুন:
   http://127.0.0.1:8000/
2. "Login / Register"-এ গিয়ে প্রথমে Register করুন। **প্রথম
   account-ই ADMIN হবে** — তাই প্রথমে আপনিই register করুন, অন্য
   কাউকে আগে করতে দেবেন না।
3. বন্ধ করতে চাইলে `start-dashboard.bat`-এর window বন্ধ করুন
   অথবা Ctrl+C চাপুন।

## ৪. আসল Windows 11 runtime test checklist

নিচের প্রতিটি item-এ PASS / FAIL লিখে জানান। কোনো item না করলে
সেটি NOT TESTED লিখুন — অনুমান করে PASS লিখবেন না।

- [ ] `start-dashboard.bat` চালু হয়, কোনো error ছাড়া
      `cpp_server.exe` বানাতে পারে (প্রথমবার)।
- [ ] http://127.0.0.1:8000/ খোলে, dashboard-এর Welcome page দেখা যায়।
- [ ] Register করা যায়; প্রথম account ADMIN হয়
      (Profile-এ বা ADMIN list-এ role দেখে যাচাই করুন)।
- [ ] Login / Logout করা যায়; logout-এর পর protected section
      খোলে না, Login page আসে।
- [ ] একটি Task, একটি Decision, একটি Budget entry বানানো যায় এবং
      browser বন্ধ করে আবার খুললে data ঠিক থাকে।
- [ ] দ্বিতীয় user register করলে সে USER হয়, প্রথম user-এর data
      দেখতে পায় না।
- [ ] Backup বানিয়ে, একটি decision মুছে, Restore (confirm দিয়ে)
      করলে শুধু নিজের backup ফিরে আসে।
- [ ] `start-console.bat` চালু হয়; Register (1), Login (2), একটি
      Daily Decision (9) এবং Logout (8) করা যায়।
- [ ] কোনো error হলে তার পুরো লেখাটি (screenshot বা copy-paste)
      জানান, সাথে Windows version (Settings → System → About) এবং
      `g++ --version`-এর আউটপুট।

## ৫. সত্যি কথাটা: কী PASS, কী NOT TESTED

- **Cross-compile (MinGW দিয়ে Windows .exe বানানো): PASS**
  — এই round-এ আবার যাচাই করা হয়েছে, 0 warning।
- **আসল Windows 11-এ runtime: NOT TESTED** — এই VM-এ কোনো আসল
  Windows 11 machine নেই, এবং Wine দিয়ে চালানো Windows test হিসেবে
  গণ্য হবে না। উপরের checklist-টি আসল Windows-এ চালিয়ে
  ফলাফল জানালেই তবেই runtime-কে PASS বলা যাবে। তার আগে কোনো
  রিপোর্টে Windows runtime-কে PASS বলা যাবে না।
- **Windows Postgres build: NOT TESTED** — উপরে বলা হয়েছে,
  production-এর জন্য এটি বাধা নয়।
