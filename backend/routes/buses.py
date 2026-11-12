from flask import Blueprint, jsonify, session
from datetime import datetime, timezone
from database import run_query
from routes.decorators import login_required
from services.bus_simulation import start_bus

buses_bp = Blueprint("buses", __name__)

def can_access_bus(bus_id):
    if session.get("role") == "admin":
        return True
    if session.get("role") == "driver":
        return bool(run_query("SELECT id FROM drivers WHERE id=%s AND bus_id=%s", (session.get("driver_id"), bus_id), fetch_one=True))
    return bool(run_query("SELECT id FROM student_bus_assignments WHERE student_id=%s AND bus_id=%s", (session.get("student_id"), bus_id), fetch_one=True))


def annotate_location(loc):
    timestamp = loc.get("recorded_at")
    age = max(0, (datetime.now(timezone.utc) - timestamp).total_seconds()) if timestamp else None
    loc["is_stale"] = age is None or age > 30 or not loc.get("sharing_active")
    loc["age_seconds"] = round(age) if age is not None else None
    loc["lat"] = loc.get("latitude")
    loc["lng"] = loc.get("longitude")
    loc["is_live"] = loc.get("location_source") == "gps" and not loc["is_stale"]
    loc["tracking_label"] = "Live GPS" if loc["is_live"] else "Last known GPS" if timestamp else "Waiting for GPS"
    if loc.get("location_source") == "simulation":
        from config import SIMULATION_ENABLED
        loc["tracking_label"] = "Demo simulation" if SIMULATION_ENABLED else "Waiting for GPS"
    if timestamp:
        loc["recorded_at"] = timestamp.isoformat()




@buses_bp.route("/api/buses", methods=["GET"])
@login_required("admin")
def list_buses():
    rows = run_query(
        """SELECT b.*, bl.distance_covered_km, bl.status, bl.traffic_condition, bl.speed_kmph,
                  bl.college_entry_detected, bl.college_entry_time,
                  ((bl.college_entry_time AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date =
                   (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date) AS college_entry_today,
                  bl.latitude, bl.longitude, bl.active_trip_id, bl.recorded_at, bl.location_source, bl.sharing_active, bl.accuracy_m,
                  cs.stop_name AS current_stop_name, ns.stop_name AS next_stop_name
           FROM buses b
           LEFT JOIN bus_locations bl ON bl.bus_id = b.id
           LEFT JOIN bus_stops cs ON cs.id = bl.current_stop_id
           LEFT JOIN bus_stops ns ON ns.id = bl.next_stop_id""",
        fetch=True,
    )
    for row in rows:
        annotate_location(row)
    return jsonify({"success": True, "buses": rows})


@buses_bp.route("/api/buses/<int:bus_id>/route", methods=["GET"])
@login_required()
def bus_route(bus_id):
    if not can_access_bus(bus_id):
        return jsonify(success=False, message="Bus is not assigned to you"), 403
    bus = run_query("SELECT * FROM buses WHERE id=%s", (bus_id,), fetch_one=True)
    if not bus:
        return jsonify({"success": False, "message": "Bus not found"}), 404
    stops = run_query(
        "SELECT * FROM bus_stops WHERE route_id=%s ORDER BY sequence_order ASC",
        (bus["route_id"],), fetch=True,
    )
    return jsonify({"success": True, "stops": stops})


@buses_bp.route("/api/buses/<int:bus_id>/location", methods=["GET"])
@login_required()
def bus_location(bus_id):
    if not can_access_bus(bus_id):
        return jsonify(success=False, message="Bus is not assigned to you"), 403
    loc = run_query(
        """SELECT bl.*, cs.stop_name AS current_stop_name, cs.distance_from_start_km AS current_stop_km,
                  ns.stop_name AS next_stop_name, ns.distance_from_start_km AS next_stop_km,
                  b.bus_name, b.capacity, b.current_passengers
           FROM bus_locations bl
           JOIN buses b ON b.id = bl.bus_id
           LEFT JOIN bus_stops cs ON cs.id = bl.current_stop_id
           LEFT JOIN bus_stops ns ON ns.id = bl.next_stop_id
           WHERE bl.bus_id=%s""",
        (bus_id,), fetch_one=True,
    )
    if not loc:
        return jsonify({"success": False, "message": "Bus location not found"}), 404

    stops_total = run_query(
        "SELECT COUNT(*) AS c FROM bus_stops WHERE route_id=(SELECT route_id FROM buses WHERE id=%s)",
        (bus_id,), fetch_one=True,
    )["c"]
    next_seq = run_query("SELECT sequence_order FROM bus_stops WHERE id=%s", (loc["next_stop_id"],), fetch_one=True)
    stops_remaining = (stops_total - next_seq["sequence_order"]) if next_seq else 0

    annotate_location(loc)
    loc["stops_remaining"] = stops_remaining
    return jsonify({"success": True, "location": loc})


@buses_bp.route("/api/buses/<int:bus_id>/start", methods=["POST"])
@login_required("admin")
def start_bus_route(bus_id):
    from config import SIMULATION_ENABLED
    if not SIMULATION_ENABLED:
        return jsonify(success=False, message="Use the driver phone to share live GPS"), 409
    start_bus(bus_id)
    return jsonify({"success": True, "message": "Bus simulation started"})
