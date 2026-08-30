"""
Geofence + GPS-liveness helpers, used by both tracking modes:

- Simulated mode (no driver currently connected): college-entry is detected
  by comparing the simulated distance_covered_km against the college stop's
  known distance along the route (has_entered_college()).
- Live mode (a driver is logged in and streaming real GPS): college-entry
  and per-stop arrival are detected with a real haversine distance from the
  driver's actual lat/lng to each stop's coordinates (haversine_km()).

is_gps_live() is the single source of truth for which mode a bus is
currently in: recent-enough gps_updated_at wins over the simulated state.
"""

import math
from datetime import datetime

# Radius (km) that represents "inside college grounds" / "at a stop".
GEOFENCE_RADIUS_KM = 0.15

# A driver is considered actively connected if we've heard from their
# device within this many seconds. Older than this, we fall back to the
# simulated background thread for that bus.
GPS_LIVE_TIMEOUT_SECONDS = 20


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lng points, in kilometres."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def has_entered_college(distance_covered_km, college_distance_km):
    """Simulated-mode college-entry check (see module docstring)."""
    return distance_covered_km >= (college_distance_km - GEOFENCE_RADIUS_KM)


def is_gps_live(gps_updated_at):
    """True if a driver's real GPS ping is recent enough to be authoritative."""
    if not gps_updated_at:
        return False
    return (datetime.now() - gps_updated_at).total_seconds() < GPS_LIVE_TIMEOUT_SECONDS
