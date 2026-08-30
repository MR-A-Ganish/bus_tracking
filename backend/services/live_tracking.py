"""
Processes a real GPS ping from a driver's device: stores the live position,
infers traffic condition from real speed, and - by checking real haversine
distance from the driver's device to each stop on the route - advances
current_stop_id/next_stop_id and fires the same "approaching" / "arrived" /
"college entry" notifications the simulated thread fires, driven by genuine
location data instead of a timer.
"""

from datetime import datetime

from database import run_query
from services.geofence import haversine_km, GEOFENCE_RADIUS_KM
from services.notification_service import create_notification
from config import COLLEGE_STOP_NAME

APPROACH_RADIUS_KM = 1.5

# Per-bus in-memory de-dup so "approaching" doesn't refire on every ping -
# mirrors the simulated thread's _sim_state pattern in bus_simulation.py.
_live_state = {}


def _get_state(bus_id):
    if bus_id not in _live_state:
        _live_state[bus_id] = {"approach_notified_stop_id": None}
    return _live_state[bus_id]


def _notify_students_for_stop(bus, stop, message, event_type):
    students = run_query(
        """SELECT s.id AS student_id FROM student_bus_assignments sba
           JOIN students s ON s.id = sba.student_id
           WHERE sba.bus_id=%s AND sba.stop_id=%s""",
        (bus["id"], stop["id"]), fetch=True,
    )
    for s in students:
        create_notification("student", message, event_type, bus_id=bus["id"], student_id=s["student_id"])


def process_gps_update(bus_id, lat, lng, accuracy_m=None, speed_kmph=None):
    bus = run_query("SELECT * FROM buses WHERE id=%s", (bus_id,), fetch_one=True)
    loc = run_query("SELECT * FROM bus_locations WHERE bus_id=%s", (bus_id,), fetch_one=True)
    if not bus or not loc:
        return

    traffic_condition = None
    if speed_kmph is not None:
        traffic_condition = "high" if speed_kmph < 15 else "medium" if speed_kmph < 28 else "low"

    run_query(
        """UPDATE bus_locations
           SET gps_lat=%s, gps_lng=%s, gps_accuracy_m=%s, gps_speed_kmph=%s, gps_updated_at=%s,
               traffic_condition=COALESCE(%s, traffic_condition),
               speed_kmph=COALESCE(%s, speed_kmph),
               status=CASE WHEN status='not_started' THEN 'moving' ELSE status END
           WHERE bus_id=%s""",
        (lat, lng, accuracy_m, speed_kmph, datetime.now(), traffic_condition, speed_kmph, bus_id),
        commit=True,
    )

    stops = run_query(
        "SELECT * FROM bus_stops WHERE route_id=%s ORDER BY sequence_order ASC",
        (bus["route_id"],), fetch=True,
    )
    if not stops:
        return

    current_seq = None
    if loc["current_stop_id"]:
        current = next((s for s in stops if s["id"] == loc["current_stop_id"]), None)
        current_seq = current["sequence_order"] if current else None

    state = _get_state(bus_id)

    # Arrival: the first stop ahead of our current progress that we're now
    # within the geofence radius of (only advance one stop per ping).
    for stop in stops:
        if stop["latitude"] is None or stop["longitude"] is None:
            continue
        if current_seq is not None and stop["sequence_order"] <= current_seq:
            continue
        distance = haversine_km(lat, lng, stop["latitude"], stop["longitude"])
        if distance > GEOFENCE_RADIUS_KM:
            continue

        next_stop = next((s for s in stops if s["sequence_order"] == stop["sequence_order"] + 1), None)
        run_query(
            "UPDATE bus_locations SET current_stop_id=%s, next_stop_id=%s, status='arrived_at_stop' WHERE bus_id=%s",
            (stop["id"], next_stop["id"] if next_stop else None, bus_id), commit=True,
        )
        state["approach_notified_stop_id"] = None
        _notify_students_for_stop(bus, stop, f"{bus['bus_name']} has arrived at {stop['stop_name']}.", "arrived_at_stop")
        create_notification("admin", f"{bus['bus_name']} arrived at {stop['stop_name']} (live GPS).", "arrived_at_stop", bus_id=bus_id)

        if stop["stop_name"] == COLLEGE_STOP_NAME:
            now = datetime.now()
            run_query(
                "UPDATE bus_locations SET status='reached_college', college_entry_detected=1, college_entry_time=%s WHERE bus_id=%s",
                (now, bus_id), commit=True,
            )
            create_notification(
                "admin", f"{bus['bus_name']} has entered IFET College at {now.strftime('%I:%M %p')} (live GPS).",
                "college_entry", bus_id=bus_id,
            )
        break

    # Approaching: notify students at the very next stop once, when close.
    loc = run_query("SELECT * FROM bus_locations WHERE bus_id=%s", (bus_id,), fetch_one=True)
    next_stop = next((s for s in stops if s["id"] == loc["next_stop_id"]), None)
    if next_stop and next_stop["latitude"] is not None and state["approach_notified_stop_id"] != next_stop["id"]:
        distance = haversine_km(lat, lng, next_stop["latitude"], next_stop["longitude"])
        if distance <= APPROACH_RADIUS_KM:
            state["approach_notified_stop_id"] = next_stop["id"]
            _notify_students_for_stop(bus, next_stop, f"{bus['bus_name']} is approaching {next_stop['stop_name']}.", "approaching_stop")


def reset_live_state(bus_id):
    """Called when a driver starts a fresh trip, so stale de-dup flags don't linger."""
    _live_state.pop(bus_id, None)
