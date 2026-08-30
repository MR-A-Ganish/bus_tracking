from flask import Blueprint, jsonify
from database import run_query
from routes.decorators import login_required
from services.bus_simulation import start_bus
from services.geofence import is_gps_live

buses_bp = Blueprint("buses", __name__)


def _interpolate_position(row):
    """
    Simulated-mode position: linearly interpolate between the bus's current
    stop and next stop, based on how far it has travelled between them.
    """
    lat1, lng1 = row.get("current_lat"), row.get("current_lng")
    if lat1 is None or lng1 is None:
        return None, None

    if row["status"] in ("not_started", "arrived_at_stop", "waiting", "reached_college"):
        return lat1, lng1

    lat2, lng2 = row.get("next_lat"), row.get("next_lng")
    if lat2 is None or lng2 is None:
        return lat1, lng1

    current_km = row.get("current_stop_km") or 0
    next_km = row.get("next_stop_km")
    if next_km is None or next_km <= current_km:
        return lat1, lng1

    fraction = (row["distance_covered_km"] - current_km) / (next_km - current_km)
    fraction = max(0.0, min(1.0, fraction))
    lat = lat1 + fraction * (lat2 - lat1)
    lng = lng1 + fraction * (lng2 - lng1)
    return lat, lng


def _resolve_position(row):
    """
    Real GPS wins whenever a driver has pinged recently; otherwise fall back
    to the simulated interpolation. Returns (lat, lng, is_live).
    """
    if is_gps_live(row.get("gps_updated_at")) and row.get("gps_lat") is not None:
        return row["gps_lat"], row["gps_lng"], True
    lat, lng = _interpolate_position(row)
    return lat, lng, False


@buses_bp.route("/api/buses", methods=["GET"])
@login_required()
def list_buses():
    rows = run_query(
        """SELECT b.*, bl.distance_covered_km, bl.status, bl.traffic_condition, bl.speed_kmph,
                  bl.college_entry_detected, bl.college_entry_time,
                  bl.gps_lat, bl.gps_lng, bl.gps_speed_kmph, bl.gps_accuracy_m, bl.gps_updated_at,
                  cs.stop_name AS current_stop_name, ns.stop_name AS next_stop_name,
                  cs.latitude AS current_lat, cs.longitude AS current_lng,
                  cs.distance_from_start_km AS current_stop_km,
                  ns.latitude AS next_lat, ns.longitude AS next_lng,
                  ns.distance_from_start_km AS next_stop_km
           FROM buses b
           LEFT JOIN bus_locations bl ON bl.bus_id = b.id
           LEFT JOIN bus_stops cs ON cs.id = bl.current_stop_id
           LEFT JOIN bus_stops ns ON ns.id = bl.next_stop_id""",
        fetch=True,
    )
    for r in rows:
        lat, lng, is_live = _resolve_position(r)
        r["lat"] = lat
        r["lng"] = lng
        r["is_live"] = is_live
    return jsonify({"success": True, "buses": rows})


@buses_bp.route("/api/buses/<int:bus_id>/route", methods=["GET"])
@login_required()
def bus_route(bus_id):
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
    loc = run_query(
        """SELECT bl.*, cs.stop_name AS current_stop_name, cs.distance_from_start_km AS current_stop_km,
                  cs.latitude AS current_lat, cs.longitude AS current_lng,
                  ns.stop_name AS next_stop_name, ns.distance_from_start_km AS next_stop_km,
                  ns.latitude AS next_lat, ns.longitude AS next_lng,
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

    loc["stops_remaining"] = stops_remaining
    lat, lng, is_live = _resolve_position(loc)
    loc["lat"] = lat
    loc["lng"] = lng
    loc["is_live"] = is_live
    return jsonify({"success": True, "location": loc})


@buses_bp.route("/api/buses/<int:bus_id>/start", methods=["POST"])
@login_required("admin")
def start_bus_route(bus_id):
    start_bus(bus_id)
    return jsonify({"success": True, "message": "Bus simulation started"})
