"""Authenticated phone GPS ingestion; latest fix and history commit atomically."""
import math
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, session
from database import get_connection
from routes.decorators import login_required

tracking_bp = Blueprint("tracking", __name__)


def validate_fix(data):
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required")
    def number(key, low, high):
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"Invalid {key}")
        return float(value)
    lat = number("latitude", -90, 90)
    lng = number("longitude", -180, 180)
    accuracy = number("accuracy_m", 0, 1000)
    speed = number("speed_kmph", 0, 200)
    try:
        recorded = datetime.fromisoformat(data["recorded_at"].replace("Z", "+00:00"))
        if recorded.tzinfo is None:
            raise ValueError()
        age = (datetime.now(timezone.utc) - recorded).total_seconds()
        if age < -30 or age > 120:
            raise ValueError()
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError("GPS timestamp must be timezone-aware and within the last two minutes")
    return lat, lng, accuracy, speed, recorded


@tracking_bp.post("/api/drivers/location")
@login_required("driver")
def publish_location():
    try:
        lat, lng, accuracy, speed, recorded = validate_fix(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    with get_connection() as conn:
        driver = conn.execute("SELECT bus_id FROM drivers WHERE id=%s FOR SHARE", (session["driver_id"],)).fetchone()
        if not driver:
            return jsonify(success=False, message="Driver assignment missing"), 403
        bus_id = driver["bus_id"]
        bus = conn.execute("SELECT * FROM buses WHERE id=%s FOR UPDATE", (bus_id,)).fetchone()
        loc = conn.execute("SELECT * FROM bus_locations WHERE bus_id=%s FOR UPDATE", (bus_id,)).fetchone()
        if not loc:
            return jsonify(success=False, message="Bus location has not been initialized"), 409
        data = request.get_json()
        if type(data.get("trip_id")) is not int or data["trip_id"] != loc.get("active_trip_id"):
            return jsonify(success=False,message="Start or resume your trip before sharing GPS",error_code="trip_changed"),409
        trip = conn.execute("SELECT * FROM bus_trips WHERE id=%s AND ended_at IS NULL AND driver_id=%s", (data["trip_id"],session["driver_id"])).fetchone()
        if not trip:
            return jsonify(success=False,message="The trip has ended",error_code="trip_changed"),409
        if recorded < trip["started_at"]:
            return jsonify(success=False,message="Waiting for a GPS fix recorded after trip start",error_code="old_fix"),409
        if loc["recorded_at"] and recorded <= loc["recorded_at"]:
            return jsonify(success=False, message="An equal or newer GPS fix is already stored"), 409
        conn.execute("""INSERT INTO gps_history(bus_id,driver_id,latitude,longitude,accuracy_m,speed_kmph,recorded_at,trip_id)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", (bus_id, session["driver_id"],lat,lng,accuracy,speed,recorded,data["trip_id"]))
        conn.execute("""UPDATE bus_locations SET latitude=%s,longitude=%s,accuracy_m=%s,speed_kmph=%s,
                     recorded_at=%s,location_source='gps',sharing_active=TRUE,status=CASE WHEN status='reached_college' THEN status ELSE %s END WHERE bus_id=%s""",
                     (lat,lng,accuracy,speed,recorded,'moving' if speed > 3 else 'waiting',bus_id))
        from services.live_tracking import update_stop_progress
        update_stop_progress(conn,bus,loc,lat,lng,accuracy,recorded)
    return jsonify(success=True, message="Location shared", recorded_at=recorded.isoformat())


@tracking_bp.post("/api/drivers/location/stop")
@login_required("driver")
def stop_sharing():
    with get_connection() as conn:
        driver = conn.execute("SELECT bus_id FROM drivers WHERE id=%s FOR SHARE", (session["driver_id"],)).fetchone()
        if not driver or not driver["bus_id"]:
            return jsonify(success=False,message="No bus assigned"),409
        conn.execute("SELECT id FROM buses WHERE id=%s FOR UPDATE", (driver["bus_id"],))
        loc = conn.execute("SELECT * FROM bus_locations WHERE bus_id=%s FOR UPDATE", (driver["bus_id"],)).fetchone()
        data = request.get_json(silent=True) or {}
        if not loc or data.get("trip_id") != loc.get("active_trip_id"):
            return jsonify(success=False,message="The active trip changed. Refresh your dashboard."),409
        result = conn.execute("UPDATE bus_trips SET ended_at=CURRENT_TIMESTAMP WHERE id=%s AND driver_id=%s AND ended_at IS NULL RETURNING id", (loc["active_trip_id"],session["driver_id"])).fetchone()
        if not result:
            return jsonify(success=False,message="No active trip for this driver"),409
        conn.execute("UPDATE bus_locations SET sharing_active=FALSE,active_trip_id=NULL WHERE bus_id=%s", (driver["bus_id"],))
        conn.execute("UPDATE buses SET current_passengers=0 WHERE id=%s", (driver["bus_id"],))
        conn.execute("INSERT INTO notifications(target_role,bus_id,message,event_type) VALUES ('all',%s,'Trip ended. Location sharing stopped.','trip_ended')", (driver["bus_id"],))
    return jsonify(success=True)
