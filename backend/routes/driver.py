"""Trip lifecycle compatible with the existing driver dashboard."""
from flask import Blueprint, jsonify, session
from database import get_connection, run_query
from routes.decorators import login_required
from routes.tracking import publish_location, stop_sharing

driver_bp = Blueprint("driver", __name__)


@driver_bp.get("/api/driver/me")
@login_required("driver")
def my_driver_profile():
    driver = run_query("""SELECT d.id,d.name,d.bus_id,b.bus_name,b.route_id,bl.active_trip_id,bl.sharing_active
                          FROM drivers d LEFT JOIN buses b ON b.id=d.bus_id
                          LEFT JOIN bus_locations bl ON bl.bus_id=b.id WHERE d.id=%s""", (session["driver_id"],), fetch_one=True)
    if not driver:
        return jsonify(success=False,message="Driver account not found"),404
    return jsonify(success=True,driver=driver)


@driver_bp.post("/api/driver/start-trip")
@login_required("driver")
def start_trip():
    with get_connection() as conn:
        driver = conn.execute("SELECT * FROM drivers WHERE id=%s FOR SHARE", (session["driver_id"],)).fetchone()
        if not driver or not driver["bus_id"]:
            return jsonify(success=False,message="Ask management to assign a bus"),409
        bus = conn.execute("SELECT * FROM buses WHERE id=%s FOR UPDATE", (driver["bus_id"],)).fetchone()
        location = conn.execute("SELECT * FROM bus_locations WHERE bus_id=%s FOR UPDATE", (bus["id"],)).fetchone()
        active = conn.execute("SELECT * FROM bus_trips WHERE bus_id=%s AND ended_at IS NULL", (bus["id"],)).fetchone()
        if active:
            if active["driver_id"] != driver["id"]:
                return jsonify(success=False,message="Another driver has an active trip for this bus"),409
            return jsonify(success=True,trip_id=active["id"],message="Resuming active trip")
        stops = conn.execute("SELECT id FROM bus_stops WHERE route_id=%s ORDER BY sequence_order", (bus["route_id"],)).fetchall()
        if len(stops) < 2 or not location:
            return jsonify(success=False,message="Management must configure at least two route stops and initialize this bus"),409
        trip = conn.execute("INSERT INTO bus_trips(bus_id,driver_id) VALUES (%s,%s) RETURNING id", (bus["id"],driver["id"])).fetchone()
        conn.execute("""UPDATE bus_locations SET active_trip_id=%s,location_source='gps',sharing_active=FALSE,
                     status='not_started',current_stop_id=%s,next_stop_id=%s,distance_covered_km=0,
                     college_entry_detected=FALSE,college_entry_time=NULL,approach_notified_stop_id=NULL
                     WHERE bus_id=%s""", (trip["id"],stops[0]["id"],stops[1]["id"],bus["id"]))
        conn.execute("UPDATE buses SET current_passengers=0 WHERE id=%s", (bus["id"],))
        conn.execute("INSERT INTO notifications(target_role,bus_id,message,event_type) VALUES ('all',%s,%s,'bus_started')",
                     (bus["id"],f"{bus['bus_name']} trip started. Waiting for the driver's GPS."))
    return jsonify(success=True,trip_id=trip["id"])


driver_bp.add_url_rule("/api/driver/location", view_func=publish_location, methods=["POST"])
driver_bp.add_url_rule("/api/driver/end-trip", view_func=stop_sharing, methods=["POST"])
