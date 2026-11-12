"""
Central configuration for the Smart College Bus System backend.

The application connects to PostgreSQL through the ``DATABASE_URL``
environment variable. Keep credentials out of this file; use ``.env`` for
local development and your host's environment-variable settings in production.
"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

os.environ.setdefault("APP_ENV", "production" if os.environ.get("RENDER") == "true" else "development")
os.environ.setdefault("TRUST_PROXY", "true" if os.environ.get("RENDER") == "true" else "false")
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL and os.environ.get("DB_HOST"):
    from psycopg.conninfo import make_conninfo
    DATABASE_URL = make_conninfo(host=os.environ["DB_HOST"],port=os.environ.get("DB_PORT","5432"),
        user=os.environ.get("DB_USER","postgres"),password=os.environ.get("DB_PASSWORD",""),
        dbname=os.environ.get("DB_NAME","smart_bus_system"),sslmode=os.environ.get("DB_SSLMODE","prefer"))
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured. Add it to backend/.env or to the "
        "deployment environment variables."
    )

# Browser maps need a public, HTTP-referrer-restricted Google Maps JavaScript
# API key. It is intentionally supplied through the environment, never source.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# Secret key used to sign simple session tokens
SECRET_KEY = os.environ.get("SECRET_KEY", "smart-bus-system-dev-secret-change-me")
# Preserve existing signing keys so deployed sessions keep working. Length alone
# does not establish entropy, and changing this setting would invalidate sessions.
if os.environ.get("APP_ENV") == "production" and (
    not SECRET_KEY or SECRET_KEY == "smart-bus-system-dev-secret-change-me"
):
    raise RuntimeError("Set SECRET_KEY to a private value in the deployment environment")

# College geofence (simulated). In this prototype the "geofence" is simply
# "has the bus reached the final stop (IFET College), i.e. distance_covered_km
# >= college_distance_km". Structured this way so it can later be swapped for
# a real lat/lng radius check without touching the rest of the code.
COLLEGE_STOP_NAME = "IFET College"

# How often (seconds) the background bus simulation advances, and how much
# simulated distance is covered per tick. Kept small so a demo run finishes
# in a couple of minutes instead of requiring the bus's real ~26km / 45 min.
SIMULATION_TICK_SECONDS = 2
SIM_SPEED_MULTIPLIER = 25   # simulated minutes of travel compressed per real tick minute equivalent

# Simulation is opt-in and intended for a single-process demonstration.
SIMULATION_ENABLED = os.environ.get("SIMULATION_ENABLED", "false").lower() == "true"

# Time a bus "waits" at a stop for boarding, in simulation ticks
STOP_WAIT_TICKS = 4

# Path to the trained ETA model
ETA_MODEL_PATH = os.path.join(os.path.dirname(__file__), "ai", "eta_model.joblib")
ETA_TRAINING_DATA_PATH = os.path.join(os.path.dirname(__file__), "ai", "training_data.csv")
