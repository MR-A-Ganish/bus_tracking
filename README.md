# College bus tracking

Flask serves the student, driver and management dashboards and a PostgreSQL-backed API.
Drivers share their phone GPS with assigned students and management. The admin fleet map
and student map refresh every three seconds. GPS fixes older than 30 seconds are marked
stale. Stopping sharing preserves the last known location with an offline indicator.

## Run locally

Use Python 3.11 or 3.12 with the pinned requirements.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item backend/.env.example backend/.env
```

Set DATABASE_URL and a unique SECRET_KEY in backend/.env. Preserve your existing .env
if it is already configured. The app uses PostgreSQL. database/schema.sql and database/schema.postgresql.sql both initialize PostgreSQL
without dropping existing tables.

For a new empty database, apply database/schema.postgresql.sql with a PostgreSQL SQL
client. For an existing database, skip initialization. Apply tracked additive migrations.

```powershell
python backend/migrate.py
python backend/app.py
```

Open http://127.0.0.1:5000. A local development server works for desktop testing.
Phone GPS requires an HTTPS deployment and permission to access location.
See the [browser geolocation documentation](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/watchPosition).

## Driver and student trial

1. Deploy the updated backend and frontend to the same HTTPS origin.
2. Log in as the assigned driver on a GPS-capable phone.
3. Select Start trip and allow location permission.
4. Keep the page visible and the phone screen on throughout the trip.
5. Log in as management and an assigned student in separate browser sessions.
6. Confirm both maps show the phone location and recent timestamps.
7. Stop sharing and confirm both dashboards mark the location offline.

Management can end an active trip from the fleet table, including when a driver loses
access to the phone. Trip history is retained.

Browser GPS may pause when the screen locks or the page is backgrounded. Continuous
background fleet tracking requires a native mobile client or a dedicated tracker.
The GPS ingestion endpoint currently authenticates driver browser sessions.

## Database updates

python backend/migrate.py applies each SQL migration once, inside a transaction protected
by an advisory lock. Existing accounts and operational data are preserved. The GPS
migration adds coordinates, accuracy, observation time, sharing state, indexed GPS
history and supporting lookup indexes. Back up the database before operational upgrades.
GPS history is indexed by bus and observation time. Configure a retention period appropriate for the college before long-term operation.

The demo seed script only works with an empty users table. On a fresh demo database,
python backend/seed.py creates student01 / 1234, student02 / 1234,
admin01 / admin123 and driver01 / driver123. Use individual passwords for real users. Create accounts and reset passwords with hidden prompts.

```powershell
python backend/manage_user.py officer --role admin --name "Transport Officer"
python backend/manage_user.py driver02 --role driver --name "Driver Name" --bus-id 2
python backend/manage_user.py student03 --role student --name "Student Name" --bus-id 1 --stop-id 3
python backend/manage_user.py admin01 --reset-password
```

## Deployment configuration

Set DATABASE_URL, SECRET_KEY, APP_ENV=production and SIMULATION_ENABLED=false in the
hosting environment. Set TRUST_PROXY=true only behind the hosting reverse proxy. Preserve your existing private SECRET_KEY. For new installations, generate a random signing key. Use an HTTPS
reverse proxy and run from the repository root on a Linux host.

```sh
python backend/migrate.py
gunicorn --chdir backend --bind 0.0.0.0:8000 --workers 2 app:app
```

/api/health checks database connectivity. The app has same-origin authenticated APIs,
HTTP-only cookies, SameSite=Lax, secure cookies in production, and GPS ownership checks.
For development simulations only, set SIMULATION_ENABLED=true and use one server process.
Simulation skips buses that have received real GPS.

## Verification and remaining operational work

```powershell
python -m unittest discover -s tests -v
python -m compileall -q backend
node --check frontend/js/driver.js
node --check frontend/js/student.js
node --check frontend/js/admin.js
```

The tests cover GPS validation, authentication, assignment checks, cross-origin requests,
out-of-order fixes and freshness. Real phone permissions, map rendering and a moving-bus
trial still need verification on the deployed HTTPS site.

Replace sample stop coordinates with verified college route data before use. Real GPS
updates the map directly. Its ETA is explicitly labeled as a straight-line estimate and
does not incorporate road traffic. GPS fixes with accuracy within 100 metres drive stop arrival and college-entry events.
Management can correct names and coordinates under Route Stops. Route optimization
remains a sample-road demonstration. Boarding codes are signed, expire after two minutes and
refresh on the driver dashboard every minute. Attendance, capacity and notifications
update in one transaction under a bus row lock. Attendance allows one boarding per student per trip. Ending a trip resets the active
passenger count and permits another trip on the configured route. Passenger drop-offs
and reversing route direction are not modeled.
The optional ML ETA uses synthetic training data for simulation.

## Render release

The render.yaml Blueprint describes a web service using an existing DATABASE_URL.
It runs additive migrations before Gunicorn, enables secure cookies and trusts the
single hosting reverse proxy. When updating the existing Render service, set its
build and start commands to the values in render.yaml and apply those environment
settings. Preserve the existing production SECRET_KEY so active sessions remain valid.
Push these project files to the Git repository connected to Render, then deploy that
commit. The source repository is https://github.com/MR-A-Ganish/bus_tracking. Render should
deploy its main branch. The root WSGI entry point applies tracked migrations on Render
even when the service retains its existing gunicorn app:app start command.

## Operational verification

python tests/integration_postgres.py runs real API and concurrency checks in a generated
isolated PostgreSQL schema and removes it afterward. It requires schema-creation
permission on the configured database. No operational student or GPS records are used.
python tests/browser_server.py starts a localhost-only review server backed by another
isolated schema with disposable accounts. POST /__test_shutdown to stop it and remove
the schema. Test accounts use the password browser-test-password and usernames
admin-demo, driver-demo and student-demo.

The backend pools up to five database connections per server process. Authentication,
management changes and notifications share one transaction per HTTP request. Production
uses two workers by default. Set the total worker count within your database connection
limit. The public health endpoint reports migration readiness and the Render commit.

## Vadalur route and pickup stops

The Vadalur to IFET College route starts at Vadalur Bus Stand and ends at the college.
Its initial endpoint distance is a 54.88 km OSRM road-routing estimate. Confirm the
college bus path, cumulative distances and entrance coordinates before operation.
Admins choose Route Stops, select this route, and add pickup names and coordinates.
Use each row's Map button to pick a position. Up and Down change pickup order.
Save the complete stop list after updating cumulative distances. Historical or assigned
stops cannot be deleted, and active trips must end before route order changes.

Under Buses, edit a bus and choose its route. A route change with assigned students
requires the checkbox that moves those assignments to the new starting stop. Then set
each student's actual pickup stop under Students. Active trips prevent bus-route changes.
Existing trips and bus assignments are preserved when the Vadalur route is created.
