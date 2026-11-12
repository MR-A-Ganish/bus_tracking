import io
from datetime import datetime
from zoneinfo import ZoneInfo
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from config import SECRET_KEY

from flask import Blueprint, request, jsonify, send_file, session
import qrcode

from database import run_query, get_connection
from routes.decorators import login_required

attendance_bp = Blueprint("attendance", __name__)


def _qr_code_for_bus(bus_id):
    location = run_query("SELECT active_trip_id FROM bus_locations WHERE bus_id=%s", (bus_id,), fetch_one=True)
    if not location or not location["active_trip_id"]:
        from werkzeug.exceptions import Conflict
        raise Conflict("Start a trip before displaying a boarding code")
    return URLSafeTimedSerializer(SECRET_KEY, salt="bus-boarding").dumps({"bus_id": bus_id,"trip_id":location["active_trip_id"]})


def _can_display_qr(bus_id):
    from routes.buses import can_access_bus
    return session.get("role") in ("admin", "driver") and can_access_bus(bus_id)


@attendance_bp.route("/api/buses/<int:bus_id>/qr", methods=["GET"])
@login_required()
def get_bus_qr(bus_id):
    if not _can_display_qr(bus_id):
        return jsonify(success=False, message="Only the assigned driver or management can display boarding codes"), 403
    payload = _qr_code_for_bus(bus_id)
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@attendance_bp.route("/api/buses/<int:bus_id>/qr-code-text", methods=["GET"])
@login_required()
def get_bus_qr_text(bus_id):
    if not _can_display_qr(bus_id):
        return jsonify(success=False, message="Only the assigned driver or management can display boarding codes"), 403
    return jsonify({"success": True, "qr_text": _qr_code_for_bus(bus_id)})


@attendance_bp.route("/api/boarding", methods=["POST"])
@login_required("student")
def board_bus():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("qr_text"), str):
        return jsonify(success=False, message="A boarding code is required"), 400
    try:
        payload = URLSafeTimedSerializer(SECRET_KEY, salt="bus-boarding").loads(data["qr_text"], max_age=120)
        bus_id = payload["bus_id"]
        if type(bus_id) is not int:
            raise ValueError()
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return jsonify(success=False, message="Invalid or expired QR code. Scan the driver's current code."), 400
    student_id = session["student_id"]
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    with get_connection() as conn:
        bus = conn.execute("SELECT * FROM buses WHERE id=%s FOR UPDATE", (bus_id,)).fetchone()
        assignment = conn.execute("SELECT * FROM student_bus_assignments WHERE student_id=%s AND bus_id=%s", (student_id, bus_id)).fetchone()
        if not bus or not assignment:
            return jsonify(success=False, message="This is not your assigned bus"), 403
        trip_id = payload.get("trip_id")
        trip = conn.execute("""SELECT t.id FROM bus_trips t JOIN bus_locations bl ON bl.active_trip_id=t.id
                             WHERE t.id=%s AND t.bus_id=%s AND t.ended_at IS NULL""", (trip_id,bus_id)).fetchone()
        if not trip:
            return jsonify(success=False,message="This boarding code belongs to an ended trip"),409
        existing = conn.execute("SELECT id FROM attendance WHERE student_id=%s AND trip_id=%s", (student_id,trip_id)).fetchone()
        if existing:
            return jsonify(success=False, message="Attendance already recorded for this trip"), 409
        passengers = conn.execute("SELECT COUNT(*) AS count FROM attendance WHERE trip_id=%s", (trip_id,)).fetchone()["count"]
        if passengers >= bus["capacity"]:
            return jsonify(success=False, message="Bus full. Boarding unavailable."), 409
        conn.execute("""INSERT INTO attendance(student_id,bus_id,stop_id,attendance_date,attendance_time,trip_id)
                     VALUES (%s,%s,%s,%s,%s,%s)""", (student_id,bus_id,assignment["stop_id"],now.date(),now.strftime("%H:%M:%S"),trip_id))
        passengers += 1
        conn.execute("UPDATE buses SET current_passengers=%s WHERE id=%s", (passengers,bus_id))
        conn.execute("""INSERT INTO notifications(target_role,bus_id,student_id,message,event_type)
                     VALUES ('student',%s,%s,'Boarding confirmed. Attendance recorded.','boarding_confirmed'),
                            ('admin',%s,NULL,'A student boarded the bus.','boarding_confirmed')""", (bus_id,student_id,bus_id))
    return jsonify(success=True, message="Boarding confirmed", passengers=passengers,
                   capacity=bus["capacity"], available_seats=bus["capacity"]-passengers)


@attendance_bp.route("/api/attendance", methods=["GET"])
@login_required("admin")
def list_attendance():
    bus_id = request.args.get("bus_id", type=int)
    query = """SELECT a.*, s.name AS student_name, bs.stop_name, b.bus_name
               FROM attendance a
               JOIN students s ON s.id = a.student_id
               JOIN bus_stops bs ON bs.id = a.stop_id
               JOIN buses b ON b.id = a.bus_id
               WHERE a.attendance_date = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date"""
    params = ()
    if bus_id:
        query += " AND a.bus_id=%s"
        params = (bus_id,)
    query += " ORDER BY a.attendance_time DESC"
    rows = run_query(query, params, fetch=True)
    # Serialize PostgreSQL date and time fields consistently for browsers.
    for r in rows:
        if r.get("attendance_time") is not None:
            r["attendance_time"] = str(r["attendance_time"])
        if r.get("attendance_date") is not None:
            r["attendance_date"] = str(r["attendance_date"])
    return jsonify({"success": True, "attendance": rows})
