"""
Background bus-movement simulation.

Runs in a daemon thread started from app.py. Every SIMULATION_TICK_SECONDS it
advances every bus that has been "started" a little further along its route:

    moving -> arrived_at_stop -> waiting (boarding window) -> moving -> ...
    ... -> reached_college (geofence triggers a management notification)

All state changes are written to bus_locations in MySQL, so the REST API
(and therefore both dashboards) reflect real, changing data - not static
text. This is structured so a real GPS feed could later replace the
`_advance_distance()` step without touching the state machine.
"""

import threading
import time
import random
from datetime import datetime

from database import run_query
from services.geofence import has_entered_college, is_gps_live
from services.notification_service import create_notification
from config import SIMULATION_TICK_SECONDS, STOP_WAIT_TICKS, COLLEGE_STOP_NAME

# Ephemeral, per-bus simulation flags that don't need to live in the DB
# (works for the single-process `flask run` dev server used in this project).
_sim_state = {}  # bus_id -> {"wait_ticks_remaining": int, "approach_notified": bool}

_lock = threading.Lock()
_started_buses = set()


def _get_state(bus_id):
    if bus_id not in _sim_state:
        _sim_state[bus_id] = {"wait_ticks_remaining": 0, "approach_notified": False}
    return _sim_state[bus_id]


def start_bus(bus_id):
    """Called by the /api/buses/<id>/start endpoint (or auto-start on server boot)."""
    with _lock:
        if bus_id in _started_buses:
            return
        _started_buses.add(bus_id)

    loc = run_query("SELECT * FROM bus_locations WHERE bus_id=%s", (bus_id,), fetch_one=True)
    bus = run_query("SELECT * FROM buses WHERE id=%s", (bus_id,), fetch_one=True)
    if loc["status"] == "not_started":
        run_query(
            "UPDATE bus_locations SET status='moving' WHERE bus_id=%s", (bus_id,), commit=True
        )
        create_notification("student", f"{bus['bus_name']} has started its trip.", "bus_started", bus_id=bus_id)
        create_notification("admin", f"{bus['bus_name']} has started its trip.", "bus_started", bus_id=bus_id)


def register_bus_as_started(bus_id):
    """
    Called by routes/driver.py when a driver starts a trip. Adds the bus to
    the simulated thread's active set (with none of start_bus()'s own
    status-change/notification side effects, since the driver flow already
    handles those) so that if the driver's live GPS ever goes stale, the
    simulated thread is ready to seamlessly take over ticking that bus.
    """
    with _lock:
        _started_buses.add(bus_id)


def _get_stops_in_order(route_id):
    return run_query(
        "SELECT * FROM bus_stops WHERE route_id=%s ORDER BY sequence_order ASC",
        (route_id,), fetch=True,
    )


def _tick_bus(bus):
    bus_id = bus["id"]
    loc = run_query("SELECT * FROM bus_locations WHERE bus_id=%s", (bus_id,), fetch_one=True)
    if loc is None or loc["status"] in ("not_started", "reached_college"):
        return
    if is_gps_live(loc["gps_updated_at"]):
        # A driver is actively streaming real GPS for this bus - the simulated
        # thread stands down and lets services/live_tracking.py drive position,
        # stop progress and notifications instead. It resumes automatically
        # once the GPS feed goes stale (see is_gps_live()).
        return

    stops = _get_stops_in_order(bus["route_id"])
    stop_by_id = {s["id"]: s for s in stops}
    state = _get_state(bus_id)

    # Randomly vary traffic a little to keep the demo realistic and to give
    # the ETA model / route optimizer something to react to.
    if random.random() < 0.15:
        new_traffic = random.choice(["low", "medium", "high"])
        run_query("UPDATE bus_locations SET traffic_condition=%s WHERE bus_id=%s", (new_traffic, bus_id), commit=True)
        loc["traffic_condition"] = new_traffic

    if loc["status"] == "moving":
        next_stop = stop_by_id.get(loc["next_stop_id"])
        if next_stop is None:
            return

        traffic_speed_penalty = {"low": 1.0, "medium": 0.75, "high": 0.55}[loc["traffic_condition"]]
        km_per_tick = (loc["speed_kmph"] / 3600) * SIMULATION_TICK_SECONDS * 40 * traffic_speed_penalty
        new_distance = loc["distance_covered_km"] + km_per_tick

        # "Approaching stop" notification once within 2km of the next stop
        remaining = next_stop["distance_from_start_km"] - loc["distance_covered_km"]
        if 0 < remaining <= 2.0 and not state["approach_notified"]:
            state["approach_notified"] = True
            _notify_students_for_stop(bus, next_stop, f"{bus['bus_name']} is approaching {next_stop['stop_name']}.", "approaching_stop")

        if new_distance >= next_stop["distance_from_start_km"]:
            # Arrived exactly at the stop
            run_query(
                "UPDATE bus_locations SET distance_covered_km=%s, status='arrived_at_stop', current_stop_id=%s WHERE bus_id=%s",
                (next_stop["distance_from_start_km"], next_stop["id"], bus_id), commit=True,
            )
            state["wait_ticks_remaining"] = STOP_WAIT_TICKS
            state["approach_notified"] = False
            _notify_students_for_stop(bus, next_stop, f"{bus['bus_name']} has arrived at {next_stop['stop_name']}.", "arrived_at_stop")
            create_notification("admin", f"{bus['bus_name']} arrived at {next_stop['stop_name']}.", "arrived_at_stop", bus_id=bus_id)

            if next_stop["stop_name"] == COLLEGE_STOP_NAME:
                _handle_college_arrival(bus, next_stop)
        else:
            run_query("UPDATE bus_locations SET distance_covered_km=%s WHERE bus_id=%s", (new_distance, bus_id), commit=True)

    elif loc["status"] == "arrived_at_stop":
        run_query("UPDATE bus_locations SET status='waiting' WHERE bus_id=%s", (bus_id,), commit=True)

    elif loc["status"] == "waiting":
        state["wait_ticks_remaining"] -= 1
        if state["wait_ticks_remaining"] <= 0:
            current_stop = stop_by_id.get(loc["current_stop_id"])
            if current_stop and current_stop["stop_name"] == COLLEGE_STOP_NAME:
                return  # journey already ended in _handle_college_arrival
            ordered = sorted(stops, key=lambda s: s["sequence_order"])
            idx = next((i for i, s in enumerate(ordered) if s["id"] == current_stop["id"]), None)
            if idx is not None and idx + 1 < len(ordered):
                new_next = ordered[idx + 1]
                run_query(
                    "UPDATE bus_locations SET status='moving', next_stop_id=%s WHERE bus_id=%s",
                    (new_next["id"], bus_id), commit=True,
                )
                create_notification("admin", f"{bus['bus_name']} is continuing towards {new_next['stop_name']}.", "continuing", bus_id=bus_id)


def _notify_students_for_stop(bus, stop, message, event_type):
    students = run_query(
        """SELECT s.id AS student_id FROM student_bus_assignments sba
           JOIN students s ON s.id = sba.student_id
           WHERE sba.bus_id=%s AND sba.stop_id=%s""",
        (bus["id"], stop["id"]), fetch=True,
    )
    for s in students:
        create_notification("student", message, event_type, bus_id=bus["id"], student_id=s["student_id"])


def _handle_college_arrival(bus, college_stop):
    loc = run_query("SELECT * FROM bus_locations WHERE bus_id=%s", (bus["id"],), fetch_one=True)
    if has_entered_college(loc["distance_covered_km"], college_stop["distance_from_start_km"]):
        now = datetime.now()
        run_query(
            "UPDATE bus_locations SET status='reached_college', college_entry_detected=1, college_entry_time=%s WHERE bus_id=%s",
            (now, bus["id"]), commit=True,
        )
        time_str = now.strftime("%I:%M %p")
        create_notification(
            "admin", f"{bus['bus_name']} has entered IFET College at {time_str}.", "college_entry", bus_id=bus["id"],
        )


def simulation_loop():
    """Runs forever in a background thread, ticking every started bus."""
    while True:
        try:
            buses = run_query("SELECT * FROM buses", fetch=True)
            for bus in buses:
                if bus["id"] in _started_buses:
                    _tick_bus(bus)
        except Exception as e:
            print(f"[bus_simulation] tick error: {e}")
        time.sleep(SIMULATION_TICK_SECONDS)


def start_background_simulation():
    thread = threading.Thread(target=simulation_loop, daemon=True)
    thread.start()
