"""
Central configuration for the Smart College Bus System backend.

All secrets (DB password, session secret key) are read from environment
variables - never hardcoded here, since this file is committed to git.
For local development, copy backend/.env.example to backend/.env and fill
in your real Postgres password there; .env is gitignored and loaded
automatically via python-dotenv below.
"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Render (and most managed Postgres hosts) provide one connection string via
# DATABASE_URL - if it's set, use it directly and ignore the discrete DB_*
# vars below (those are for local dev / hosts that don't provide a DSN).
_DATABASE_URL = os.environ.get("DATABASE_URL")

if _DATABASE_URL:
    DB_CONFIG = {"dsn": _DATABASE_URL}
else:
    DB_CONFIG = {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "smart_bus_system"),
        # "prefer" encrypts when the server supports it and falls back to an
        # unencrypted connection otherwise - safe default for both local dev
        # and a managed host. Override with DB_SSLMODE=require/disable if needed.
        "sslmode": os.environ.get("DB_SSLMODE", "prefer"),
    }

# Secret key used to sign session cookies. Set a real random value via the
# SECRET_KEY env var in any shared/deployed environment.
SECRET_KEY = os.environ.get("SECRET_KEY", "smart-bus-system-dev-secret-change-me")

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

# Time a bus "waits" at a stop for boarding, in simulation ticks
STOP_WAIT_TICKS = 4

# Path to the trained ETA model
ETA_MODEL_PATH = os.path.join(os.path.dirname(__file__), "ai", "eta_model.joblib")
ETA_TRAINING_DATA_PATH = os.path.join(os.path.dirname(__file__), "ai", "training_data.csv")
