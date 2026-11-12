# Demo Runbook — kalke (10 November) sir er samne

Ei file ta apnar jonno — PC te demo deoar step-by-step. Proti step e ekta command
chalaben, result dekhe tarpor porer step e jaben. Kono step e atke gele oi
step er "jodi na hoy" ongsho ta porben.

## Age theke ja lagbe

- ZIP file: `Personal-Decision-Problem-Solver-Phase4-182e74e-demo-ready.zip` (Muse dibe)
- Apnar PC te MSYS2 + g++ age thekei ache (6 November e test kora hoyeche)
- Gemini API key (Google AI Studio theke) — sudhu apnar PC te lagbe, chat e na
- Neon database er connection string (Neon console theke) — sudhu apnar PC te lagbe

## Step 0 — ZIP khulun

1. ZIP file ta `Downloads` theke khulun (Extract). Folder er nam hobe
   `Personal-Decision-Problem-Solver-Phase4-182e74e`.
2. Oi folder ta khule PowerShell khulun (folder er khali jaygay right-click
   → "Open in Terminal" ba address bar e `powershell` likhe Enter).

## Step 1 — proyojonio package install korun (ekbar e)

PowerShell e ei command ta chalaben:

```powershell
pacman -S --noconfirm mingw-w64-ucrt-x86_64-curl mingw-w64-ucrt-x86_64-postgresql
```

Ei command ta MSYS2 UCRT64 terminal e chalaben (Start menu → MSYS2 UCRT64).
MINGW64 terminal e chalale package er nam milbe na.

Eta MSYS2 te libcurl (Gemini AI er jonno) ar libpq (Neon database er jonno)
install korbe. Seshe `g++ --version` chaliye dekhben version dekhay kina.

- Jodi install na hoy: AI ar Neon database chara demo dite hobe (Step 3 er
  "TXT mode" onusare). AI feature tokhon "not configured" dekhabe — eta
  age thekei bole rakhben.

- Build e jodi `undefined reference to curl_easy_...` ba `PQconnectdb`
  lekha ashe: notun `.bat` nijei g++ er pashe curl khuje ney, tai ei
  error ar ashar kotha na. Tobuo ele: UCRT64 terminal e oi folder e
  giye `mingw32-make` chalaben, othoba uporer pacman command ta abar
  chaliye `cpp_server.exe` muche abar build korben.

## Step 2 — key ar database address boshano (apnar PC te, sudhu ei session er jonno)

PowerShell e (ekta ekta kore, alada alada):

```powershell
$env:GEMINI_API_KEY = "PASTE_YOUR_KEY_HERE"
```

Key er jaygay apnar asol Gemini key ta paste korben (AI Studio theke copy kore).
Tarpor:

```powershell
$env:DATABASE_URL = "PASTE_NEON_CONNECTION_STRING_HERE"
```

Neon console (console.neon.tech → project "pdps" → Connection Details) theke
pooled connection string ta "Copy snippet" diye copy kore ekhane paste korben.

- Ei duto command sudhu ei PowerShell window er jonno kaj korbe. Window bondho
  korle muche jabe — kono file e save hobe na.
- Jodi DATABASE_URL na boshate chan: kichu na boshalei hobe — tokhon TXT mode
  e cholbe (console ar website eki txt file share korbe, 6 November e jemon
  choleche). Kintu tokhon Neon online database er demo hobe na.

## Step 3 — Dashboard chalu korun

```powershell
.\start-dashboard.bat
```

Seshe browser e khulben: `http://127.0.0.1:8000/`

- Dashboard khullei prothome **Register** korben — prothom account tai ADMIN
  hobe. Onno keu age register korle se ADMIN hoye jabe, tai apni age korben.
- Register form e password duibar likhte hobe (Password + Confirm password) —
  duibar eki password likhben; na mille "Passwords do not match" dekhabe.
- Jodi `GEMINI_API_KEY` boshano thake, AI section gulo kaj korbe. Na thakle
  AI te "not configured" dekhabe.

## Step 4 — Console chalu korun (alada PowerShell window e)

Notun PowerShell window khule oi eki folder e giye:

```powershell
.\start-console.bat
```

Tarpor console e login korben (Step 3 er eki username/password). Menu 18
(Show Balance) e Income/Expense/Balance dashboard er sathe miliye dekhaben —
dui jaygay eki number asha mane console ar website eki database use korche.

## Step 5 — Demo er krom (suggestion)

1. Login (ADMIN account)
2. Daily Decision — ekta siddhanto nin, score dekhun
3. Task — task jog korun
4. Budget — income/expense din, balance dekhun
5. Priority — priority score dekhun
6. Habit — habit log korun, streak dekhun
7. Savings — savings goal dekhun
8. Weekly Report
9. Compare Options
10. Problem Solver
11. AI Assistant (6 ta feature, ekta ekta kore) + AI History
12. Admin Panel — user list dekhun (sudhu username/role, kono password na)

## Jodi kichu na chole

- Dashboard na khulle: PowerShell e error ta porben. `port already in use`
  dekhale ager server ta bondho kore abar chalaben.
- AI "not configured" dekhale: Step 2 er key ta boshano hoyeche kina dekhben,
  tarpor server ta bondho kore abar chalaben (key boshale server restart lage).
- Database error dekhale: Step 2 er DATABASE_URL ta thik moto paste hoyeche
  kina dekhben. Na hole DATABASE_URL charai chalaben (TXT mode) — demo cholbe.
- Render/Vercel er kono link demo te dekhaben na — online backend ekhon nei
  (Render card chay). Demo purotai apnar PC te (localhost) cholbe.

## Backup (demo er age)

Demo er age data file gulo alada folder e copy kore rakhben (backup). Neon
database use korle data Neon e thakbe; TXT mode e thakle data file gulo
(`decisions.txt`, `tasks.txt`, ityadi) folder ei thakbe.
