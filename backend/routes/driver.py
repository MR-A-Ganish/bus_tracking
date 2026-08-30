from flask import Blueprint, request, jsonify, session
from database import run_query
from routes.decorators import login_required
from services.notification_service import create_notification
from services.live_tracking import process_gps_update, reset_live_state
from services.bus_simulation import register_bus_as_started

driver_bp = Blueprint("driver", __name__)


def _my_driver():
    return run_query(
        """SELECT d.*, b.bus_name, b.route_id FROM drivers d
           LEFT JOIN buses b ON b.id = d.bus_id
           WHERE d.id=%s""",
        (session["driver_id"],), fetch_one=True,
    )


@driver_bp.route("/api/driver/me", methods=["GET"])
@login_required("driver")
def my_driver_profile():
    driver = _my_driver()
    if not driver:
        return jsonify({"success": False, "message": "Driver not found"}), 404
    return jsonify({"success": True, "driver": driver})


@driver_bp.route("/api/driver/start-trip", methods=["POST"])
@login_required("driver")
def start_trip():
    driver = _my_driver()
    if not driver or not driver["bus_id"]:
        return jsonify({"success": False, "message": "No bus assigned to your account yet - ask your Transport Officer."}), 400

    bus_id = driver["bus_id"]
    first_stop = run_query(
        "SELECT * FROM bus_stops WHERE route_id=%s ORDER BY sequence_order ASC LIMIT 1",
        (driver["route_id"],), fetch_one=True,
    )
    second_stop = run_query(
        "SELECT * FROM bus_stops WHERE route_id=%s ORDER BY sequence_order ASC LIMIT 1 OFFSET 1",
        (driver["route_id"],), fetch_one=True,
    )

    reset_live_state(bus_id)
    run_query(
        """UPDATE bus_locations
           SET status='moving', distance_covered_km=0, college_entry_detected=0, college_entry_time=NULL,
               current_stop_id=%s, next_stop_id=%s, gps_updated_at=NULL
           WHERE bus_id=%s""",
        (first_stop["id"] if first_stop else None, second_stop["id"] if second_stop else None, bus_id),
        commit=True,
    )

    register_bus_as_started(bus_id)

    bus = run_query("SELECT * FROM buses WHERE id=%s", (bus_id,), fetch_one=True)
    create_notification("student", f"{bus['bus_name']} has started its trip - live GPS tracking is on.", "bus_started", bus_id=bus_id)
    create_notification("admin", f"{bus['bus_name']} has started its trip - driver {driver['name']} is now sharing live GPS.", "bus_started", bus_id=bus_id)
    return jsonify({"success": True})


@driver_bp.route("/api/driver/location", methods=["POST"])
@login_required("driver")
def update_location():
    driver = _my_driver()
    if not driver or not driver["bus_id"]:
        return jsonify({"success": False, "message": "No bus assigned to your account yet"}), 400

    data = request.get_json(force=True) or {}
    lat = data.get("lat")
    lng = data.get("lng")
    accuracy_m = data.get("accuracy")
    speed_mps = data.get("speed")  # metres/second from the Geolocation API, may be null

    if lat is None or lng is None:
        return jsonify({"success": False, "message": "lat and lng are required"}), 400

    speed_kmph = round(speed_mps * 3.6, 1) if isinstance(speed_mps, (int, float)) and speed_mps >= 0 else None
    process_gps_update(driver["bus_id"], lat, lng, accuracy_m=accuracy_m, speed_kmph=speed_kmph)

    return jsonify({"success": True})


@driver_bp.route("/api/driver/end-trip", methods=["POST"])
@login_required("driver")
def end_trip():
    driver = _my_driver()
    if not driver or not driver["bus_id"]:
        return jsonify({"success": False, "message": "No bus assigned to your account"}), 400

    bus_id = driver["bus_id"]
    loc = run_query("SELECT * FROM bus_locations WHERE bus_id=%s", (bus_id,), fetch_one=True)
    if loc and loc["current_stop_id"]:
        current_stop = run_query("SELECT * FROM bus_stops WHERE id=%s", (loc["current_stop_id"],), fetch_one=True)
        if current_stop:
            run_query(
                "UPDATE bus_locations SET distance_covered_km=%s, gps_updated_at=NULL WHERE bus_id=%s",
                (current_stop["distance_from_start_km"], bus_id), commit=True,
            )
    else:
        run_query("UPDATE bus_locations SET gps_updated_at=NULL WHERE bus_id=%s", (bus_id,), commit=True)

    reset_live_state(bus_id)
    bus = run_query("SELECT * FROM buses WHERE id=%s", (bus_id,), fetch_one=True)
    create_notification("admin", f"Driver {driver['name']} stopped sharing live GPS for {bus['bus_name']}.", "driver_offline", bus_id=bus_id)
    return jsonify({"success": True})
