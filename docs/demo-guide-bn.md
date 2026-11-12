# ডেমো গাইড — Personal Decision & Problem Solver

**তারিখ:** ১০ নভেম্বর ২০২৬ | **ডেমো:** নিজের PC-তে (localhost) + Neon অনলাইন ডেটাবেস + আসল Gemini AI

এই গাইডে যা আছে, তা-ই করলেই ডেমো চলবে। এক ধাপ শেষ করে ফলাফল দেখে পরের
ধাপে যাবেন। কোনো ধাপে আটকে গেলে নিচের **সমস্যা সমাধান** অংশটি দেখুন।

---

## যা যা লাগবে

- ZIP ফাইল: `Personal-Decision-Problem-Solver-Phase4-182e74e-demo-ready.zip` (Muse দেবে)
- PC-তে MSYS2 + g++ (আগে থেকেই আছে)
- Gemini API key (Google AI Studio থেকে) — শুধু আপনার PC-তে লাগবে, চ্যাটে নয়
- Neon ডেটাবেসের connection string (Neon console থেকে) — শুধু আপনার PC-তে লাগবে

---

## ধাপ ১ — ZIP খুলুন

1. ZIP ফাইলটি `Downloads` থেকে Extract করুন।
2. যে ফোল্ডারটি তৈরি হবে, সেটি খুলুন।
3. ফোল্ডারের খালি জায়গায় right-click করে **"Open in Terminal"** চাপুন,
   অথবা address bar-এ `powershell` লিখে Enter চাপুন।

## ধাপ ২ — প্রয়োজনীয় প্যাকেজ ইনস্টল করুন (একবারই)

PowerShell-এ এই কমান্ডটি চালান:

```powershell
pacman -S --noconfirm mingw-w64-ucrt-x86_64-curl mingw-w64-ucrt-x86_64-postgresql
```

এই কমান্ডটি MSYS2 UCRT64 টার্মিনালে চালাবেন (Start menu → MSYS2 UCRT64)।
MINGW64 টার্মিনালে চালালে প্যাকেজের নাম মিলবে না।

এটি MSYS2-এ `libcurl` (Gemini AI-এর জন্য) এবং `libpq` (Neon ডেটাবেসের জন্য)
ইনস্টল করবে। শেষে `g++ --version` চালিয়ে দেখুন — version দেখালে ঠিক আছে।

- ইনস্টল না হলে: AI ও Neon ছাড়া ডেমো দিতে হবে (নিচের "TXT মোড" দেখুন)।
  তখন AI সেকশনে "not configured" দেখাবে — এটি আগেই স্যারকে বলে রাখবেন।

## ধাপ ৩ — Key ও ডেটাবেসের ঠিকানা বসানো (আপনার PC-তে, শুধু এই সেশনের জন্য)

PowerShell-এ একটা একটা করে চালান:

```powershell
$env:GEMINI_API_KEY = "PASTE_YOUR_KEY_HERE"
```

Key-এর জায়গায় আপনার আসল Gemini key পেস্ট করবেন (AI Studio থেকে কপি করে)।
তারপর:

```powershell
$env:DATABASE_URL = "PASTE_NEON_CONNECTION_STRING_HERE"
```

Neon console (console.neon.tech → project "pdps" → Connection Details) থেকে
pooled connection string "Copy snippet" দিয়ে কপি করে এখানে পেস্ট করবেন।

- এই দুটি কমান্ড শুধু এই PowerShell উইন্ডোর জন্য কাজ করবে। উইন্ডো বন্ধ
  করলে মুছে যাবে — কোনো ফাইলে save হবে না।
- `DATABASE_URL` না বসালে TXT মোডে চলবে (console ও website একই txt ফাইল
  share করবে)। তখন Neon অনলাইন ডেটাবেসের ডেমো হবে না।

## ধাপ ৪ — Dashboard চালু করুন

```powershell
.\start-dashboard.bat
```

তারপর ব্রাউজারে খুলুন: `http://127.0.0.1:8000/`

- Dashboard খুললেই প্রথমে **Register** করবেন — প্রথম অ্যাকাউন্টটিই ADMIN হবে।
  অন্য কেউ আগে register করলে সে ADMIN হয়ে যাবে, তাই আপনি আগে করবেন।
- Register ফর্মে password দুইবার লিখতে হবে (Password + Confirm password) —
  দুইবার একই password লিখবেন; না মিললে "Passwords do not match" দেখাবে।
- `GEMINI_API_KEY` বসানো থাকলে AI সেকশনগুলো কাজ করবে। না থাকলে AI-তে
  "not configured" দেখাবে।

## ধাপ ৫ — Console চালু করুন (আলাদা PowerShell উইন্ডোতে)

নতুন PowerShell উইন্ডো খুলে একই ফোল্ডারে গিয়ে:

```powershell
.\start-console.bat
```

তারপর console-এ login করবেন (ধাপ ৪-এর একই username/password)। Menu 18
(Show Balance)-এ Income/Expense/Balance dashboard-এর সাথে মিলিয়ে দেখাবেন —
দুই জায়গায় একই সংখ্যা আসা মানে console ও website একই ডেটাবেস ব্যবহার করছে।

## ধাপ ৬ — ডেমোর ক্রম (সাজেশন)

1. Login (ADMIN অ্যাকাউন্ট)
2. Daily Decision — একটি সিদ্ধান্ত নিন, score দেখুন
3. Task — task যোগ করুন
4. Budget — income/expense দিন, balance দেখুন
5. Priority — priority score দেখুন
6. Habit — habit log করুন, streak দেখুন
7. Savings — savings goal দেখুন
8. Weekly Report
9. Compare Options
10. Problem Solver
11. AI Assistant (৬টি ফিচার, একটা একটা করে) + AI History
12. Admin Panel — user list দেখুন (শুধু username/role, কোনো password নয়)

## ধাপ ৭ — ডেমো শেষে

- Logout করুন।
- ডেটা Neon-এ থাকলে সেখানেই থাকবে; TXT মোডে থাকলে data ফাইলগুলো
  (`decisions.txt`, `tasks.txt` ইত্যাদি) ফোল্ডারেই থাকবে।
- ডেমোর আগে data ফাইলগুলোর একটি কপি আলাদা ফোল্ডারে রেখে দিন (backup)।

---

## সমস্যা সমাধান (Troubleshooting)

| সমস্যা | কারণ | সমাধান |
|---|---|---|
| `.\start-dashboard.bat` চালালে কিছুই হয় না / সাথে সাথে বন্ধ হয়ে যায় | g++ পাওয়া যাচ্ছে না, অথবা build-এ error | PowerShell-এ `g++ --version` চালান। না দেখালে MSYS2-এর `mingw64.exe` থেকে PowerShell খুলে আবার চেষ্টা করুন। |
| `port already in use` / `Address already in use` | আগের server এখনো চলছে | আগের PowerShell উইন্ডোতে Ctrl+C চেপে server বন্ধ করুন, তারপর আবার চালান। |
| Dashboard খুলছে না (`127.0.0.1:8000` লোড হয় না) | server চালু হয়নি বা ভুল port | PowerShell-এ server-এর শেষ লাইনগুলো পড়ুন। `Listening` / `port 8000` লেখা থাকতে হবে। না থাকলে ধাপ ৪ আবার করুন। |
| AI-তে "not configured" / "AI unavailable" দেখায় | Key বসানো হয়নি, অথবা server key বসানোর আগে চালু হয়েছে | ধাপ ৩-এ key বসিয়েছেন কি না দেখুন। তারপর server বন্ধ করে (Ctrl+C) আবার চালান — key বসালে server restart লাগে। |
| AI-তে 503 / 502 error | Gemini সার্ভার ব্যস্ত, অথবা মডেলের সমস্যা | কয়েক সেকেন্ড পরে আবার চেষ্টা করুন। না হলে `$env:GEMINI_MODEL = "gemini-3-flash-preview"` বসিয়ে server restart করুন। |
| `DATABASE_URL` দিলে server সাথে সাথে বন্ধ হয়ে যায় | ডেটাবেসে সংযোগ হচ্ছে না (ভুল ঠিকানা / ইন্টারনেট নেই) | ঠিকানাটি ঠিকমতো paste হয়েছে কি না দেখুন। না হলে `DATABASE_URL` ছাড়াই চালান (TXT মোড) — ডেমো চলবে। |
| build-এ `undefined reference to curl_easy_...` / `PQconnectdb` | প্যাকেজ ইনস্টল আছে কিন্তু build তা খুঁজে পায়নি (ভুল terminal / PATH) | নতুন `.bat` নিজেই g++-এর পাশে curl খুঁজে নেয়, তাই এই error আর আসার কথা নয়। তবুও এলে: **MSYS2 UCRT64** terminal-এ ওই folder-এ গিয়ে `mingw32-make` চালান, অথবা ধাপ ২-এর `pacman` কমান্ড আবার চালিয়ে `cpp_server.exe` মুছে আবার build করুন। |
| Login হচ্ছে না / "Invalid credentials" | ভুল username/password, অথবা অন্য ডেটাবেসে অ্যাকাউন্ট | যে ডেটাবেসে (Neon বা TXT) register করেছিলেন, সেই একই মোডে login করুন। Neon ও TXT-এর অ্যাকাউন্ট আলাদা। |
| Console-এ "Please login first" দেখায় | Console-এ login করা হয়নি | Console-এ Menu 2 (Login) দিয়ে আগে login করুন, তারপর Menu 9–43 ব্যবহার করুন। |
| Console ও dashboard-এর balance মিলছে না | দুটি আলাদা ডেটাবেসে চলছে (একটি Neon, একটি TXT) | দুই জায়গায় একই `DATABASE_URL` বসানো আছে কি না দেখুন। দুটোতেই একই মোডে চালাতে হবে। |
| Dashboard-এ লাল banner "Backend is not connected" | Vercel-এর ওয়েবসাইট খুলেছেন (সেখানে backend নেই) | Vercel লিংক নয় — `http://127.0.0.1:8000/` খুলুন। ডেমো localhost-এই চলবে। |
| ব্রাউজারে 404 / খালি পাতা | ভুল ঠিকানা | ঠিকানা ঠিক আছে কি না দেখুন: `http://127.0.0.1:8000/` (শেষে `/` সহ)। |

## জরুরি নিয়ম

- **Key কখনো চ্যাটে, ইমেইলে বা কোনো ফাইলে লিখবেন না।** শুধু নিজের PC-র
  PowerShell-এ বসাবেন।
- **প্রথমে নিজে register করবেন** — প্রথম অ্যাকাউন্টটিই ADMIN হয়।
- **Render-এর কোনো লিংক ডেমোতে দেখাবেন না** — অনলাইন backend এখন নেই
  (Render card চায়)। ডেমো পুরোটাই আপনার PC-তে চলবে।
- ডেমোর আগে backup নিন — data ফাইলগুলো আলাদা ফোল্ডারে কপি করে রাখুন।
