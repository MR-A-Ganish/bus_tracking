# Smart College Bus Tracking and Transportation Management System

A complete, working final-year project: Flask + MySQL backend, a real
Machine-Learning ETA prediction model, simulated GPS bus tracking, QR-code
attendance, college-entry geofence detection, route optimization, and
separate Student / Management dashboards.

This is a **prototype** built for a final-year project review — the ETA
model is trained on generated sample data (clearly labeled as such), and
GPS/geofencing is simulated. Every part of the code is structured so real
GPS hardware or real historical data can be dropped in later without
rewriting the architecture.

---

## 1. What's actually implemented (no faked features)

| Feature | How it works |
|---|---|
| Login + roles | MySQL `users` table, hashed passwords, Flask sessions — every student and admin has their own real account, not just a fixed demo pair |
| Admin management panel | Admin dashboard has full CRUD (add/edit/delete) for students, buses, and other admin accounts, with bus↔stop assignment — `backend/routes/admin.py` |
| Live tracking map | Interactive Leaflet/OpenStreetMap view showing each bus's marker moving in real time along the actual route, computed by interpolating its simulated GPS progress between stops (`backend/routes/buses.py`) |
| Bus tracking | Background Python thread updates `bus_locations` in MySQL every 2s; frontend polls the API |
| AI ETA prediction | Real `scikit-learn` RandomForestRegressor trained on generated data (`backend/ai/eta_model.py`), served via `/api/eta/predict` |
| QR attendance | Real QR codes generated server-side (`qrcode` library) and scanned in-browser via device camera (`html5-qrcode`), with a manual-entry fallback |
| College-entry detection | Simulated geofence check (`backend/services/geofence.py`) comparing simulated distance to the college stop's distance |
| Route optimization | Dijkstra's shortest-path algorithm over alternate road segments (`backend/services/route_optimizer.py`) |
| Database | Real MySQL, 11 tables, Flask talks to it directly via `mysql-connector-python` (no in-memory-only data) |
| Notifications | Rows written to a MySQL `notifications` table by real system events (bus started, approaching stop, boarding, delay, college entry, capacity warning) |

The frontend (`frontend/`) is a redesigned, responsive dashboard (Inter font,
card-based layout, live badges/animations) rather than a bare prototype UI.
The live map uses OpenStreetMap tiles over the internet (no API key needed)
— the rest of the app works fully offline once loaded.

---

## 2. Prerequisites (Windows)

Install these once:

1. **Python 3.10+** — https://www.python.org/downloads/ (tick "Add Python to PATH" during install)
2. **MySQL Server** — easiest is MySQL Installer: https://dev.mysql.com/downloads/installer/
   During setup, set a root password and remember it (or leave it blank for a local dev setup).
3. **VS Code** — https://code.visualstudio.com/
4. **Git** (optional, only if you want version control) — https://git-scm.com/

---

## 3. Project structure

```
SmartCollegeBusSystem/
├── backend/
│   ├── app.py                  # Flask entry point - run this
│   ├── config.py               # DB credentials & simulation settings - EDIT THIS
│   ├── database.py             # MySQL connection helper
│   ├── seed.py                 # Creates demo login accounts - run once after schema
│   ├── routes/                 # API endpoints (auth, buses, eta, attendance, admin...)
│   ├── services/                # bus_simulation.py, geofence.py, route_optimizer.py, notification_service.py
│   └── ai/
│       ├── eta_model.py        # trains + serves the ML ETA model
│       └── training_data.csv   # auto-generated on first run
├── frontend/
│   ├── index.html              # Login page
│   ├── student.html            # Student dashboard
│   ├── admin.html              # Management dashboard
│   ├── css/style.css
│   └── js/ (login.js, student.js, admin.js)
├── database/
│   └── schema.sql              # Run this in MySQL first
├── requirements.txt
└── README.md                   # (this file)
```

---

## 4. Setup — exact steps

Open the project folder in VS Code (`File > Open Folder...`), then open a
terminal in VS Code (`` Ctrl + ` ``) and run the following, in order.

### Step 1 — Create a virtual environment and install dependencies

```powershell
cd SmartCollegeBusSystem
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

You should see `(venv)` appear at the start of your terminal prompt once
the virtual environment is active.

### Step 2 — Create the database

Open a terminal and run (you'll be prompted for your MySQL root password):

```powershell
mysql -u root -p < database\schema.sql
```

If `mysql` isn't recognized, add MySQL's `bin` folder to your PATH (typically
`C:\Program Files\MySQL\MySQL Server 8.0\bin`), or use the full path:

```powershell
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u root -p < database\schema.sql
```

This creates the `smart_bus_system` database, all 11 tables, and sample
buses/stops/routes.

### Step 3 — Configure your database password

Open `backend/config.py` and set your MySQL root password:

```python
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "YOUR_MYSQL_PASSWORD_HERE",
    "database": "smart_bus_system",
}
```

(Alternatively, set environment variables `DB_USER` / `DB_PASSWORD` instead
of editing the file.)

### Step 4 — Create the demo login accounts

```powershell
cd backend
python seed.py
```

This creates the demo accounts and sample student→bus→stop assignments.
Safe to re-run any time to reset the demo data.

### Step 5 — Train the ETA model (optional — happens automatically too)

```powershell
python ai\eta_model.py
```

This generates `training_data.csv` and `eta_model.joblib`. If you skip this
step, the first API call to `/api/eta/predict` will train it automatically.

### Step 6 — Run the server

```powershell
python app.py
```

You should see:
```
Smart College Bus System backend running at http://127.0.0.1:5000
```

### Step 7 — Open the app

Open your browser to **http://127.0.0.1:5000**

---

## 5. Demo accounts

| Role | Username | Password | Notes |
|---|---|---|---|
| Student | `student01` | `1234` | Priya R — Bus 01, stop: Kandamangalam |
| Student | `student02` | `1234` | Arun K — Bus 01, stop: Thirunavalur |
| Admin | `admin01` | `admin123` | Transport Officer |

These three are seeded by `seed.py` so the login page always has something
to demo out of the box. Every other student/admin account is created and
managed from the **Management dashboard → Students / Buses / Admins** tabs
(add, edit, delete) — there's no limit on how many real accounts you create.

---

## 6. How to demo the full flow

1. Log in as **admin01** in one browser tab.
2. In the Management dashboard's **Overview** tab, click **Start** next to Bus 01.
3. Open the **Fleet Map** tab to watch Bus 01's marker move live on the map.
4. Open a second (private/incognito) browser window and log in as **student01**.
5. Watch the Student dashboard: the live map shows the bus moving along the
   route, the bus's status changes (moving → arrived at stop → waiting →
   moving), and the ETA to Kandamangalam updates live from the trained ML
   model.
6. When the bus reaches Kandamangalam, go to `http://127.0.0.1:5000/api/buses/1/qr-code-text`
   in a browser tab logged in as the student (or use the "Scan QR with Camera"
   button and point it at the QR image from `/api/buses/1/qr`) to board.
   You can also just paste the QR text into the manual fallback field on the
   student dashboard.
7. Watch the passenger count update, and check the Management dashboard's
   Attendance tab and Notifications panel.
8. Let the simulation continue — when Bus 01 reaches IFET College, the
   Management dashboard's "College Entries Today" counter and notification
   feed will show `"Bus 01 has entered IFET College at ..."`.
9. Try the **Management dashboard → Students** tab: add a brand-new student
   account, assign them to a bus/stop, then log in as that student in another
   window to show the account is fully live.

---

## 7. Notes on the AI ETA model (for your project review)

- Real bus-GPS history isn't available for a student project, so
  `backend/ai/eta_model.py` **generates a synthetic training dataset**
  (`generate_training_data()`) using a physics-based formula (distance ÷
  speed, scaled by a traffic delay factor, plus per-stop boarding time and
  random noise) — this mimics how real travel time behaves.
- A `RandomForestRegressor` (scikit-learn) is trained on that data with an
  80/20 train/test split. On a typical run it achieves roughly 2–3 minutes
  Mean Absolute Error on the held-out test set — printed to the console when
  you run `python ai/eta_model.py`.
- Features: `distance_km`, `avg_speed_kmph`, `traffic_condition` (0/1/2),
  `stops_remaining`.
- This is clearly a **prototype limitation** — swapping in real historical
  GPS data (once available) is a matter of replacing `generate_training_data()`
  with a loader for real trip logs; the rest of the pipeline (train/predict/API)
  stays the same.

## 8. Notes on route optimization (for your project review)

The 5 stops themselves are fixed (a college bus can't skip stops), but
`backend/services/route_optimizer.py` models a small graph where each pair
of consecutive stops has **two alternate road options** (e.g. Main Road vs
Bypass Road), each with different traffic sensitivity. **Dijkstra's shortest
path algorithm** picks the fastest option per hop given current traffic —
a genuine, standard graph algorithm that's easy to explain in a viva, not a
claim of commercial-grade navigation.

## 9. Limitations to mention in your review (be upfront about these)

- GPS is simulated (distance increases over time on a fixed timer), not real
  hardware — but the code is structured (`geofence.py`, `bus_simulation.py`)
  so a real GPS/GNSS module could replace the simulated distance update with
  minimal changes.
- The live map's bus stop coordinates are approximate points along the real
  Villupuram → IFET College corridor (not surveyed GPS fixes), and the bus
  marker's position is linearly interpolated between the current and next
  stop based on simulated progress — a straight-line approximation of the
  actual road, which is a reasonable simplification for a prototype.
- The ML model is trained on generated, not historical, data.
- The background simulation thread keeps some ephemeral state in memory
  (`services/bus_simulation.py`), which works for the single-process
  `python app.py` dev server used here, but would need a shared store
  (e.g. Redis) if you ever ran multiple server processes.
- QR codes are per-bus-per-day (not per-boarding), which is simple and
  explainable, but in a production system you'd likely rotate them more
  frequently for tighter security.

---

## 10. Troubleshooting

- **"Could not connect to MySQL"** — check `backend/config.py` matches your
  MySQL username/password, and that the MySQL service is running
  (`services.msc` on Windows → look for "MySQL80" or similar → Start).
- **Port 5000 already in use** — close whatever else is using it, or change
  the port in the last lines of `backend/app.py`.
- **Camera QR scanning doesn't work** — some browsers block camera access on
  `http://` (non-HTTPS) for anything other than `localhost`. Since this runs
  on `127.0.0.1`/`localhost`, it should work in Chrome/Edge; if not, use the
  manual QR-text fallback field on the student dashboard.
- **`pip install` fails on `mysql-connector-python`** — make sure you're
  using the virtual environment (`venv\Scripts\activate`) and a Python
  version between 3.10 and 3.12.
